"""
FACP-Executor 最小可运行原型
见 docs/04-executor.md

职责边界（重要）：
  1. 只执行传入的 steps，不规划、不推断意图
  2. 永不发起 COLLAB_CALL
  3. 窗口/控件定位不到就失败返回，不猜测

运行要求：
  - Windows
  - 管理员权限（否则 UIA 读不到部分控件树）
  - 依赖：nats-py, python-uiautomation, pillow, python-dotenv
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from nats.aio.client import Client as NATS

from action_engine import ActionEngine
from security_hook import SecurityHook, StepBlocked
from suspend_registry import SuspendRegistry

load_dotenv()

NODE_ID = os.getenv("NODE_ID", "facp-executor-01")
NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
ALLOW_HIGH_RISK = os.getenv("ALLOW_HIGH_RISK", "false").lower() == "true"
SNAPSHOT_ROOT = os.getenv("SNAPSHOT_ROOT", "./log/snap")
SCREENSHOT_POLICY = os.getenv("SCREENSHOT_POLICY", "on_fail")
STEP_TIMEOUT_SEC = int(os.getenv("STEP_TIMEOUT_SEC", "10"))

engine = ActionEngine(snapshot_root=SNAPSHOT_ROOT, step_timeout_sec=STEP_TIMEOUT_SEC)
security = SecurityHook(allow_high_risk=ALLOW_HIGH_RISK)
suspends = SuspendRegistry()

nc = NATS()

# 单实例互斥：一台机器同一时刻只执行一个任务（FACP-004 §4.2）
_exec_lock = asyncio.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_reply(call: dict, status: str, payload: dict, error: dict | None = None,
                elapsed_ms: int = 0) -> dict:
    return {
        "msg_type": "COLLAB_REPLY",
        "msg_id": f"reply-{call.get('msg_id')}",
        "reply_to": call.get("msg_id"),
        "trace_id": call.get("trace_id"),
        "fsid": call.get("fsid"),
        "responder_node_id": NODE_ID,
        "responder_domain": "local",
        "status": status,
        "error": error,
        "elapsed_ms": elapsed_ms,
        "payload": payload,
    }


async def send_reply(subject: str, reply: dict) -> None:
    await nc.publish(subject, json.dumps(reply, ensure_ascii=False).encode("utf-8"))


def validate_envelope(env: dict) -> tuple[bool, str]:
    """前置结构校验（FACP-002 §6 第 1 步）。"""
    required = ["msg_type", "msg_id", "trace_id", "fsid", "caller_node_id",
                "caller_domain", "target_node_id", "intent", "call_depth"]
    for field in required:
        if not env.get(field):
            return False, f"missing field: {field}"
    if env["msg_type"] != "COLLAB_CALL":
        return False, "msg_type must be COLLAB_CALL"
    if env["intent"] != "desktop_execute":
        return False, f"intent not supported: {env['intent']}"
    steps = env.get("payload", {}).get("steps")
    if not isinstance(steps, list) or not steps:
        return False, "payload.steps must be a non-empty list"
    return True, ""


async def handle_message(msg) -> None:
    reply_subject = msg.reply
    started = time.time()

    try:
        env = json.loads(msg.data.decode("utf-8"))
    except Exception as exc:
        # 无法解析的报文无法拿到 msg_id/trace_id，只能落日志，不能可靠回执
        print(f"[FACP] 报文解析失败，丢弃：{exc}")
        return

    ok, reason = validate_envelope(env)
    if not ok:
        if reply_subject:
            await send_reply(reply_subject, build_reply(
                env, "rejected",
                {"reason": reason},
                {"code": "4001", "reason": "schema_invalid", "message": reason, "retryable": False},
                int((time.time() - started) * 1000),
            ))
        return

    # FACP-002 §6 第 4 步：会话级急停校验。被急停的 FSID 一律不再接受新任务。
    fsid = env["fsid"]
    if suspends.is_suspended(fsid):
        if reply_subject:
            await send_reply(reply_subject, build_reply(
                env, "suspended",
                {"reason": "session_suspended"},
                {"code": "4012", "reason": "session_suspended",
                 "message": f"FSID {fsid} 已被用户急停，等待恢复", "retryable": False},
                int((time.time() - started) * 1000),
            ))
        return

    if _exec_lock.locked():
        # 已有任务在执行（FACP-004 §4.2 单实例互斥）
        if reply_subject:
            await send_reply(reply_subject, build_reply(
                env, "rejected",
                {"reason": "busy"},
                {"code": "4020", "reason": "busy", "message": "executor busy", "retryable": True},
                int((time.time() - started) * 1000),
            ))
        return

    async with _exec_lock:
        steps = env["payload"]["steps"]

        # 双开关的第二级：会话是否被授予高危执行权限（FACP-004 §5.2）
        session_granted = bool(env["payload"].get("session_high_risk_granted", False))
        hook = security.for_session(session_granted)

        # 逐条高危预检：任何一步被拦，整个任务不开始
        try:
            hook.precheck_all(steps)
        except StepBlocked as blocked:
            if reply_subject:
                await send_reply(reply_subject, build_reply(
                    env, "forbidden",
                    {"blocked_step_idx": blocked.step_idx, "reason": blocked.reason},
                    {"code": "4009", "reason": "high_risk_blocked",
                     "message": blocked.reason, "retryable": False},
                    int((time.time() - started) * 1000),
                ))
            return

        # 执行；每步前再查一次急停，保证执行中也能停下（FACP-004 §5.4）
        result = engine.run_steps(
            steps,
            trace_id=env["trace_id"],
            suspend_check=lambda: suspends.is_suspended(fsid),
        )

    if result["error"] is None:
        status = "success"
    elif result["error"].get("reason") == "session_suspended":
        status = "suspended"
    else:
        status = "failed"
    payload = {
        "failed_step_idx": result.get("failed_step_idx"),
        "step_results": result["step_results"],
        "snapshot_path": result.get("snapshot"),
    }
    elapsed = int((time.time() - started) * 1000)

    if reply_subject:
        await send_reply(reply_subject, build_reply(env, status, payload,
                                                    result.get("error"), elapsed))


async def main() -> None:
    await nc.connect(NATS_URL)
    await nc.subscribe(f"node.{NODE_ID}", cb=handle_message)
    print(f"[FACP] Executor {NODE_ID} 就绪 | 订阅 node.{NODE_ID} | "
          f"ALLOW_HIGH_RISK={ALLOW_HIGH_RISK} | NATS={NATS_URL}")
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
