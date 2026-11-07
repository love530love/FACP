# CHANGELOG

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [MAINTENANCE.md §3](MAINTENANCE.md)。

分类：`Added` 新增 / `Changed` 变更 / `Deprecated` 弃用 / `Removed` 移除 / `Fixed` 修复 / `Security` 安全。

---

## [Unreleased]

（暂无）

---

## [0.5.0] - 2026-11-07

### Added
- `code/sidecar/example_desktop_call.py`：可运行的 `desktop_execute` 调用示例，含 `--dry-run` 字段自检；`steps_l0/l1/l2.json` 三份模板。
- `docs/03-sidecar.md §3.3`：向 Executor 发起调用（含 L2 高危）的载荷字段说明与两个常见坑。
- `code/sidecar/tests`：20 条用例覆盖信封必填字段、`cross_domain` 推导、高危授权字段、本地自检拦截。
- `file_write` 动作实现（overwrite / create / append，写入统一 LF，回读校验字节数）。
- `shell_run` 动作实现（捕获 stdout/stderr、退出码、超时）。
- `scripts/check_links.py`：站内 Markdown 链接与标题锚点校验，已接入 CI。
- `code/executor/suspend_registry.py`：会话急停状态（本地 JSON，原子写入、mtime 缓存）。
- `scripts/facp_suspend.py`：命令行急停开关（`--suspend` / `--resume` / `--status`）。
- `docs/04-executor.md §4.3`：执行中急停（在途任务）—— 检查点、传导方式与不保证的事。
- 错误码 `4012 session_suspended`（FACP-003 v0.4.0）。

### Changed
- Executor 收到 CALL 的预检增加第 4 步暂停校验；执行循环在每一步之前复查急停，命中则中止后续步骤并回 `status=suspended`。
- CI 的语法检查与测试范围扩展到 `code/sidecar`。

### Fixed
- `docs/02-protocol.md` 中指向 `MAINTENANCE.md` 的相对路径缺少 `../`，链接实际是坏的；已修正并补上 `#3-版本号规则` 锚点（FACP-002 v0.4.1）。
- `scripts/check_links.py` 的围栏解析改为逐行状态机：文档正文里出现过「四个连续反引号」的行内写法，全局正则会把它当成围栏开始，导致后续代码块配对错位、一半标题识别不到。

---

## [0.4.0] - 2026-11-07

> **迁移说明（调用方注意）**：L2 高危动作的放行条件由「仅全局开关」收紧为「全局 + 会话级」。
> 调用方需在 CALL 的 `payload` 中带 `session_high_risk_granted: true`（由 Sidecar 依据 Observer
> 的授信结论填写），否则 `file_write` / `shell_run` 一律返回 `forbidden`，且整个任务在预检阶段
> 被拒绝、不执行任何步骤。这是收紧方向：不会造成越权，只会让未携带该字段的旧调用被拒绝。

### Added
- 建立 FACP 文档项目：分层文档（00–08）、索引脚本、维护规范、术语表、路线图。
- `code/executor` 最小可运行 Demo：NATS 订阅、UIA 动作引擎、高危动作拦截。
- 文档元信息（front matter）与自动索引机制。
- `code/executor/tests`：44 条回归用例，覆盖 L0/L1/L2 分级、双开关语义、路径黑名单、上跳目录、命令黑名单、覆盖保护、整体预检，以及 `file_read` 与 `run_steps` 失败中断。
- `file_read` 动作实现（L0）：文档 §3.1 早已定义、原型此前缺失；现支持 `max_bytes` 截断、`encoding` 可指定，路径黑名单照常生效。
- `SecurityHook.for_session()`：按单次会话派生 hook，落实 §5.2 的会话级授权。

### Changed
- 将原先单篇架构说明拆分为「总览 / 身份域 / 协议 / Sidecar / Executor / Observer / 提示词 / 风险 / 部署」九个专题，按阅读顺序编号。
- Executor 放行 L2 动作由「单一全局开关」改为「全局 + 会话级双开关」（对齐 FACP-004 §5.2）：载荷须带 `session_high_risk_granted=true`，否则一律 `forbidden`。此前只有全局开关，与规范不一致。
- CI `docs-check` 增加 pytest 回归测试步骤。

### Fixed
- `.gitattributes` 统一行尾为 LF，消除 Windows 下 CRLF 换行噪音；`*.ps1/*.bat` 保留 CRLF。
- Release 工作流说明中的相对链接改为绝对链接（GitHub Release 页面不解析仓库相对路径）。

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
