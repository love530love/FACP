"""
文档链接校验（docs-check 的一部分）

检查 Markdown 里的站内相对链接：
  1. 目标文件是否存在
  2. 目标文件里是否存在对应的标题锚点（`#xxx`）

外链（http/https/mailto）不检查——网络不可靠，且不该让 CI 依赖外部站点。

用法：
    python scripts/check_links.py            # 校验，有问题返回 1
    python scripts/check_links.py --verbose  # 打印每一条通过的链接
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md")) + [
    ROOT / name for name in ("MAINTENANCE.md", "CHANGELOG.md", "GLOSSARY.md", "ROADMAP.md")
]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

SKIP_PREFIXES = ("http://", "https://", "mailto:", "ftp://")


def strip_fences(text: str) -> str:
    """去掉代码块内容，只留行数占位。

    必须逐行判断围栏，不能用 ````.*?```` 全局匹配：
    文档正文里出现过 ````fcp` 这种四个反引号的行内写法，
    全局正则会把它当成围栏开始，导致后面的代码块配对全部错位。
    """
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    marker = ""

    for line in lines:
        stripped = line.strip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            marker = stripped[:3]
            out.append("")
            continue
        if in_fence and stripped.startswith(marker):
            in_fence = False
            marker = ""
            out.append("")
            continue
        out.append("" if in_fence else line)

    return "\n".join(out)


def slugify(heading: str) -> str:
    """按 GitHub 的标题锚点规则生成 slug。

    规则：去掉行内代码/链接标记 → 小写 → 删掉除字母数字、中文、空格、连字符、下划线以外的字符
    → 空格转连字符。
    """
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def collect_anchors(path: Path) -> set[str]:
    text = strip_fences(path.read_text(encoding="utf-8"))
    anchors = set()
    for _, heading in HEADING_RE.findall(text):
        anchors.add(slugify(heading))
    return anchors


def check_file(path: Path, verbose: bool = False) -> list[str]:
    problems: list[str] = []
    text = strip_fences(path.read_text(encoding="utf-8"))
    anchors_cache: dict[Path, set[str]] = {}

    for target in LINK_RE.findall(text):
        if target.startswith(SKIP_PREFIXES):
            continue

        if target.startswith("#"):
            target_path = path
            anchor = target[1:]
        else:
            path_part, _, anchor = target.partition("#")
            target_path = (path.parent / path_part).resolve()
            path_part_norm = path_part

            if not target_path.exists():
                problems.append(f"{path.relative_to(ROOT)}: 链接目标不存在 -> {path_part_norm}")
                continue

        if anchor:
            if target_path not in anchors_cache:
                anchors_cache[target_path] = collect_anchors(target_path)
            if anchor not in anchors_cache[target_path]:
                problems.append(
                    f"{path.relative_to(ROOT)}: 锚点不存在 -> {target}"
                    f"（{target_path.name} 中无 '#{anchor}'）"
                )
        elif verbose:
            print(f"  OK {path.relative_to(ROOT)} -> {target}")

    return problems


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    all_problems: list[str] = []
    checked = 0

    for path in TARGETS:
        if not path.exists():
            continue
        checked += 1
        all_problems.extend(check_file(path, verbose=verbose))

    if all_problems:
        print(f"共检查 {checked} 份文档，发现 {len(all_problems)} 处链接问题：", file=sys.stderr)
        for p in all_problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"共检查 {checked} 份文档，链接全部有效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
