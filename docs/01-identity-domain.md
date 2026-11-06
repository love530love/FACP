---
id: FACP-001
title: 身份模型与安全域规范
version: 0.2.0
status: stable
owner: 李富强
updated: 2026-11-07
related: [FACP-000, FACP-002, FACP-003]
---

# 身份模型与安全域规范

> 本规范解决一个具体问题：**Qoder / WorkBuddy / 豆包 / Claude 都有国内版与国际版，账号、会话、后端、网络要求完全不同。接入时如果只按"软件名"区分节点，必然串会话、串域、串风控。**
> 结论：**版本是第一分类维度，不是附注。**

## 1. 三条身份铁律

1. **版本即身份**：`qoder-cn` 与 `qoder-intl` 是两个节点，能力标签可以相同，身份永不合并。
2. **账号即身份**：同版本多账号并行（如两套豆包国际版账号）= 多个节点，各自独立 `account_fingerprint`。
3. **域即边界**：节点的 `security_domain` 决定它默认能和谁说话，与它擅长什么无关。

## 2. Node 身份元模型（注册报文）

```json
{
  "node_id": "qoder-intl-01",
  "app_name": "qoder",
  "edition": "intl",
  "display_name": "Qoder 国际版",
  "security_domain": "intl",
  "account_fingerprint": "sha256:9f2a...c41d",
  "capabilities": ["code-analyze", "triton-debug", "code-review"],
  "network_isolation_tag": "us-residential-group-2",
  "transport_type": "native_local_api",
  "local_session_map": { "fs-triton-kernel-dev-001": "conv_9a3f" },
  "allowed_domains": ["intl"],
  "cross_domain_allow_list": [],
  "max_call_depth": 5,
  "online": true,
  "last_heartbeat": "2026-11-07T10:32:11+08:00"
}
```

### 2.1 字段规则

| 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|
| `node_id` | string | ✅ | 全局唯一，建议 `<app>-<edition>-<seq>`，如 `doubao-intl-02` |
| `app_name` | enum | ✅ | `claude` / `qoder` / `workbuddy` / `doubao` / `codex` / `facp-executor` |
| `edition` | enum | ✅ | `cn` / `intl` / `local`（Executor 为 `local`） |
| `security_domain` | enum | ✅ | `cn` / `intl`，**必须与 edition 一致**（`local` 节点可声明可接入域） |
| `account_fingerprint` | string | ✅ | 账号标识的哈希，**严禁存明文账号/邮箱**；用于区分同版本多账号 |
| `capabilities` | string[] | ✅ | 能力标签，小写 kebab-case，供其他节点查询择优 |
| `network_isolation_tag` | string | ✅ | 网络隔离分组，与 VPS / 代理分组一一对应，用于风控追溯 |
| `transport_type` | enum | ✅ | `native_local_api` / `structured_clipboard` / `ui_automation`（见 FACP-003 §5） |
| `local_session_map` | object | ✅ | `fsid → App 内部会话 ID`，可空 `{}` |
| `allowed_domains` | string[] | ✅ | 默认为 `[自身域]` |
| `cross_domain_allow_list` | string[] | ✅ | 默认 `[]`，仅由用户在 Observer 手动添加 |
| `max_call_depth` | int | ✅ | 默认 5，节点可下调不可上调超全局上限 |

### 2.2 域归属表

| 节点 | security_domain | 说明 |
|---|---|---|
| `claude-desktop-*` | `intl` | 国际域，模型流量走独立隔离出口 |
| `qoder-intl-*` | `intl` | Qoder 国际版 |
| `qoder-cn-*` | `cn` | Qoder 国内版 |
| `workbuddy-intl-*` | `intl` | WorkBuddy 国际版 |
| `workbuddy-cn-*` | `cn` | WorkBuddy 国内版 |
| `doubao-intl-*` | `intl` | 豆包国际版 |
| `doubao-cn-*` | `cn` | 豆包国内版 |
| `codex-*` | `intl` | Codex Desktop |
| `facp-executor-*` | `local` | 通用执行手脚，可服务两域（仍受 FSID 策略约束） |

## 3. 安全域规则

### 3.1 默认行为

```
节点收到 COLLAB_CALL
  ├─ caller_domain == target_domain  → 同域，进入能力/深度校验
  └─ caller_domain != target_domain  → 跨域，进入四道闸门（§3.2）
```

### 3.2 跨域放行的四个必要条件（**全部满足**）

