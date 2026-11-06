# FACP 文档维护规范

> 目的：这套文档不是一次性材料，而是**长期演进的架构基线**。任何人（包括未来的自己）改代码前先改文档、改完代码回写文档，保证文档与实现不脱节。

---

## 1. 文档元信息规范（强制）

每份 `docs/*.md` 顶部必须有 YAML front matter：

```yaml
---
id: FACP-002
title: 消息协议规范
version: 0.4.0
status: stable
owner: 李富强
updated: 2026-11-07
related: [FACP-001, FACP-003, FACP-004]
---
```

| 字段 | 规则 |
|---|---|
| `id` | 全局唯一，格式 `FACP-00N`，与文件名前缀一致，**永不复用** |
| `version` | `MAJOR.MINOR.PATCH`，见 §3 |
| `status` | `draft` / `review` / `stable` / `deprecated`，见 §2 |
| `updated` | ISO 日期，每次实质修改必更新 |
| `related` | 关联文档 id 数组，用于索引脚本生成交叉引用 |

缺任一字段 → `gen_index.py` 会在输出中标记 `⚠ metadata incomplete`，CI/自检时视为失败。

## 2. 状态流转

```
draft ──评审通过──> review ──冻结──> stable ──废弃──> deprecated
  ↑                    │
  └────返工修改────────┘
```

| 状态 | 含义 | 允许被引用为实现依据？ |
|---|---|---|
| `draft` | 思路未定，字段可能大改 | ❌ 仅讨论 |
| `review` | 结构已定，等待验证 | ⚠️ 可开发原型 |
| `stable` | 已实现并验证，变更需走变更评审 | ✅ 是 |
| `deprecated` | 被新文档取代，保留历史 | ❌ 顶部必须写明替代文档 |

> **稳定版变更门槛**：`stable` 文档修改任何**协议字段、枚举值、校验规则**，必须同时更新 `CHANGELOG.md` 的 `Changed` 段，并在 PR/提交说明中写明影响面（哪些 Sidecar / Executor 需要同步改）。

## 3. 版本号规则

| 变更类型 | 版本动作 | 示例 |
|---|---|---|
| 措辞修正、补例子、修错别字 | `PATCH +1` | 0.4.0 → 0.4.1 |
| 新增章节、新增可选字段、补充能力 | `MINOR +1` | 0.4.1 → 0.5.0 |
| 删除/重命名字段、改枚举、改校验语义、破坏兼容 | `MAJOR +1` | 0.5.0 → 1.0.0 |

> 协议类文档（FACP-002 / 001 / 003 / 004）的 **MAJOR 变更必须同时给出迁移说明**（旧字段如何处理、是否需要双写过渡期）。

## 4. 一次标准更新的完整流程

1. **先定影响面**：这次改的是身份？协议？执行语义？还是纯 UI？
2. **改文档**：对应 `docs/*.md`，更新 `updated` / `version`。
3. **改索引**：`python scripts/gen_index.py --write`。
4. **改代码**：`code/` 下对应模块 + 注释里引用文档 id（如 `# see FACP-002 §6`）。
5. **记变更**：在 `CHANGELOG.md` 的 `[Unreleased]` 段追加条目，分类为 `Added / Changed / Deprecated / Removed / Fixed / Security`。
6. **过清单**：跑 §6 自检清单。
7. **发版时**：`[Unreleased]` 提升为版本标题 + 日期。

## 5. 目录与命名约定

```
FACP/
├── README.md                 总入口（人读第一页）
├── MAINTENANCE.md            本文件
├── CHANGELOG.md              变更日志
├── ROADMAP.md                演进路线
├── GLOSSARY.md               术语表
├── docs/
│   ├── 00-overview.md        编号即阅读顺序，编号不复用
│   └── NN-topic.md           kebab-case，英文短名
├── code/
│   └── <module>/             可运行样例，与文档 id 对应
└── scripts/
    └── gen_index.py
```

- 文档正文用**中文**，字段名 / 枚举 / 主题名用**英文**，避免中英混杂产生歧义。
- 代码块必须标语言。
- 引用其他文档用相对路径链接，不用绝对路径。
- 不写"待定/以后再说"的悬空段；未定内容写进 `ROADMAP.md` 的 `Open Questions`，正文只写已定结论。

## 6. 更新后自检清单

```
[ ] front matter 完整，id 无重复，version 按规则递增
[ ] 索引已重新生成（README 表格与 docs 实际一致）
[ ] CHANGELOG 有对应条目
[ ] 协议改动：示例 JSON 与字段说明一致，无残留旧字段
[ ] 跨文档引用未失效（related 双向可追溯）
[ ] 涉及的代码样例能跑（至少 import/语法通过）
[ ] 安全域相关改动：默认拒绝原则未被破坏
[ ] 未引入"中心调度"语义（协作平面仍不做决策）
```

## 7. 定期维护节奏

| 频率 | 动作 |
|---|---|
| 每次实质修改 | 走 §4 流程 |
| 每周 | 检查 `draft` 文档是否该推进 / 废弃；清理 `[Unreleased]` |
| 每月 | 对照代码实际行为复核 `stable` 文档（协议漂移检查） |
| 每个 Phase 结束 | 更新 `ROADMAP.md` 阶段状态，归档已废弃节点适配器文档 |

## 8. 索引脚本

```bash
python scripts/gen_index.py            # 打印索引表，不写文件
python scripts/gen_index.py --write    # 回写 README 的标记区块
python scripts/gen_index.py --check    # 只校验 front matter，缺失/重复时非零退出
```

索引脚本只改写 README 中两行标记之间的内容：

```markdown
<!-- INDEX:START -->
... 自动生成，勿手改 ...
<!-- INDEX:END -->
```

> 因此 README 的叙述性文字可以自由编辑，只有标记区块受脚本管辖。
