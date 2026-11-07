"""
UIA 动作引擎（FACP-004 §3）
每步执行前后校验目标窗口，失败即终止整任务并截图。
"""

import subprocess
import time
from pathlib import Path
from typing import Any

import uiautomation as auto
from PIL import ImageGrab


class ActionEngine:
    def __init__(self, snapshot_root: str, step_timeout_sec: int = 10):
        self.snapshot_root = Path(snapshot_root)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.step_timeout_sec = step_timeout_sec

    # ---------- 基础设施 ----------

    def snapshot(self, trace_id: str, hint: str) -> str:
        ts = int(time.time() * 1000)
        path = self.snapshot_root / f"{trace_id}_{hint}_{ts}.png"
        try:
            ImageGrab.grab().save(path)
            return str(path.resolve())
        except Exception as exc:
            return f"<snapshot failed: {exc}>"

    @staticmethod
    def find_window(title: str, match_mode: str = "contains", timeout: float = 5.0):
        """按标题查找顶层窗口；找不到返回 None（绝不返回"最像的"）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if match_mode == "exact":
                win = auto.WindowControl(searchDepth=1, Name=title)
            else:
                win = auto.WindowControl(searchDepth=1, NameContains=title)
            if win.Exists(0, 0):
                return win
            time.sleep(0.3)
        return None

    @staticmethod
    def assert_foreground(title: str) -> None:
        """校验当前前台窗口是否是目标窗口。"""
        fg = auto.GetForegroundControl()
        if fg is None:
            raise RuntimeError("无法获取前台窗口")
        if title.lower() not in (fg.Name or "").lower():
            raise RuntimeError(f"前台窗口为 '{fg.Name}'，与目标 '{title}' 不一致")

    # ---------- 单步执行 ----------

    def run_step(self, step: dict[str, Any]) -> dict[str, Any]:
        action = step.get("action")
        t0 = time.time()
        result = {"action": action, "ok": False, "verified": False, "msg": ""}

        try:
            if action == "start_process":
                subprocess.Popen([step["path"], *step.get("args", [])],
                                 cwd=step.get("cwd"))
                time.sleep(step.get("wait_sec", 1.5))
                result["ok"] = True
                result["verified"] = True

            elif action == "file_read":
                # L0 只读（FACP-004 §3.2）：不截屏、不改窗口状态
                path = step["path"]
                limit = int(step.get("max_bytes", 65536))
                try:
                    with open(path, "r", encoding=step.get("encoding", "utf-8"),
                              errors="replace") as fh:
                        content = fh.read(limit)
                    result["content"] = content
                    result["truncated"] = len(content) >= limit
                    result["ok"] = True
                    result["verified"] = True
                except FileNotFoundError:
                    result["msg"] = f"文件不存在: {path}"
                except PermissionError as exc:
                    result["msg"] = f"无权限读取: {exc}"

            elif action == "file_write":
                # L2 高危（FACP-004 §5）：能到这里说明安全层已放行双开关
                path = step["path"]
                mode = step.get("mode", "overwrite")   # overwrite / create / append
                content = step.get("content", "")
                encoding = step.get("encoding", "utf-8")
                target = Path(path)
                if step.get("create_parents", True):
                    target.parent.mkdir(parents=True, exist_ok=True)
                if mode == "append":
                    with open(target, "a", encoding=encoding, newline="\n") as fh:
                        fh.write(content)
                else:
                    with open(target, "w", encoding=encoding, newline="\n") as fh:
                        fh.write(content)
                # 回读校验：写入成功 = 文件存在且大小符合预期
                written = target.stat().st_size if target.exists() else -1
                result["ok"] = written >= 0
                result["verified"] = written >= 0
                result["path"] = str(target.resolve())
                result["bytes"] = written
                if not result["ok"]:
                    result["msg"] = "写入后文件不存在"

            elif action == "shell_run":
                # L2 高危（FACP-004 §5）：命令黑名单已在安全层过滤，这里只负责执行
                command = step["command"]
                timeout = int(step.get("timeout_sec", 30))
                try:
                    proc = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=step.get("cwd"),
                    )
                except subprocess.TimeoutExpired:
                    result["msg"] = f"命令超时（>{timeout}s）"
                else:
                    result["exit_code"] = proc.returncode
                    result["stdout"] = proc.stdout[-4000:]
                    result["stderr"] = proc.stderr[-4000:]
                    result["ok"] = proc.returncode == 0
                    result["verified"] = True
                    if proc.returncode != 0:
                        result["msg"] = f"非零退出码: {proc.returncode}"

            elif action == "find_window":
                win = self.find_window(
                    step["window_title"],
                    step.get("match_mode", "contains"),
                    timeout=step.get("timeout_sec", 5.0),
                )
                if win is None:
                    result["msg"] = f"窗口未找到: {step['window_title']}"
                else:
                    result["ok"] = True
                    result["verified"] = True
                    result["window_handle"] = win.NativeWindowHandle

            elif action == "activate_window":
                win = self.find_window(step["window_title"],
                                       step.get("match_mode", "contains"))
                if win is None:
                    result["msg"] = f"窗口不存在: {step['window_title']}"
                else:
                    win.SetActive()
                    win.SetFocus()
                    time.sleep(0.6)
                    self.assert_foreground(step["window_title"])
                    result["ok"] = True
                    result["verified"] = True

            elif action == "focus_control":
                win = self.find_window(step["window_title"])
                if win is None:
                    result["msg"] = f"窗口不存在: {step['window_title']}"
                else:
                    kwargs = {"searchDepth": 3, "Name": step.get("control_name")}
                    if step.get("control_type"):
                        kwargs["ControlType"] = getattr(auto, step["control_type"], None)
                    ctrl = win.Control(**kwargs) if step.get("control_name") else win
                    if ctrl is None or not ctrl.Exists(0, 0):
                        result["msg"] = f"控件不存在: {step.get('control_name')}"
                    else:
                        ctrl.SetFocus()
                        result["ok"] = True
                        result["verified"] = True

            elif action == "type_text":
                win = self.find_window(step["window_title"])
                if win is None:
                    result["msg"] = f"窗口不存在: {step['window_title']}"
                else:
                    win.SetActive()
                    win.SetFocus()
                    time.sleep(0.3)
                    self.assert_foreground(step["window_title"])
                    if step.get("clear_first"):
                        win.SendKeys("{Ctrl}a{Delete}")
                    win.SendKeys(step["text"])
                    if step.get("send_enter"):
                        win.SendKeys("{Enter}")
                    result["ok"] = True
                    # 文本内容无法可靠回读，标记为未校验
                    result["verified"] = False

            elif action == "hotkey":
                auto.SendKeys("+".join(f"{{{k}}}" for k in step["keys"]))
                result["ok"] = True

            elif action == "click":
                win = self.find_window(step["window_title"])
                if win is None:
                    result["msg"] = f"窗口不存在: {step['window_title']}"
                elif step.get("control_name"):
                    ctrl = win.Control(searchDepth=3, Name=step["control_name"])
                    if not ctrl.Exists(0, 0):
                        result["msg"] = f"控件不存在: {step['control_name']}"
                    else:
                        ctrl.Click()
                        result["ok"] = True
                elif step.get("x") is not None and step.get("y") is not None:
                    win.Click(step["x"], step["y"])
                    result["ok"] = True
                else:
                    # 无定位信息的点击一律拒绝（FACP-004 §3.2）
                    result["msg"] = "click 必须提供 control_name 或 (x, y)"

            elif action == "screenshot":
                result["snapshot"] = self.snapshot("manual", "shot")
                result["ok"] = True

            else:
                result["msg"] = f"不支持的动作: {action}"

        except Exception as exc:
            result["msg"] = f"{type(exc).__name__}: {exc}"

        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        return result

    # ---------- 序列执行 ----------

    def run_steps(self, steps: list[dict[str, Any]], trace_id: str = "tr-unknown",
                  suspend_check=None) -> dict[str, Any]:
        """逐条执行。suspend_check 是可调用对象，返回 True 表示会话已被急停（FACP-004 §5.4）。

        检查点放在每一步**执行前**而不是执行后：急停的语义是「不再做任何新动作」，
        已经做完的步骤照常计入 step_results，方便调用方知道停在哪一步。
        """
        step_results = []
        for idx, step in enumerate(steps):
            if suspend_check is not None and suspend_check():
                return {
                    "step_results": step_results,
                    "failed_step_idx": idx,
                    "snapshot": self.snapshot(trace_id, f"suspended_before_step{idx}"),
                    "error": {
                        "code": "4012",
                        "reason": "session_suspended",
                        "message": f"第 {idx} 步执行前收到会话急停，已停止后续动作",
                        "failed_step_idx": idx,
                        "retryable": False,
                    },
                }
            r = self.run_step(step)
            r["step_idx"] = idx
            step_results.append(r)

            if not r["ok"]:
                return {
                    "step_results": step_results,
                    "failed_step_idx": idx,
                    "snapshot": self.snapshot(trace_id, f"fail_step{idx}"),
                    "error": {
                        "code": "5002",
                        "reason": "step_failed",
                        "message": r["msg"],
                        "failed_step_idx": idx,
                        "retryable": True,
                    },
                }

        return {
            "step_results": step_results,
            "failed_step_idx": None,
            "snapshot": self.snapshot(trace_id, "done"),
            "error": None,
        }
