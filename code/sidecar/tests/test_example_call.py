"""
Sidecar 调用示例的回归测试（FACP-003 §3.3 / FACP-002 §4）

示例代码是别人照抄的模板，字段写错比文档写错传播得更快，
所以信封构造与本地自检都要有测试兜着。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from example_desktop_call import (  # noqa: E402
    build_call,
    build_desktop_payload,
    validate_local,
)


def make_call(**overrides):
    payload = overrides.pop("payload", build_desktop_payload(
        [{"action": "find_window", "window_title": "Claude"}],
        instruction="切到 Claude",
    ))
    kwargs = dict(
        caller_node_id="claude-desktop-01",
        caller_domain="local",
        target_node_id="facp-executor-01",
        target_domain="local",
        fsid="fs-demo-001",
        payload=payload,
    )
    kwargs.update(overrides)
    return build_call(**kwargs)


# ---------- 信封构造 ----------

def test_call_has_all_required_fields():
    call = make_call()
    for field in ("msg_type", "msg_id", "trace_id", "fsid", "caller_node_id",
                  "caller_domain", "target_node_id", "target_domain", "intent",
                  "call_depth", "max_call_depth", "cross_domain", "ttl_seconds", "payload"):
        assert call.get(field) not in (None, "", []), f"缺字段 {field}"
    assert call["msg_type"] == "COLLAB_CALL"
    assert call["intent"] == "desktop_execute"


def test_ids_are_unique_per_call():
    a, b = make_call(), make_call()
    assert a["msg_id"] != b["msg_id"]
    assert a["trace_id"] != b["trace_id"]


def test_cross_domain_flag_is_derived_not_trusted():
    """cross_domain 必须由两端域名推导，不能让调用方随手写。"""
    same = make_call(caller_domain="cn", target_domain="cn")
    cross = make_call(caller_domain="cn", target_domain="intl")
    assert same["cross_domain"] is False
    assert cross["cross_domain"] is True


# ---------- 高危 payload ----------

def test_normal_payload_has_no_granted_field():
    payload = build_desktop_payload([{"action": "find_window"}], high_risk=False)
    assert payload["risk_level"] == "normal"
    assert "session_high_risk_granted" not in payload


def test_high_risk_payload_always_carries_granted_flag():
    """高危时必须显式写入该字段，缺失与 false 才不会被混为一谈。"""
    granted = build_desktop_payload([{"action": "file_write", "path": "x"}],
                                    high_risk=True, granted=True)
    denied = build_desktop_payload([{"action": "file_write", "path": "x"}],
                                   high_risk=True, granted=False)
    assert granted["risk_level"] == "high"
    assert granted["session_high_risk_granted"] is True
    assert denied["session_high_risk_granted"] is False


# ---------- 本地自检 ----------

def test_benign_call_passes_validation():
    assert validate_local(make_call()) == []


def test_missing_steps_is_rejected():
    call = make_call(payload={"instruction": "x", "risk_level": "normal",
                              "steps": []})
    problems = validate_local(call)
    assert any("steps" in p for p in problems)


def test_l2_action_without_high_risk_flag_is_rejected():
    payload = build_desktop_payload([{"action": "file_write", "path": "x"}])
    problems = validate_local(make_call(payload=payload))
    assert any("risk_level" in p for p in problems)


def test_l2_action_without_granted_is_rejected_locally():
    payload = build_desktop_payload([{"action": "shell_run", "command": "echo hi"}],
                                    high_risk=True, granted=False)
    problems = validate_local(make_call(payload=payload))
    assert any("session_high_risk_granted" in p for p in problems)


def test_l2_action_with_both_flags_passes():
    payload = build_desktop_payload([{"action": "shell_run", "command": "echo hi"}],
                                    high_risk=True, granted=True)
    assert validate_local(make_call(payload=payload)) == []


def test_cross_domain_without_audit_token_is_rejected():
    payload = build_desktop_payload([{"action": "find_window"}])
    call = make_call(caller_domain="cn", target_domain="intl", payload=payload)
    problems = validate_local(call)
    assert any("audit_token" in p for p in problems)


def test_depth_over_limit_is_rejected():
    call = make_call(call_depth=6, max_call_depth=5)
    problems = validate_local(call)
    assert any("call_depth" in p for p in problems)
