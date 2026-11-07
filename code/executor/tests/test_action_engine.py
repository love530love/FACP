"""
动作引擎回归测试（FACP-004 §3）

只测不依赖真实桌面环境的 L0 动作（file_read）与错误分支。
UIA / PIL 在 CI 的 Linux runner 上不可用，这里用 stub 顶替导入，
不执行任何窗口操作。
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# 在导入 action_engine 之前顶替 Windows 专属依赖
sys.modules.setdefault("uiautomation", MagicMock())

if "PIL" not in sys.modules:
    pil = types.ModuleType("PIL")
    pil.ImageGrab = types.ModuleType("PIL.ImageGrab")
    sys.modules["PIL"] = pil
    sys.modules["PIL.ImageGrab"] = pil.ImageGrab

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from action_engine import ActionEngine  # noqa: E402


def make_engine(tmp_path):
    return ActionEngine(snapshot_root=str(tmp_path / "snap"))


def test_file_read_returns_content(tmp_path):
    target = tmp_path / "note.md"
    target.write_text("hello facp", encoding="utf-8")
    result = make_engine(tmp_path).run_step({"action": "file_read", "path": str(target)})
    assert result["ok"] is True
    assert result["verified"] is True
    assert result["content"] == "hello facp"
    assert result["truncated"] is False


def test_file_read_respects_max_bytes(tmp_path):
    target = tmp_path / "big.txt"
    target.write_text("x" * 1000, encoding="utf-8")
    result = make_engine(tmp_path).run_step(
        {"action": "file_read", "path": str(target), "max_bytes": 100}
    )
    assert result["ok"] is True
    assert len(result["content"]) == 100
    assert result["truncated"] is True


def test_file_read_missing_file_fails(tmp_path):
    result = make_engine(tmp_path).run_step(
        {"action": "file_read", "path": str(tmp_path / "nope.txt")}
    )
    assert result["ok"] is False
    assert "不存在" in result["msg"]


def test_unknown_action_fails_without_raising(tmp_path):
    result = make_engine(tmp_path).run_step({"action": "teleport"})
    assert result["ok"] is False
    assert "不支持" in result["msg"]


def test_snapshot_dir_created(tmp_path):
    snap = tmp_path / "deep" / "snap"
    ActionEngine(snapshot_root=str(snap))
    assert snap.is_dir()


def test_run_steps_aborts_at_first_failure(tmp_path):
    engine = make_engine(tmp_path)
    steps = [
        {"action": "file_read", "path": str(tmp_path / "missing.txt")},
        {"action": "file_read", "path": str(tmp_path / "missing2.txt")},
    ]
    out = engine.run_steps(steps, trace_id="tr-test")
    assert out["failed_step_idx"] == 0
    assert len(out["step_results"]) == 1
    assert out["error"]["code"] == "5002"
    assert out["error"]["retryable"] is True


# ---------- file_write（L2） ----------

def test_file_write_create(tmp_path):
    target = tmp_path / "out.txt"
    result = make_engine(tmp_path).run_step({
        "action": "file_write", "path": str(target), "mode": "create", "content": "hello"
    })
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "hello"
    assert result["bytes"] >= 4


def test_file_write_append_keeps_previous_content(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("first\n", encoding="utf-8")
    result = make_engine(tmp_path).run_step({
        "action": "file_write", "path": str(target), "mode": "append", "content": "second\n"
    })
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "first\nsecond\n"


def test_file_write_overwrite_replaces(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("old content", encoding="utf-8")
    result = make_engine(tmp_path).run_step({
        "action": "file_write", "path": str(target), "content": "new"
    })
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "new"


def test_file_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "out.txt"
    result = make_engine(tmp_path).run_step({
        "action": "file_write", "path": str(target), "mode": "create", "content": "x"
    })
    assert result["ok"] is True
    assert target.exists()


def test_file_write_writes_lf_line_endings(tmp_path):
    """写入端统一 LF，避免跨平台 diff 噪音。"""
    target = tmp_path / "out.txt"
    make_engine(tmp_path).run_step({
        "action": "file_write", "path": str(target), "content": "a\nb\n"
    })
    raw = target.read_bytes()
    assert b"\r\n" not in raw
    assert b"a\nb\n" in raw


# ---------- shell_run（L2） ----------

def test_shell_run_captures_stdout(tmp_path):
    result = make_engine(tmp_path).run_step({
        "action": "shell_run", "command": 'python -c "print(\'facp-ok\')"'
    })
    assert result["ok"] is True
    assert result["verified"] is True
    assert "facp-ok" in result["stdout"]
    assert result["exit_code"] == 0


def test_shell_run_nonzero_exit_marks_failed(tmp_path):
    result = make_engine(tmp_path).run_step({
        "action": "shell_run", "command": 'python -c "import sys; sys.exit(3)"'
    })
    assert result["ok"] is False
    assert result["exit_code"] == 3
    assert "非零退出码" in result["msg"]


def test_shell_run_times_out(tmp_path):
    result = make_engine(tmp_path).run_step({
        "action": "shell_run",
        "command": 'python -c "import time; time.sleep(5)"',
        "timeout_sec": 1,
    })
    assert result["ok"] is False
    assert "超时" in result["msg"]
