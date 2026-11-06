# GLOSSARY 术语表

> 只收录本项目内有特定含义的词。通用技术词不重复解释。

| 术语 | 英文 | 定义 | 出处 |
|---|---|---|---|
| **FACP** | Federation Agent Collaboration Plane | 本项目的整体名称：联邦 Agent 协作平面 | FACP-000 |
| **联邦（Mesh）** | Agent Mesh | 对等节点网络；节点之间可直接互相调用，无中心调度 | FACP-000 §2 |
| **节点** | Node | 一个 Sidecar 或 Executor 实例，拥有独立身份、安全域、能力标签 | FACP-001 §2 |
| **边车** | Sidecar | 一对一绑定某个桌面 AI 客户端的适配进程，是该 App 在 Mesh 中的代表 | FACP-003 |
| **执行手脚** | Executor | 通用桌面动作执行节点，可被任意 Agent 调用 | FACP-004 |
| **FSID** | Federation Session ID | 联邦会话 ID，跨 App 协作项目的根标识，一个 FSID 可挂载多个 App 内会话 | FACP-002 §3 |
| **安全域** | security_domain | `cn`（国内域）/ `intl`（国际域）/ `local`（执行节点）；决定默认通信边界 | FACP-001 §3 |
| **版本** | edition | `cn` / `intl`，软件发行版本；与安全域强绑定 | FACP-001 §2 |
| **能力标签** | capability tag | 节点自注册的擅长项，如 `triton-debug`、`document_polish` | FACP-001 §2 |
| **能力寻址** | capability addressing | `target_node_id = "*:<capability>"`，由注册表解析具体节点 | FACP-002 §4.3 |
| **协作调用** | COLLAB_CALL | 唯一允许的请求消息类型 | FACP-002 §4 |
| **协作回执** | COLLAB_REPLY | 唯一允许的响应消息类型，status 为闭合枚举 | FACP-002 §5 |
| **意图** | intent | CALL 的业务类型枚举，决定 payload 结构 | FACP-002 §4.2 |
| **调用深度** | call_depth | 嵌套调用层数，超 `max_call_depth` 直接拒绝 | FACP-002 §7 |
| **追踪 ID** | trace_id | 整条调用链共享的标识，贯穿所有跳转 | FACP-002 §7.1 |
| **注入** | inject | Sidecar 把协作任务写入 App 的目标会话 | FACP-003 §4 |
| **嗅探** | sniff | Sidecar 从 App 会话输出中识别 `fcp` 结构化指令 | FACP-003 §1 |
| **适配级别** | TransportType / Tier | Tier1 官方本地 API / Tier2 结构化剪贴板 / Tier3 UI 自动化 | FACP-003 §3 |
| **会话映射** | session_map | `fsid ↔ App 本地会话 ID` 的对应关系，持久化在本地 SQLite | FACP-003 §4 |
| **步骤** | steps | Executor 的原子动作数组，串行执行，每步必须指定窗口 | FACP-004 §3 |
| **高危动作** | L2 action | `file_write` / `shell_run`，默认禁止，需双开关放行 | FACP-004 §5 |
| **人工确认** | require_confirm | 执行前推送到 Observer 等待用户点确认 | FACP-004 §5.4 |
| **刹车** | brake | 五层急停机制：全局 / 会话 / 节点 / 执行 / 单条 | FACP-007 §5 |
| **观测面板** | Observer | 只观测、只开关、不调度的本地 Web 面板 | FACP-005 |
| **审计钩子** | audit hook | 跨域消息落库前的检查点，做摘要与关键词拦截 | FACP-001 §3.2 |
| **域策略** | domain_policy | FSID 级设置：`same-domain-only` / `cross-domain-audit` | FACP-002 §3.2 |
| **网络隔离标签** | network_isolation_tag | 与 VPS/代理分组对应的标识，用于风控溯源 | FACP-001 §6 |
| **身份指纹** | account_fingerprint | 账号标识的哈希，用于区分同版本多账号，禁止存明文 | FACP-001 §2 |
| **冻结** | freeze | 协议文档进入 `stable`，字段变更需变更评审 | MAINTENANCE §2 |
