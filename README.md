# FACP — 联邦 Agent 协作平面

[![docs-check](https://github.com/love530love/FACP/actions/workflows/docs-check.yml/badge.svg)](https://github.com/love530love/FACP/actions/workflows/docs-check.yml)
[![release](https://img.shields.io/github/v/tag/love530love/FACP?label=release)](https://github.com/love530love/FACP/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **F**ederation **A**gent **C**ollaboration **P**lane
> 让 Claude Desktop、Qoder（CN/INTL）、WorkBuddy（CN/INTL）、豆包（CN/INTL）、Codex Desktop 等**互相独立、闭源的桌面 AI 客户端**，以对等节点方式自发协作；并为其配一套可被任意节点调用的桌面执行手脚（FACP-Executor），替代工程师手工操作电脑。

---

## 一句话定位

> 不是写一个调度器去指挥各个 AI，而是**让每个 AI 自己成为联邦里的一个节点**：它知道同伴是谁、能力是什么、属于国内还是国际安全域；当任务超出自身边界时，自主生成协作请求，由边车（Sidecar）代为寻址、唤醒进程、切换会话、传递上下文信封；需要操控电脑时，派工给 Executor 执行。

## 三条不可让步的底线

| # | 底线 | 说明 |
|---|---|---|
| 1 | **不做中心调度** | 协作平面只负责注册、寻址、投递、校验、审计、观测；决策权在 Agent 本体 |
| 2 | **身份不可混淆** | `qoder-cn` 与 `qoder-intl` 是两个独立节点；同版本多账号也是独立节点 |
| 3 | **跨域默认拒绝** | CN / INTL 域默认不通；跨域是**会话级**授权，全链路审计留痕 |

## 文档地图

### 核心文档

> 下表由 `scripts/gen_index.py` 自动生成，请勿手改。

<!-- INDEX:START -->
| 编号 | 文档 | 状态 | 版本 | 最近更新 | 关联 |
|---|---|---|---|---|---|
| [FACP-000](docs/00-overview.md) | 架构总览与设计原则 | `stable` | 0.3.0 | 2026-11-07 | FACP-001, FACP-002, FACP-003, FACP-004, FACP-005 |
| [FACP-001](docs/01-identity-domain.md) | 身份模型与安全域规范 | `stable` | 0.2.0 | 2026-11-07 | FACP-000, FACP-002, FACP-003 |
| [FACP-002](docs/02-protocol.md) | 消息协议规范 | `stable` | 0.4.0 | 2026-11-07 | FACP-001, FACP-003, FACP-004 |
| [FACP-003](docs/03-sidecar.md) | Sidecar SDK 开发规范与接口 | `draft` | 0.2.0 | 2026-11-07 | FACP-001, FACP-002, FACP-004 |
| [FACP-004](docs/04-executor.md) | Executor 执行引擎（手脚）规范 | `draft` | 0.2.0 | 2026-11-07 | FACP-002, FACP-007 |
| [FACP-005](docs/05-observer.md) | Observer 观测面板 PRD | `draft` | 0.1.0 | 2026-11-07 | FACP-000, FACP-001, FACP-004 |
| [FACP-006](docs/06-prompts.md) | 联邦模式系统提示词集 | `review` | 0.2.0 | 2026-11-07 | FACP-001, FACP-002, FACP-004 |
| [FACP-007](docs/07-risk.md) | 风险评估与风控约束 | `stable` | 0.3.0 | 2026-11-07 | FACP-001, FACP-004, FACP-008 |
| [FACP-008](docs/08-deployment.md) | 部署清单与运行环境 | `draft` | 0.1.0 | 2026-11-07 | FACP-003, FACP-004, FACP-007 |
<!-- INDEX:END -->

### 阅读路径建议

| 你是谁 / 想干什么 | 建议顺序 |
|---|---|
| 第一次了解全局 | 00 → 01 → 02 |
| 写 Sidecar 适配器 | 01 → 02 → 03 → 06 |
| 写 Executor / 执行层 | 02 → 04 → 07 |
| 改 UI / 面板 | 05 → 01 |
| 上线部署 | 08 → 07 |

### 代码样例

| 目录 | 内容 | 状态 |
|---|---|---|
| [code/executor](code/executor) | Executor 最小可运行 Demo（NATS + UIA） | 可跑通原型 |
| [scripts/gen_index.py](scripts/gen_index.py) | 扫描文档元信息，自动生成索引表 | 可用 |

### 过程与治理

| 文档 | 用途 |
|---|---|
| [MAINTENANCE.md](MAINTENANCE.md) | **维护规范**：文档元信息、状态流转、更新流程、评审清单 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志（按 Keep a Changelog 风格） |
| [ROADMAP.md](ROADMAP.md) | 演进路线（Phase 0 → Phase 4） |
| [GLOSSARY.md](GLOSSARY.md) | 术语表 |

---

## 30 秒理解架构

```
┌─────────────── FACP 联邦协作平面（不做调度） ───────────────┐
│ Registry 注册中心 │ NATS 消息总线 │ FSHub 会话中心 │ Observer │
└───────────────────────────┬──────────────────────────────┘
                            │  结构化信令，不承载模型厂商流量
      ┌─────────────────────┼─────────────────────┐
 Sidecar-Claude       Sidecar-Qoder-intl    Sidecar-Executor
      │                     │                     │
 Claude Desktop         Qoder 国际版          桌面/窗口/文件
```

**三层职责分离（最关键的架构约束）**

| 层 | 只做什么 | 绝不做 |
|---|---|---|
| 协作平面 | 注册、投递、域校验、审计、观测 | 任务规划、路由决策 |
| Sidecar | 单 App 的进程/窗口/会话/协议翻译 | 操作其他 App、通用桌面点击 |
| Executor | 通用桌面原子动作串行执行 | 自主规划任务、主动呼叫其他节点 |

**Agent 本体的唯一约定**：在会话内输出被 ` ```fcp ` 包裹的 `COLLAB_CALL` JSON，Sidecar 嗅探并投递。

---

## 典型端到端链路（真实场景）

```
1. 用户在 Claude Desktop 提出：审查这份 Triton kernel 的内存对齐
2. Claude 判断：我不具备 Triton 源码级审查能力 → 输出 COLLAB_CALL
3. Sidecar-Claude 域校验 → NATS 投递 node.qoder-intl-01
4. Sidecar-Qoder-intl：进程未启动 → 拉起 → 查找 fsid 绑定会话 → 切换 → 注入任务
5. Qoder 完成审查 → REPLY 回总线 → 注入 Claude 会话
6. Claude 判断需要落盘修改 → 向 facp-executor-01 下 steps：打开 VSCode→定位窗口→输入注释
7. Executor 串行执行、逐步截图、返回 step_results
8. 全程无中央调度器；Observer 上画出一条跨三个节点的 Trace
```

---

## 快速开始

```bash
# 1. 阅读顺序（新人 / 自己几个月后回来）
docs/00-overview.md → docs/01-identity-domain.md → docs/02-protocol.md
→ docs/03-sidecar.md → docs/04-executor.md → docs/08-deployment.md

# 2. 跑通 Executor 原型
cd code/executor
pip install -r requirements.txt
cp .env.example .env
python main.py

# 3. 重新生成索引表（改完文档必做）
python scripts/gen_index.py --write
```

---

## 文档写作与维护约定（摘要）

- 每份文档**必须有 YAML front matter**（id / title / version / status / updated / related），否则索引脚本会跳过并告警。
- 状态只能取：`draft` → `review` → `stable` → `deprecated`。
- 任何**协议字段变更**必须同步改 `docs/02-protocol.md` + `CHANGELOG.md` + 相关 Sidecar/Executor 代码，缺一不可。
- 详见 [MAINTENANCE.md](MAINTENANCE.md)。

---

*最近更新：2026-11-07 ｜ 当前迭代：Phase 0（原型验证）*
