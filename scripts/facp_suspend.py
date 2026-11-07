"""
会话急停开关（命令行版）

FACP-003 §5 的 `POST /suspend` 是 Sidecar 的 HTTP 接口，实现时调用的就是同一套逻辑；
在 Sidecar 还没跑起来的时候，这个脚本给人一个能立刻按下的急停按钮。

用法：
    # 急停某会话
    python scripts/facp_suspend.py --fsid fs-demo-001 --suspend --reason "发现它在乱点"

    # 恢复
    python scripts/facp_suspend.py --fsid fs-demo-001 --resume

    # 看当前所有被急停的会话
    python scripts/facp_suspend.py --status
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code" / "executor"))

from suspend_registry import SuspendRegistry, default_path  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="FACP 会话急停开关")
    parser.add_argument("--fsid", help="目标会话 ID")
    parser.add_argument("--suspend", action="store_true", help="急停该会话")
    parser.add_argument("--resume", action="store_true", help="恢复该会话")
    parser.add_argument("--status", action="store_true", help="打印当前急停状态")
    parser.add_argument("--reason", default="", help="写入状态的说明，便于事后追溯")
    parser.add_argument("--file", help="覆盖状态文件路径（默认取 FACP_SUSPEND_FILE 或系统目录）")
    args = parser.parse_args(argv)

    registry = SuspendRegistry(args.file)

    if args.status:
        state = registry.snapshot()
        print(f"状态文件: {registry.path}")
        if not state:
            print("当前没有会话被急停")
            return 0
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if not args.fsid:
        parser.error("--fsid 必填（除非使用 --status）")
    if args.suspend == args.resume:
        parser.error("--suspend 与 --resume 必须且只能选一个")

    registry.set_suspended(args.fsid, args.suspend, reason=args.reason)
    action = "已急停" if args.suspend else "已恢复"
    print(f"{action}: {args.fsid}")
    print(f"状态文件: {registry.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
