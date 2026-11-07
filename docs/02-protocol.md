---
id: FACP-002
title: 消息协议规范
version: 0.4.2
status: stable
owner: 李富强
updated: 2026-11-07
related: [FACP-001, FACP-003, FACP-004]
---

# 消息协议规范

> 本规范定义节点之间**唯一允许**的通信形式。它同时约束 Sidecar、Executor、FSHub 三方实现，任何字段变更按 [MAINTENANCE §3](../MAINTENANCE.md#3-版本号规则) 走版本评审。

## 1. 设计约束（先立规矩）

1. 只有两类消息：`COLLAB_CALL`（请求）与 `COLLAB_REPLY`（回执）。没有广播、没有闲聊、没有第三方旁听。
2. 信封层**必须**是结构化 JSON；自然语言只能出现在 `payload` 内部。
3. 每条消息**必须**带 `fsid` 与 `trace_id`——没有会话归属的调用一律拒绝。
4. 每条消息**必须**带 `call_depth`；达到上限直接拒绝，不重试。
5. 所有枚举值小写下划线，不用中文字段名。

## 2. 传输层约定

| 项 | 约定 |
|---|---|
| 总线 | NATS，地址 `nats://127.0.0.1:4222`（本机）/ 内网地址（多机） |
| 节点私有主题 | `node.<node_id>`（Sidecar 订阅自己的） |
| 回执主题 | 发起方在 CALL 中通过 NATS `reply` 机制回投，或显式 `reply_subject` |
| 能力广播主题 | `capability.<tag>`（可选，用于能力发现） |
| 审计事件主题 | `audit.cross_domain`（FSHub 订阅） |
| 消息大小上限 | 建议 ≤ 256 KB；超限时用 `artifact_refs` 传引用，不塞正文 |
| 编码 | UTF-8，`ensure_ascii=false` |

## 3. 联邦会话（FSID）

### 3.1 定义
FSID 是**跨 App 协作项目的根标识**。一个 FSID 可以在 N 个 App 里各挂一条原生会话作为协作分支，共享同一个协作上下文信封，但各 App 内部历史互不合并（用户仍在自己熟悉的窗口里看自己的对话）。

### 3.2 FSID 元数据

```json
{
  "fsid": "fs-triton-kernel-dev-001",
  "title": "昆仑芯 Triton 算子开发",
  "domain_policy": "same-domain-only",
  "active_node_ids": ["claude-desktop-01", "qoder-intl-01"],
  "artifact_index": [
    { "art_id": "art-001", "type": "text", "title": "方案初稿", "uri": "fshub://art-001" },
    { "art_id": "art-002", "type": "code", "title": "kernel.py", "uri": "file:///D:/work/kernel.py" }
  ],
  "cross_domain_audit_log": [],
  "user_suspend": false,
  "creator_node_id": "claude-desktop-01",
  "created_at": "2026-11-07T10:12:00+08:00",
  "updated_at": "2026-11-07T11:40:22+08:00"
}
```

| 字段 | 规则 |
|---|---|
| `fsid` | 格式 `fs-<slug>-<seq>`，全局唯一，**永不复用** |
| `domain_policy` | `same-domain-only`（默认）/ `cross-domain-audit` |
| `active_node_ids` | 已挂载该 FSID 的节点 |
| `artifact_index` | 工件索引，只存引用不存大正文 |
| `user_suspend` | `true` 时该会话所有自动协作被拒（返回 `suspended`） |

### 3.3 生命周期

| 阶段 | 触发 | 动作 |
|---|---|---|
| 创建 | 任一 Sidecar 检测到用户新开会话 | 申请 FSID，绑定当前 App 本地会话 |
| 挂载 | 节点收到该 FSID 的 CALL 但本地无绑定 | 新建 App 会话并绑定 FSID |
| 解绑 | 用户操作 / 节点下线 | 移除 `local_session_map` 条目 |
| 归档 | 长期无活动（建议 7 天） | 标记 archived，不再接受 CALL |
| 销毁 | 用户显式删除 | 保留审计日志，元数据软删 |

> **FSID 对人是透明的**：面板只展示 `title`，用户不需要记 ID。

## 4. COLLAB_CALL 报文

```json
{
  "msg_type": "COLLAB_CALL",
  "msg_id": "0f3c1a9e-8b2d-4c71-9a55-2e7d1b0c4f88",
  "trace_id": "tr-7d21c0e4",
  "fsid": "fs-triton-kernel-dev-001",
  "caller_node_id": "claude-desktop-01",
  "caller_domain": "intl",
  "target_node_id": "qoder-intl-01",
  "target_domain": "intl",
  "intent": "code_review",
  "call_depth": 2,
  "max_call_depth": 5,
  "cross_domain": false,
  "audit_token": null,
  "ttl_seconds": 300,
  "created_at": "2026-11-07T11:40:22+08:00",
  "payload": {
    "instruction": "审查 kernel.py 的 shared memory 对齐与 bank conflict 风险",
    "artifact_refs": ["art-002"],
    "acceptance": "输出风险点列表 + 修改建议，不改代码"
  }
}
```

### 4.1 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `msg_type` | ✅ | 固定 `COLLAB_CALL` |
| `msg_id` | ✅ | UUID v4，用于回执关联、去重 |
| `trace_id` | ✅ | 整条调用链共享，贯穿所有跳转 |
| `fsid` | ✅ | 所属联邦会话 |
| `caller_node_id` | ✅ | 发起节点，必须存在于 Registry |
| `caller_domain` | ✅ | 冗余字段，用于目标侧快速校验（防伪造需签名，见 §8） |
| `target_node_id` | ✅ | 指定目标；若为 `"*:<capability>"` 则由注册表解析为具体节点（见 §4.3） |
| `target_domain` | ✅ | 同上，用于网关预检 |
| `intent` | ✅ | 意图枚举，见 §4.2 |
| `call_depth` | ✅ | 当前嵌套层数，发起方 +1 后填入 |
| `max_call_depth` | ✅ | 上限，取全局与两节点配置的最小值 |
| `cross_domain` | ✅ | 是否跨域调用，与 `caller_domain != target_domain` 必须一致 |
| `audit_token` | 条件 | 跨域时必填，由 FSHub 审计钩子签发，一次性 |
| `ttl_seconds` | ✅ | 超时秒数，默认 300，超时返回 `timeout` |
| `payload` | ✅ | 业务载荷，结构由 `intent` 决定 |
| `reply_subject` | 可选 | 显式回执主题；缺省用 NATS `msg.reply` |

### 4.2 intent 枚举（初始集合）

| intent | 目标节点类型 | payload 关键结构 |
|---|---|---|
| `code_review` | LLM 节点 | `instruction`, `artifact_refs`, `acceptance` |
| `document_polish` | LLM 节点 | `instruction`, `artifact_refs` |
| `deep_plan` | LLM 节点 | `instruction`, `constraints` |
| `multimodal_describe` | 多模态节点 | `artifact_refs`(image), `question` |
| `desktop_execute` | Executor | `instruction`, `risk_level`, `require_confirm`, `steps` |
| `session_summary` | 任意节点 | `fsid`, `scope` |

> 新增 intent 必须同步更新本表 + CHANGELOG，并对所有 Sidecar 做兼容确认（未知 intent 一律回 `rejected`，不得猜测执行）。

### 4.3 能力寻址（可选扩展）

`target_node_id` 支持两种形式：

- 具体节点：`qoder-intl-01` —— 确定性投递
- 能力寻址：`*:triton-debug` —— 由 Registry 解析为当前在线的、同域的、负载最低的节点

解析规则：**只在该 FSID 允许的域内解析**；解析失败返回 `no_capable_node`。能力寻址不改变"由发起 Agent 决定要找什么能力"这一原则，只是把"具体选谁"交给注册表。

## 5. COLLAB_REPLY 报文

```json
{
  "msg_type": "COLLAB_REPLY",
  "msg_id": "5b8e2d47-1c33-4a90-b7f6-0d2c9a1e3b55",
  "reply_to": "0f3c1a9e-8b2d-4c71-9a55-2e7d1b0c4f88",
  "trace_id": "tr-7d21c0e4",
  "fsid": "fs-triton-kernel-dev-001",
  "responder_node_id": "qoder-intl-01",
  "responder_domain": "intl",
  "status": "success",
  "error": null,
  "elapsed_ms": 18420,
  "payload": {
    "summary": "发现 3 处 risk：bank conflict 2 处、越界 1 处",
    "artifact_refs": ["art-003"],
    "steps": []
  }
}
```

### 5.1 status 枚举（闭合集合）

| status | 语义 | 是否可重试 |
|---|---|---|
| `success` | 完成 | — |
| `partial` | 部分完成，见 payload | 可，需缩小任务 |
| `rejected` | 目标拒绝执行（能力不匹配 / 未知 intent / 主动拒绝） | 换节点 |
| `forbidden_cross_domain` | 跨域四道闸门未通过 | ❌ 不可重试 |
| `depth_exceed` | 调用深度超限 | ❌ 不可重试 |
| `suspended` | 该 FSID 被用户暂停协作 | ❌ 等用户恢复 |
| `timeout` | 超过 `ttl_seconds` | 可，需加长 TTL |
| `failed` | 执行失败（含 Executor 某步失败） | 可，看 `error` |
| `no_capable_node` | 能力寻址无匹配节点 | 换能力标签 |

> **待补充**：`busy`（目标节点过载，建议换节点或排队）。当前以 `rejected` + `error.reason=busy` 表达，定案后升版本。

### 5.2 error 对象

```json
{
  "code": "4004",
  "reason": "depth_exceed",
  "message": "call_depth 6 > max_call_depth 5",
  "failed_step_idx": null,
  "retryable": false
}
```

错误码表见 [FACP-003 §6](03-sidecar.md#6-错误码)。

## 6. 校验流程（目标节点收到 CALL 后，按序执行）

```
1. 结构校验      msg_type / 必填字段 / JSON Schema           → 4001
2. 身份校验      caller_node_id 是否在 Registry、是否 online  → 4008
3. 会话校验      fsid 是否存在、是否 archived                 → 4005
4. 暂停校验      FSID.user_suspend == true                    → suspended
5. 域校验        §3.2 四道闸门                               → 4002 / 4003
6. 深度校验      call_depth > max_call_depth                 → 4004
7. 能力校验      intent 是否支持、能力标签是否匹配            → rejected
8. TTL 校验      是否已过期                                   → timeout
9. 执行          Sidecar 注入 / Executor 执行 steps（每步前复查急停，见 FACP-004 §4.3）
10. 回执         组装 REPLY，同一 trace_id 返回
```

> **任一步失败必须返回 REPLY**，不允许静默丢弃。静默丢弃会让发起方一直阻塞到 TTL，产生"卡死感"。

## 7. 调用链与死循环防护

### 7.1 trace 传播规则

| 场景 | trace_id | call_depth |
|---|---|---|
| A 发起新任务 | 新生成 | 1 |
| B 收到后呼叫 C | **沿用 A 的** | A 的 +1 |
| B 完成后回执 A | 沿用 | 不变 |

### 7.2 熔断矩阵

| 机制 | 触发 | 行为 |
|---|---|---|
| 深度熔断 | `call_depth > max_call_depth` | 拒绝，终止本次分支 |
| 环检测 | 同一 `trace_id` 内 `caller_node_id` 重复出现 | 记录告警，第二次出现即拒绝（建议实现） |
| 节点熔断 | 连续失败 ≥ 5 次或 P95 延迟超阈值 | Registry 标记 `degraded`，能力寻址跳过它 |
| 会话急停 | `user_suspend=true` | 所有新 CALL 拒绝（4012）；在途任务在下一步前中止（FACP-004 §4.3） |
| 全局急停 | 停止 NATS | 全链路协作停止，各 Agent 退化为单机 |

## 8. 安全要求

1. **审计令牌**：跨域 CALL 的 `audit_token` 由 FSHub 签发，一次性、绑定 `msg_id` + `fsid`，重放即失效。
2. **防伪造**：多机部署时建议对整个信封做 HMAC（节点密钥分发由 Registry 承担），`caller_domain` 等"自述字段"不可单独信任。
3. **大小限制**：信令层拒绝 > 256 KB 的消息；大工件走 `artifact_refs`。
4. **敏感字段**：`account_fingerprint` 不得进入 payload；payload 中禁止明文承载账号密码/token。
5. **审计落库**：跨域消息的 `payload` **摘要（hash）+ 前 200 字** 落 FSHub，完整内容不落库（隐私与体积平衡）。

## 9. 样例：Executor 调用

```json
{
  "msg_type": "COLLAB_CALL",
  "msg_id": "a1b2c3d4-0001",
  "trace_id": "tr-7d21c0e4",
  "fsid": "fs-triton-kernel-dev-001",
  "caller_node_id": "claude-desktop-01",
  "caller_domain": "intl",
  "target_node_id": "facp-executor-01",
  "target_domain": "intl",
  "intent": "desktop_execute",
  "call_depth": 3,
  "max_call_depth": 5,
  "cross_domain": false,
  "ttl_seconds": 600,
  "payload": {
    "instruction": "打开 VSCode 中的 kernel.py，在第 30 行插入对齐注释",
    "risk_level": "normal",
    "require_confirm": false,
    "steps": [
      { "action": "start_process", "path": "C:\\Program Files\\Microsoft VS Code\\Code.exe", "window_title_hint": "kernel.py" },
      { "action": "find_window", "window_title": "kernel.py", "match_mode": "contains" },
      { "action": "activate_window", "window_title": "kernel.py" },
      { "action": "type_text", "window_title": "kernel.py", "text": "// 保证 16B 对齐，避免 shared memory bank conflict" }
    ]
  }
}
```

完整执行语义见 [FACP-004](04-executor.md)。

## 10. 变更记录（协议层）

| 版本 | 变更 | 兼容性 |
|---|---|---|
| 0.4.0 | 新增 `reply_subject`、`ttl_seconds`、能力寻址 `*:capability` | 向后兼容（可选字段） |
| 0.3.0 | `status` 集合新增 `suspended` / `no_capable_node` | 需消费方忽略未知枚举 |
| 0.2.0 | 引入 `fsid`、`trace_id`、`call_depth` 强制字段 | **破坏性**，旧报文全部失效 |
