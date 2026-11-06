#!/usr/bin/env python3
"""
FACP 文档索引生成器（见 MAINTENANCE §8）

用法：
    python scripts/gen_index.py            打印索引表
    python scripts/gen_index.py --write    回写 README 的标记区块
    python scripts/gen_index.py --check    仅校验 front matter，失败时退出码 1

不依赖第三方库：front matter 用极简 YAML 子集解析（key: value / key: [a, b]）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
README = ROOT / "README.md"
START = "<!-- INDEX:START -->"
END = "<!-- INDEX:END -->"


def parse_front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    raw = text[3:end].strip()
    meta: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key] = [v.strip() for v in inner.split(",")] if inner else []
        else:
            meta[key] = value
    return meta


def collect() -> tuple[list[tuple[Path, dict]], list[str]]:
    docs, problems = [], []
    if not DOCS_DIR.exists():
        return docs, [f"docs/ 不存在: {DOCS_DIR}"]

    for path in sorted(DOCS_DIR.glob("*.md")):
        meta = parse_front_matter(path.read_text(encoding="utf-8"))
        if not meta:
            problems.append(f"{path.name}: 缺少 front matter")
            continue

        missing = [k for k in ("id", "title", "version", "status", "updated") if k not in meta]
        if missing:
            problems.append(f"{path.name}: front matter 缺字段 {missing}")

        expected_id = "FACP-" + path.name.split("-")[0].zfill(3)
        if meta.get("id") and meta["id"] != expected_id:
            problems.append(f"{path.name}: id={meta['id']} 与文件名前缀不符（应为 {expected_id}）")

        if meta.get("status") not in {"draft", "review", "stable", "deprecated"}:
            problems.append(f"{path.name}: status={meta.get('status')} 不在允许集合内")

        docs.append((path, meta))
    return docs, problems


def render_table(docs: list[tuple[Path, dict]]) -> str:
    lines = [
        "| 编号 | 文档 | 状态 | 版本 | 最近更新 | 关联 |",
        "|---|---|---|---|---|---|",
    ]
    for path, meta in docs:
        rel = path.relative_to(ROOT).as_posix()
        related = ", ".join(meta.get("related", []) or [])
        lines.append(
            f"| [{meta.get('id')}]({rel}) | {meta.get('title')} | "
            f"`{meta.get('status')}` | {meta.get('version')} | "
            f"{meta.get('updated')} | {related} |"
        )
    return "\n".join(lines)


def write_back(table: str) -> bool:
    if not README.exists():
        print(f"README 不存在: {README}", file=sys.stderr)
        return False
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(f"README 中缺少标记区块 {START} / {END}", file=sys.stderr)
        return False
    new = re.sub(
        f"{re.escape(START)}.*?{re.escape(END)}",
        f"{START}\n{table}\n{END}",
        text,
        flags=re.DOTALL,
    )
    README.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="FACP 文档索引生成")
    ap.add_argument("--write", action="store_true", help="回写 README 标记区块")
    ap.add_argument("--check", action="store_true", help="仅校验 front matter")
    args = ap.parse_args()

    docs, problems = collect()
    if problems:
        for p in problems:
            print(f"⚠ {p}", file=sys.stderr)

    table = render_table(docs)

    if args.check:
        print(f"共 {len(docs)} 份文档，{len(problems)} 个问题")
        return 1 if problems else 0

    if args.write:
        ok = write_back(table)
        print(f"已写入 README，共 {len(docs)} 份文档" if ok else "写入失败")
        return 0 if ok else 1

    print(table)
    if problems:
        print(f"\n⚠ {len(problems)} 个问题（见 stderr）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
