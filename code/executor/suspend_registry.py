"""
会话急停标志（FACP-004 §5.4）

Executor 与 Sidecar 通常同机，用一个 JSON 状态文件传递 user_suspend 信号：
  - Sidecar 收到 `POST /suspend`、或用户在界面上点急停 → 写本文件
  - Executor 在收到 CALL 的预检阶段、以及每一步执行前 → 读本文件

为什么不用 NATS 控制消息：FACP-002 §1 把消息类型限定为 CALL / REPLY 两类，
新增第三类会动协议地基。本地文件是跨进程、零依赖、不改信封的传导方式，
代价是要求 Executor 与 Sidecar 同机（FACP 的单节点模型本就如此）。

文件约定（`suspend.json`）：

    {
      "fs-xxx": {"suspended": true, "updated_at": "2026-11-07T19:00:00+08:00", "reason": "用户手动急停"}
    }

损坏或不可读时按「未暂停」处理：急停开关由本机用户掌控，
误停会让整个联邦不可用，而能写坏这个文件的人本来就能直接改配置。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def default_path() -> Path:
    override = os.environ.get("FACP_SUSPEND_FILE")
    if override:
        return Path(override)
    base = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_STATE_HOME")
        or str(Path.home())
    )
    return Path(base) / "FACP" / "suspend.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SuspendRegistry:
    """读写急停状态，按 mtime 缓存，避免每步都打一次磁盘。"""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        self._cache: dict = {}
        self._mtime: int | None = None

    def _load(self) -> dict:
        if not self.path.exists():
            self._cache, self._mtime = {}, None
            return self._cache

        mtime = self.path.stat().st_mtime_ns
        if mtime != self._mtime:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._cache = data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self._cache = {}
            self._mtime = mtime
        return self._cache

    def is_suspended(self, fsid: str) -> bool:
        entry = self._load().get(fsid)
        if entry is None:
            return False
        if isinstance(entry, dict):
            return bool(entry.get("suspended"))
        return bool(entry)

    def set_suspended(self, fsid: str, suspended: bool, reason: str = "") -> dict:
        state = dict(self._load())
        if suspended:
            state[fsid] = {
                "suspended": True,
                "updated_at": now_iso(),
                "reason": reason,
            }
        else:
            state.pop(fsid, None)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, self.path)          # 原子替换，避免读到半截文件
        self._cache = state
        self._mtime = self.path.stat().st_mtime_ns
        return state

    def snapshot(self) -> dict:
        return dict(self._load())
