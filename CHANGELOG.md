# CHANGELOG

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [MAINTENANCE.md §3](MAINTENANCE.md)。

分类：`Added` 新增 / `Changed` 变更 / `Deprecated` 弃用 / `Removed` 移除 / `Fixed` 修复 / `Security` 安全。

---

## [Unreleased]

### Added
- 建立 FACP 文档项目：分层文档（00–08）、索引脚本、维护规范、术语表、路线图。
- `code/executor` 最小可运行 Demo：NATS 订阅、UIA 动作引擎、高危动作拦截。
- 文档元信息（front matter）与自动索引机制。

### Changed
- 将原先单篇架构说明拆分为「总览 / 身份域 / 协议 / Sidecar / Executor / Observer / 提示词 / 风险 / 部署」九个专题，按阅读顺序编号。

### Security
- 明确 Executor 默认 `ALLOW_HIGH_RISK=false`，文件写入 / shell 执行需显式放行。
- 明确 CN / INTL 跨域为会话级授权，且必须经审计钩子。

---

## [0.3.0] - 2026-11-07

### Added
- **FSID（联邦会话 ID）模型**：一个协作项目可挂载多个 App 内原生会话，上下文按信封接力。
- **安全域模型**：`cn` / `intl` 双域，节点默认仅同域通信。
- **Observer 观测面板**定位：只观测、只人工开关，绝不调度。
- **Executor（执行手脚）**：通用桌面动作节点，可被任意 Agent 节点调用。
- 调用深度熔断（`max_call_depth` 默认 5）、消息 TTL、会话级急停（`user_suspend`）。

### Changed
- 由"中心化调度器 + Worker"演进为**对等 Mesh**：调度权下沉到每个 Agent 本体。
- Sidecar 职责收敛：从"什么都能干"收敛为"单 App 适配 + 协议翻译"，通用桌面操作剥离给 Executor。

### Fixed
- 修正早期把"住宅 IP VPS"等同于"防封号方案"的表述：明确 IP 只是变量之一，时区/语言/指纹/行为节奏同样决定风控结果。

---

## [0.2.0] - 2026-11-06

### Added
- 异构多厂商 Agent 协作的两种范式：中心化适配网关 / 对等联邦。
- 能力契约（Capability Contract）概念：输入输出 Schema 与底层模型解耦。
- 桌面程序形态的进程模型建议：UI 进程 / 调度进程 / Adapter 子进程 / 浏览器服务分离。

### Changed
- 明确模型厂商流量与 Mesh 信令流量必须分离。

---

## [0.1.0] - 2026-11-06

### Added
- 初始构想：多个桌面 AI 客户端互通的可行性讨论、Sidecar 边车思路、跨 App 会话定位需求。
