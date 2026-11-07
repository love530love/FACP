"""
安全拦截层回归测试（FACP-004 §5 / FACP-007 P0-1）

这组用例守的是"手脚"的红线：一旦回归失效，Executor 就可能在
没有授权的情况下改写文件或执行命令。每条用例对应规范里的一个条款。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security_hook import SecurityHook, StepBlocked  # noqa: E402


# ---------- 分级与开关 ----------

def test_l1_actions_pass_without_switch():
    """L1 常规写（start_process / click 等）默认放行（§5.1）。"""
    hook = SecurityHook()
    for action in ("start_process", "activate_window", "focus_control", "type_text", "hotkey", "click"):
        hook.check_step(0, {"action": action, "window_title": "Claude"})


def test_l0_read_actions_pass():
    hook = SecurityHook()
    hook.check_step(0, {"action": "find_window", "window_title": "Claude"})
    hook.check_step(1, {"action": "screenshot"})


@pytest.mark.parametrize("action,step", [
    ("file_write", {"action": "file_write", "path": "C:\\tmp\\a.txt"}),
    ("shell_run", {"action": "shell_run", "command": "echo hi"}),
])
def test_l2_blocked_by_default(action, step):
    """L2 高危默认禁止（§5.1/§5.2），错误信息要指出缺的是全局开关。"""
    hook = SecurityHook(allow_high_risk=False)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, step)
    assert "ALLOW_HIGH_RISK" in exc.value.reason


def test_global_switch_alone_is_insufficient():
    """只有全局开关、没有会话授权 → 仍然拒绝（§5.2 双开关）。"""
    hook = SecurityHook(allow_high_risk=True, session_authorized=False)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "shell_run", "command": "echo hi"})
    assert "session" in exc.value.reason.lower() or "会话" in exc.value.reason


def test_session_switch_alone_is_insufficient():
    """只有会话授权、没有全局开关 → 仍然拒绝。"""
    hook = SecurityHook(allow_high_risk=False, session_authorized=True)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "shell_run", "command": "echo hi"})
    assert "ALLOW_HIGH_RISK" in exc.value.reason


def test_both_switches_allow_benign_step():
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    hook.check_step(0, {"action": "shell_run", "command": "echo hi"})
    hook.check_step(1, {"action": "file_write", "path": "C:\\tmp\\new_file.txt",
                        "mode": "create"})


def test_for_session_inherits_global_switch():
    """for_session 派生的 hook 沿用全局开关，只替换会话级结论。"""
    base = SecurityHook(allow_high_risk=True)
    granted = base.for_session(True)
    denied = base.for_session(False)
    assert granted.allow_high_risk is True
    assert denied.session_authorized is False
    with pytest.raises(StepBlocked):
        denied.check_step(0, {"action": "shell_run", "command": "echo hi"})


# ---------- 路径黑名单 ----------

@pytest.mark.parametrize("path", [
    "C:\\Windows\\System32\\drivers\\etc\\hosts",
    "c:\\windows\\temp\\x.txt",
    "C:/Windows/x.txt",
    "C:\\Program Files\\App\\x.txt",
    "C:\\ProgramData\\x.txt",
])
def test_path_blacklist_blocks(path):
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "file_write", "path": path, "mode": "create"})
    assert "黑名单" in exc.value.reason


def test_path_traversal_blocks():
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "file_write", "path": "C:\\tmp\\..\\x.txt", "mode": "create"})
    assert "上跳" in exc.value.reason


def test_file_read_respects_blacklist_without_switch():
    """L0 的 file_read 不需要高危开关，但路径黑名单照样生效（§3.2）。"""
    hook = SecurityHook()
    with pytest.raises(StepBlocked):
        hook.check_step(0, {"action": "file_read", "path": "C:\\Windows\\System32\\x"})


def test_file_read_normal_path_passes():
    hook = SecurityHook()
    hook.check_step(0, {"action": "file_read", "path": "C:\\tmp\\notes.md"})


# ---------- 覆盖保护 ----------

def test_overwrite_existing_file_requires_confirm(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "file_write", "path": str(target)})
    assert "覆盖" in exc.value.reason


def test_overwrite_allowed_when_mode_is_create(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    hook.check_step(0, {"action": "file_write", "path": str(target), "mode": "create"})


def test_new_file_write_passes_when_both_switches_on(tmp_path):
    target = tmp_path / "fresh.txt"
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    hook.check_step(0, {"action": "file_write", "path": str(target)})


# ---------- 命令黑名单 ----------

@pytest.mark.parametrize("command,pattern_hint", [
    ("format c:", "format"),
    ("rm -rf /tmp/x", "rm"),
    ("del /f /q C:\\tmp\\x", "del"),
    ("diskpart", "diskpart"),
    ("reg delete HKLM\\Software\\X /f", "reg"),
    ("bcdedit /set {default} safeboot minimal", "bcdedit"),
    ("shutdown /s /t 0", "shutdown"),
    ("netsh firewall set opmode disable", "netsh"),
    ("sc delete MyService", "sc"),
    ("Remove-Item C:\\tmp -Recurse -Force", "Remove-Item"),
    ("rd /s /q C:\\tmp", "rd"),
])
def test_command_blacklist_blocks(command, pattern_hint):
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    with pytest.raises(StepBlocked) as exc:
        hook.check_step(0, {"action": "shell_run", "command": command})
    assert "黑名单" in exc.value.reason


def test_command_blacklist_is_case_insensitive():
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    with pytest.raises(StepBlocked):
        hook.check_step(0, {"action": "shell_run", "command": "FORMAT C:"})


@pytest.mark.parametrize("command", [
    "echo hello",
    "git status",
    "python scripts/gen_index.py --check",
    "dir",
])
def test_benign_commands_pass(command):
    hook = SecurityHook(allow_high_risk=True, session_authorized=True)
    hook.check_step(0, {"action": "shell_run", "command": command})


# ---------- 整体预检 ----------

def test_precheck_aborts_whole_task_on_any_block():
    """任何一步被拦，整个任务不开始（§5.3 / main.py 预检语义）。"""
    hook = SecurityHook(allow_high_risk=False)
    steps = [
        {"action": "find_window", "window_title": "Claude"},
        {"action": "file_write", "path": "C:\\tmp\\x.txt"},
        {"action": "type_text", "window_title": "Claude", "text": "hi"},
    ]
    with pytest.raises(StepBlocked) as exc:
        hook.precheck_all(steps)
    assert exc.value.step_idx == 1


def test_precheck_passes_when_all_benign():
    hook = SecurityHook()
    hook.precheck_all([
        {"action": "find_window", "window_title": "Claude"},
        {"action": "file_read", "path": "C:\\tmp\\a.md"},
    ])


def test_step_blocked_exposes_index_and_message():
    blocked = StepBlocked(3, "测试原因")
    assert blocked.step_idx == 3
    assert blocked.reason == "测试原因"
    assert str(blocked) == "step[3] blocked: 测试原因"
