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
