"""
会话急停的回归测试（FACP-004 §5.4）

这套能力存在的意义就是「停得下来」，所以测试要覆盖三条：
状态文件读写的正确性、执行中被停的时机、以及未急停时不得误停。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from suspend_registry import SuspendRegistry  # noqa: E402
from action_engine import ActionEngine  # noqa: E402


def make_registry(tmp_path):
    return SuspendRegistry(tmp_path / "suspend.json")


def make_engine(tmp_path):
    return ActionEngine(snapshot_root=str(tmp_path / "snap"), step_timeout_sec=5)


# ---------- 状态文件 ----------

def test_default_state_is_not_suspended(tmp_path):
    assert make_registry(tmp_path).is_suspended("fs-demo") is False


def test_set_then_read(tmp_path):
    reg = make_registry(tmp_path)
    reg.set_suspended("fs-demo", True, reason="手动急停")
    assert reg.is_suspended("fs-demo") is True
    # 另一个会话不受影响
    assert reg.is_suspended("fs-other") is False


def test_resume_clears_entry(tmp_path):
    reg = make_registry(tmp_path)
    reg.set_suspended("fs-demo", True)
    reg.set_suspended("fs-demo", False)
    assert reg.is_suspended("fs-demo") is False


def test_state_persists_across_instances(tmp_path):
    path = tmp_path / "suspend.json"
    SuspendRegistry(path).set_suspended("fs-demo", True, reason="跨实例")
    assert SuspendRegistry(path).is_suspended("fs-demo") is True


def test_corrupt_state_file_is_treated_as_not_suspended(tmp_path):
    """文件写坏时不能把整个联邦锁死，按未暂停处理。"""
    path = tmp_path / "suspend.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert SuspendRegistry(path).is_suspended("fs-demo") is False


def test_snapshot_lists_only_suspended(tmp_path):
    reg = make_registry(tmp_path)
    reg.set_suspended("fs-a", True, reason="r")
    reg.set_suspended("fs-b", False)
    snap = reg.snapshot()
    assert list(snap.keys()) == ["fs-a"]
    assert snap["fs-a"]["suspended"] is True


# ---------- 执行中急停 ----------

def test_suspended_before_first_step_executes_nothing(tmp_path):
    engine = make_engine(tmp_path)
    target = tmp_path / "never.txt"
    result = engine.run_steps(
        [{"action": "file_write", "path": str(target), "content": "x"}],
        suspend_check=lambda: True,
    )
    assert result["error"]["code"] == "4012"
    assert result["error"]["reason"] == "session_suspended"
    assert result["step_results"] == []
    assert not target.exists()


def test_suspend_midway_stops_after_completed_steps(tmp_path):
    """第一步做完后才急停：第一步保留结果，第二步不再执行。"""
    engine = make_engine(tmp_path)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        return calls["n"] > 1          # 第一次检查放行，第二次检查已急停

    result = engine.run_steps([
        {"action": "file_write", "path": str(first), "content": "1"},
        {"action": "file_write", "path": str(second), "content": "2"},
    ], suspend_check=check)

    assert first.exists()
    assert not second.exists()
    assert len(result["step_results"]) == 1
    assert result["failed_step_idx"] == 1
    assert result["error"]["code"] == "4012"


def test_not_suspended_runs_all_steps(tmp_path):
    engine = make_engine(tmp_path)
    result = engine.run_steps([
        {"action": "file_write", "path": str(tmp_path / "a.txt"), "content": "a"},
        {"action": "file_write", "path": str(tmp_path / "b.txt"), "content": "b"},
    ], suspend_check=lambda: False)
    assert result["error"] is None
    assert len(result["step_results"]) == 2


def test_without_suspend_check_behaviour_unchanged(tmp_path):
    """不传 suspend_check 时走原路径，老调用不受影响。"""
    engine = make_engine(tmp_path)
    result = engine.run_steps([
        {"action": "file_write", "path": str(tmp_path / "c.txt"), "content": "c"},
    ])
    assert result["error"] is None
