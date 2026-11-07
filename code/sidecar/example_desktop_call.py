"""
FACP-003 §3.3 示例：Sidecar 向 Executor 发起 desktop_execute 调用

演示两条路径：

  1. 普通动作（L0/L1：find_window / activate_window / type_text ...）
     直接发起，不需要任何高危开关。

  2. 高危动作（L2：file_write / shell_run）
     payload 必须同时带 `risk_level: "high"` 与 `session_high_risk_granted: true`。
     后者由 Sidecar 依据 Observer 对该 FSID 的授信结论填写，Executor 不自行判定权限。
     缺任何一个，Executor 都会在**预检阶段整体拒绝**，一步都不执行（返回 forbidden）。

用法：

    # 只打印信封，不联网（无 NATS 也能验证字段是否正确）
    python example_desktop_call.py --target facp-executor-01 --dry-run

    # 发起 L1 调用
    python example_desktop_call.py --target facp-executor-01 --steps steps_l1.json

    # 发起 L2 调用（需要 Executor 侧 ALLOW_HIGH_RISK=true）
    python example_desktop_call.py --target facp-executor-01 \
        --steps steps_l2.json --high-risk --granted

    # 缺 --granted 时本地就会拦下并报错，不必等 Executor 拒绝
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_desktop_payload(
    steps: list[dict],
    *,
    instruction: str = "",
    high_risk: bool = False,
    granted: bool = False,
    require_confirm: bool = False,
) -> dict:
    """构造 desktop_execute 的 payload（FACP-002 §4.2）。

    高危时**总是显式写入** session_high_risk_granted，
    避免"字段缺失"与"明确未授权"两种情况在目标侧被混为一谈。
    """
    payload = {
        "instruction": instruction,
        "risk_level": "high" if high_risk else "normal",
        "require_confirm": require_confirm,
        "steps": steps,
    }
    if high_risk:
        payload["session_high_risk_granted"] = bool(granted)
    return payload


def build_call(
    *,
    caller_node_id: str,
    caller_domain: str,
    target_node_id: str,
    target_domain: str,
    fsid: str,
    payload: dict,
    intent: str = "desktop_execute",
    call_depth: int = 1,
    max_call_depth: int = 5,
    ttl_seconds: int = 300,
    trace_id: str | None = None,
    msg_id: str | None = None,
) -> dict:
    """组装 COLLAB_CALL 信封（FACP-002 §4）。"""
    cross_domain = caller_domain != target_domain
    call = {
        "msg_type": "COLLAB_CALL",
        "msg_id": msg_id or str(uuid.uuid4()),
        "trace_id": trace_id or f"tr-{uuid.uuid4().hex[:8]}",
        "fsid": fsid,
        "caller_node_id": caller_node_id,
        "caller_domain": caller_domain,
        "target_node_id": target_node_id,
        "target_domain": target_domain,
        "intent": intent,
        "call_depth": call_depth,
        "max_call_depth": max_call_depth,
        "cross_domain": cross_domain,
        "audit_token": None,
        "ttl_seconds": ttl_seconds,
        "created_at": now_iso(),
        "payload": payload,
    }
    return call


REQUIRED_FIELDS = (
    "msg_type", "msg_id", "trace_id", "fsid",
    "caller_node_id", "caller_domain", "target_node_id", "target_domain",
    "intent", "call_depth", "max_call_depth", "cross_domain", "ttl_seconds", "payload",
)


def validate_local(call: dict) -> list[str]:
    """发送前本地自检。目标侧还会按 FACP-002 §6 再校验一次。"""
    problems: list[str] = []

    for field in REQUIRED_FIELDS:
        if call.get(field) in (None, "", []):
            problems.append(f"缺少必填字段: {field}")

    if call.get("msg_type") != "COLLAB_CALL":
        problems.append("msg_type 必须是 COLLAB_CALL")

    if int(call.get("call_depth", 0)) > int(call.get("max_call_depth", 0)):
        problems.append(
            f"call_depth {call['call_depth']} > max_call_depth {call['max_call_depth']}"
        )

    payload = call.get("payload") or {}
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("payload.steps 必须是非空列表")

    if call.get("cross_domain") and not call.get("audit_token"):
        problems.append("跨域调用必须带 audit_token（由 FSHub 审计钩子签发）")

    # 本地就把高危授权缺失拦住，不让它白跑一趟
    if payload.get("risk_level") == "high":
        if "session_high_risk_granted" not in payload:
            problems.append(
                "risk_level=high 但缺少 session_high_risk_granted；"
                "Executor 会在预检阶段整体拒绝"
            )
        elif payload["session_high_risk_granted"] is not True:
            problems.append("session_high_risk_granted 不为 true，L2 动作会被拒绝")

    high_risk_actions = {"file_write", "shell_run"}
    declared = {s.get("action") for s in steps if isinstance(s, dict)}
    if declared & high_risk_actions and payload.get("risk_level") != "high":
        problems.append(
            f"steps 含 L2 动作 {sorted(declared & high_risk_actions)}，"
            "但 risk_level 不是 high"
        )

    return problems


def load_steps(path: str | None) -> list[dict]:
    if not path:
        return [
            {"action": "find_window", "window_title": "Claude"},
        ]
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("steps", [])
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path} 中未找到非空 steps 列表")
    return data


async def send_and_wait(nats_url: str, subject: str, call: dict, timeout: float) -> dict:
    try:
        import nats
    except ImportError:
        raise SystemExit("需要 nats-py：pip install nats-py（仅实际发送时需要，--dry-run 不需要）")

    nc = await nats.connect(nats_url)
    try:
        reply = await nc.request(
            subject,
            json.dumps(call, ensure_ascii=False).encode("utf-8"),
            timeout=timeout,
        )
        return json.loads(reply.data.decode("utf-8"))
    finally:
        await nc.drain()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FACP desktop_execute 调用示例")
    parser.add_argument("--target", default="facp-executor-01", help="目标节点 node_id")
    parser.add_argument("--target-domain", default="local")
    parser.add_argument("--caller", default="claude-desktop-01")
    parser.add_argument("--caller-domain", default="local")
    parser.add_argument("--fsid", default="fs-demo-sidecar-001")
    parser.add_argument("--steps", help="steps JSON 文件路径")
    parser.add_argument("--instruction", default="按 steps 执行桌面动作")
    parser.add_argument("--high-risk", action="store_true", help="标记 payload.risk_level=high")
    parser.add_argument("--granted", action="store_true", help="声明会话已获高危授权")
    parser.add_argument("--require-confirm", action="store_true")
    parser.add_argument("--ttl", type=int, default=300)
    parser.add_argument("--nats-url", default="nats://127.0.0.1:4222")
    parser.add_argument("--dry-run", action="store_true", help="只打印信封，不发送")
    args = parser.parse_args(argv)

    steps = load_steps(args.steps)
    payload = build_desktop_payload(
        steps,
        instruction=args.instruction,
        high_risk=args.high_risk,
        granted=args.granted,
        require_confirm=args.require_confirm,
    )
    call = build_call(
        caller_node_id=args.caller,
        caller_domain=args.caller_domain,
        target_node_id=args.target,
        target_domain=args.target_domain,
        fsid=args.fsid,
        payload=payload,
        ttl_seconds=args.ttl,
    )

    problems = validate_local(call)
    if problems:
        print("本地校验未通过：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(call, ensure_ascii=False, indent=2))
        return 0

    reply = asyncio_run(send_and_wait(args.nats_url, f"node.{args.target}", call, args.ttl))
    print(json.dumps(reply, ensure_ascii=False, indent=2))
    return 0 if reply.get("status") == "success" else 1


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


if __name__ == "__main__":
    raise SystemExit(main())