| # | 条件 | 校验方 |
|---|---|---|
| 1 | 该 FSID 的 `domain_policy == cross-domain-audit` | FSHub / 目标 Sidecar |
| 2 | 发起节点 `cross_domain_allow_list` 包含目标域 | 发起侧 Sidecar 预检 + 目标侧复核 |
| 3 | 目标节点 `cross_domain_allow_list` 包含发起域 | 目标侧 Sidecar |
| 4 | 消息经审计钩子落库（payload 摘要 + 命中规则） | FSHub 审计库 |

任一不满足 → 返回 `COLLAB_REPLY(status=forbidden_cross_domain)`，并写拒绝日志。

> **跨域不是节点永久打通，是会话级临时授权。** 关闭 FT 会话的跨域开关，立即切断后续所有跨域投递。

### 3.3 为什么必须会话级而不是全局级

用户可以同时存在多个 FSID 并行推进：

| FSID | 域策略 | 成员 | 用途 |
|---|---|---|---|
| `fs-triton-dev-001` | `same-domain-only` | Claude(intl) + Qoder(intl) | 海外方案与源码审查 |
| `fs-gov-doc-002` | `same-domain-only` | 豆包(cn) + WorkBuddy(cn) | 国内交付文档 |
| `fs-bridge-003` | `cross-domain-audit` | Qoder(cn) → Qoder(intl) | 国内需求整理 → 国际侧实现，全程留痕 |

全局打通会让 A、B 两个本应隔离的项目瞬间串味。

## 4. Agent 侧的身份自觉（第一道防线）

底层校验是兜底；**让 Agent 自己知道边界**才是第一道防线。每个 Agent 的系统提示词必须注入：

| 注入项 | 作用 |
|---|---|
| `node_id` / `edition` / `security_domain` | 让它知道自己是谁 |
| `domain_policy` | 让它知道本会话能不能跨域 |
| `peer_catalog` | 让它知道能找谁（已按域过滤） |

效果：Agent 在生成 `COLLAB_CALL` 前就会自我约束，不会持续产出必然被拒的非法跨域调用（否则会出现"请求 → 被拒 → 重试"的体验灾难）。

提示词模板见 [FACP-006](06-prompts.md) §2。

## 5. 可见性要求（人不能靠猜）

Observer 必须做到一眼分清：

- 节点按域分栏：🟦 `intl` / 🟩 `cn`
- 同软件 CN / INTL **强制两个独立卡片**，禁止折叠合并
- FSID 卡片标注 `[同域仅允许]` / `[跨域审计开启]`
- 唤醒节点前弹窗明确版本：`即将唤起 Qoder 国际版` / `Qoder 国内版`
- 调用链上跨域连线用**红色虚线**，标注「跨域｜已审计」

## 6. 合规与风控对齐

身份域与网络隔离必须**保持一致**，否则成为风控漏洞：

| 域 | 模型厂商流量出口 | 要求 |
|---|---|---|
| `intl` | 预先分配的国际隔离出口（分组见 `network_isolation_tag`） | Claude / Qoder-intl 建议各自独立分组，避免一个账号出事连带全灭 |
| `cn` | 国内正常链路，**不套国际代理** | 避免国内版被识别为异常来源 |

**Mesh 信令与模型流量分离**：NATS 只传协作信封、工件摘要、审计事件；各 App 访问自家后端（Anthropic / 各家国内服务）的流量由 App 自身网络栈控制，FACP 不代理、不转发模型 API 请求。

> 反例（必须避免）：为了让节点"能上网"，把全局系统代理一开，所有 App 流量一起走同一个出口 → 身份域隔离在信令层成立、在网络层崩塌。

## 7. 多账号扩展

`account_fingerprint` 使以下场景自然成立：

- 同软件 + 同版本 + 两个账号 → 两个节点（`doubao-intl-01` / `doubao-intl-02`）
- 同软件 + 不同版本 → 两个节点且不同域
- 同一机器上同时运行 CN 与 INTL 两个窗口 → 各自独立 Sidecar

注册表对同 `app_name` 的节点做**分组展示但不合并**，Agent 查询能力时可以看到候选列表并自行选择（选择依据可以是负载、历史评分、账号剩余额度）。

## 8. 反例清单（评审时优先检查）

| 反例 | 后果 |
|---|---|
| 只用 `app_name` 建节点，不区分 edition | 跨版本误唤醒、会话串号、合规越界 |
| `security_domain` 与 `edition` 不一致 | 校验逻辑自相矛盾 |
| 存明文账号邮箱做标识 | 隐私泄露 |
| 全局一键打通 CN/INTL | 隔离体系失效 |
| 跨域只靠底层拦截，Agent 不知边界 | 大量无效调用与重试 |
| FSID 同域策略下混挂两域节点 | 人分不清、Agent 分不清 |
| 未记录 `network_isolation_tag` | 出事后无法定位是哪个出口被污染 |
