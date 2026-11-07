---
id: FACP-003
title: Sidecar SDK 开发规范与接口
version: 0.3.0
status: draft
owner: 李富强
updated: 2026-11-07
related: [FACP-001, FACP-002, FACP-004]
---

# Sidecar SDK 开发规范与接口

> Sidecar = 一对一绑定某个桌面 AI 客户端的边车进程，是该 App 在联邦网络中的代理节点。
> **边界**：它只操作**自己绑定的那一个 App**；通用桌面操作（点别的软件、改文件、跑命令）一律交给 [Executor](04-executor.md)。

## 1. 职责清单

| 职责 | 必须 | 说明 |
|---|---|---|
| 节点注册 / 心跳 / 下线 | ✅ | 向 Registry 上报身份报文（FACP-001 §2） |
| NATS 订阅与投递 | ✅ | 订阅 `node.<node_id>`，接收 COLLAB_CALL |
| 信封校验 | ✅ | 按 FACP-002 §6 十步校验，前 7 步在投递前完成 |
| FSID ↔ 本地会话映射 | ✅ | 持久化到本地 SQLite，同步 FSHub |
| App 生命周期 | ✅ | `is_running` / `start` / `bring_to_front` |
| 会话定位与切换 | ✅ | 按 FSID 找到对应会话并切过去 |
| 任务注入 | ✅ | 把 payload 注入目标会话 |
| 输出嗅探 | ✅ | 识别 Agent 在会话内输出的 ````fcp` COLLAB_CALL |
| 回执注入 | ✅ | 收到 REPLY 后写回原会话上下文 |
| 审计事件上报 | ✅ | 跨域消息摘要 + 命中规则 |
| 通用桌面操作 | ❌ | **禁止**，交给 Executor |

## 2. 进程模型建议

```
DesktopApp.exe  ←── (Tier1 本地 API / Tier2 剪贴板 / Tier3 UIA)
      ▲
      │ IPC
Sidecar.exe（单实例，绑定唯一 App + 唯一账号）
      │
      ├─ NATS ──> Mesh
      ├─ HTTP  127.0.0.1:<port> ──> Observer / 调试
      └─ SQLite  本地会话映射 + 日志
```

- **一个 Sidecar 只绑定一个 App 实例、一个账号**。同 App 双账号 = 两个 Sidecar 进程、两个 `node_id`。
- 崩溃不能影响 App 本体：Sidecar 挂了，用户仍能正常使用该 App。
- 启动顺序：App 可后启动；Sidecar 应能在 App 未启动时正常注册（`online=false, app_running=false`）。

## 3. 适配层分级（TransportType）

| 级别 | 方式 | 稳定性 | 风控风险 | 使用建议 |
|---|---|---|---|---|
| **Tier1** | App 官方本地 HTTP API | 高 | 低 | **优先**，作为正式路径 |
| Tier2 | 结构化剪贴板（带 `[FACP:<fsid>]` 标记头）+ 快捷键提交 | 中 | 中 | App 无 API 但有可预期输入框时 |
| Tier3 | Windows UI Automation / Win32 控件定位 | 低（随 UI 改版失效） | 高（易被识别为自动化） | **仅原型验证**，禁止高频 |

### 3.1 Tier 降级与升级策略

- 启动时探测：调 Tier1 探测接口 → 成功则锁定 Tier1 并缓存 30 分钟
- Tier1 连续 3 次失败 → 降级 Tier2（记录告警），不自动降到 Tier3
- Tier3 必须显式在配置中打开 `allow_ui_automation: true`，默认关闭

### 3.2 Tier2 剪贴板消息格式

```
[FACP:<fsid>|<trace_id>|<intent>]
<payload 的 instruction>
[/FACP]
```

接收侧（Agent 本体的提示词）需被告知：以该标记开头的输入来自联邦协作，不是用户输入。

### 3.3 向 Executor 发起调用（含 L2 高危）

Executor 是**独立节点**，Sidecar 只负责投递 `desktop_execute`，不直接操作桌面。载荷字段见 [FACP-002 §4.2](02-protocol.md#42-intent-枚举初始集合)：

| 字段 | 必填 | 说明 |
|---|---|---|
| `instruction` | ✅ | 一句话意图，给人看的，不参与执行逻辑 |
| `risk_level` | ✅ | `normal` / `high`；steps 含 `file_write` 或 `shell_run` 时**必须**为 `high` |
| `require_confirm` | ✅ | 是否要求人工确认后才执行 |
| `session_high_risk_granted` | 条件 | `risk_level=high` 时必填。由 Sidecar 依据 Observer 对该 FSID 的授信结论填写，Executor 不自行判定权限（详见 [FACP-004 §5.2](04-executor.md#52-l2-放行的双开关)） |
| `steps` | ✅ | 动作序列，每步一个动作，结构见 FACP-004 §3.1 |

两条容易踩的坑：

1. **高危时不要省略 `session_high_risk_granted`。** 字段缺失与明确的 `false` 在协议上等价于拒绝，但显式写入能让审计日志区分"调用方忘了"与"明确未授权"。
2. **不要把 `risk_level` 写成 `high` 却只放了 L0/L1 动作。** 这会让 Executor 走双开关路径，在没有全局 `ALLOW_HIGH_RISK` 时白跑一趟被拒。

可运行示例见 [`code/sidecar/example_desktop_call.py`](../code/sidecar/example_desktop_call.py)：先用 `--dry-run` 打印信封核对字段，再去掉该参数实际投递；steps 模板见同目录 `steps_l0.json` / `steps_l1.json` / `steps_l2.json`。

```bash
# 只校验字段，不联网
python code/sidecar/example_desktop_call.py --target facp-executor-01 --dry-run

# 发起 L2 调用（Executor 侧需 ALLOW_HIGH_RISK=true）
python code/sidecar/example_desktop_call.py --target facp-executor-01 \
    --steps code/sidecar/steps_l2.json --high-risk --granted
```

## 4. 会话映射（FSID ↔ App 本地会话）

### 4.1 数据结构（本地 SQLite）

```sql
CREATE TABLE session_map (
  fsid            TEXT PRIMARY KEY,
  local_session_id TEXT NOT NULL,      -- App 内部的 conversation/chat id
  local_title     TEXT,                -- 便于人排查
  bound_at        TEXT NOT NULL,
  last_active_at  TEXT,
  state           TEXT DEFAULT 'active' -- active / archived
);

CREATE TABLE fsid_meta_cache (
  fsid         TEXT PRIMARY KEY,
  domain_policy TEXT,
  user_suspend  INTEGER,
  synced_at     TEXT
);
```

### 4.2 切换会话算法

```
switch_session(fsid):
  1. 查本地 session_map
     ├─ 命中 → 取 local_session_id
     └─ 未命中 → 判定为"新加入协作区"
           ├─ 该 App 允许自动建会话？→ 新建会话，写入映射，回写 FSHub.active_node_ids
           └─ 不允许 → 返回 4007（需用户在 App 内手动建会话后重试）
  2. 若 App 未运行 → start_app()，等待就绪（超时 20s）
  3. 激活窗口（bring_to_front）
  4. 按 local_session_id 定位会话
     ├─ Tier1：API 直接打开该 conversation
     ├─ Tier2：会话列表搜索标题/ID → 快捷键跳转
     └─ Tier3：UIA 在会话列表控件中匹配项 → 点击
  5. 校验：当前活动会话 == 目标会话？否 → 返回 4007
```

> **第 5 步校验是必须的**。没有校验的"切换"等于赌博：切错了会把 A 项目的任务注入到 B 项目的会话里，且事后极难发现。

### 4.3 会话标题规范（提升可定位性）

建议 Sidecar 建会话时用统一标题前缀，降低 Tier2/Tier3 的定位难度：

```
[FACP] <fsid 短码> · <会话标题前 20 字>
例：[FACP] triton-001 · 昆仑芯算子开发
```

## 5. 对外 RPC 接口（本机 HTTP，仅 127.0.0.1）

> 供 Observer、调试工具、健康检查使用；**Mesh 主通道是 NATS**，HTTP 不承载跨节点协作。

| 方法 | 路径 | 说明 | 返回 |
|---|---|---|---|
| GET | `/ping` | 心跳 + 身份摘要 | `{node_id, domain, app_running, transport_type}` |
| GET | `/capabilities` | 能力标签 | `{capabilities: []}` |
| GET | `/health` | 详细健康状态 | `{registry_ok, nats_ok, app_ok, tier, fail_count}` |
| GET | `/sessions` | 本节点已绑定 FSID | `[{fsid, local_session_id, state}]` |
| POST | `/app/start` | 拉起 App | `{ok, pid}` |
| GET | `/app/status` | 进程状态 | `{running, pid, window_title}` |
| POST | `/session/switch` | `{fsid}` | `{ok, local_session_id}` 或错误码 |
| POST | `/session/inject` | `{fsid, payload}` | `{ok, injected_at}` |
| GET | `/session/artifact` | `?fsid=` 读取最新产出摘要 | `{summary, artifact_refs}` |
| POST | `/fsid/bind` | `{fsid, local_session_id}` 手动绑定 | `{ok}` |
| POST | `/fsid/unbind` | `{fsid}` | `{ok}` |
| POST | `/suspend` | `{fsid, suspended}` 本地暂停 | `{ok}` |

> 所有接口需带本机 token（`X-FACP-Token`），防止同机其他程序滥用。

## 6. 错误码

| Code | 名称 | 触发 |
|---|---|---|
| 4001 | `schema_invalid` | 信封 JSON 非法 / 缺必填字段 |
| 4002 | `cross_domain_denied_policy` | FSID 策略为 same-domain-only |
| 4003 | `cross_domain_denied_allowlist` | 节点白名单未开放对方域 |
| 4004 | `depth_exceed` | call_depth 超限 |
| 4005 | `fsid_unknown` | FSID 不存在 / 已归档 |
| 4006 | `app_start_failed` | App 启动失败或超时 |
| 4007 | `session_locate_failed` | 会话定位失败 / 切换后校验不一致 |
| 4008 | `caller_untrusted` | 发起节点不在注册表 / 已下线 |
| 4009 | `intent_unsupported` | 未知 intent |
| 4010 | `payload_too_large` | 信封超 256 KB |
| 4011 | `audit_token_invalid` | 跨域令牌过期/重放 |
| 5001 | `app_api_error` | Tier1 接口调用失败 |
| 5002 | `inject_failed` | 注入后未检测到 Agent 响应 |

## 7. SDK 配置文件

```yaml
# sidecar.yaml
node_id: claude-desktop-01
app_name: claude
edition: intl
security_domain: intl
display_name: Claude Desktop

nats_url: nats://127.0.0.1:4222
registry_url: http://127.0.0.1:8901
fshub_url: http://127.0.0.1:8900

transport_type: native_local_api
allow_ui_automation: false

app_path: "C:\\Users\\<user>\\AppData\\Local\\Programs\\Claude\\Claude.exe"
app_start_timeout_sec: 20

max_call_depth: 5
allowed_domains: ["intl"]
cross_domain_allow_list: []

network_isolation_tag: us-residential-1
local_http_port: 9101
local_token: "<随机生成，写入本机配置>"

inject_rate_limit:
  max_per_min: 6          # 防止短时高频注入触发客户端风控
  min_interval_ms: 800

log:
  dir: ./log
  level: info
  keep_days: 30
```

### 7.1 关键配置说明

| 配置 | 为什么要这个值 |
|---|---|
| `inject_rate_limit` | 高频注入是最容易被客户端/厂商识别为自动化的信号之一，必须限速 |
| `app_start_timeout_sec` | 桌面 App 冷启动可能需要 15s+，超时太短会误判失败 |
| `allow_ui_automation` | 默认 false，把高危路径变成显式选择 |
| `local_token` | 本机 HTTP 接口若裸奔，任何进程都能让 Sidecar 注入消息 |

## 8. 心跳与节点状态

| 状态 | 条件 | 能力寻址是否命中 |
|---|---|---|
| `online` | 30s 内有心跳，App 运行中 | ✅ |
| `idle` | 30s 内有心跳，App 未运行 | ✅（会被先唤醒） |
| `degraded` | 连续失败 ≥ 5 或延迟超阈值 | ❌ |
| `offline` | 90s 无心跳 | ❌ |

心跳报文只发 `node_id` + `status` + 关键指标（不重复发全量身份，减少总线噪音）。

## 9. 实现检查清单（写完一个 Sidecar 自检）

```
[ ] 未启动 App 时也能正常注册为 idle
[ ] 收到 CALL 前完成前 7 步校验，失败必回 REPLY
[ ] 会话切换后有"当前活动会话 == 目标"的断言
[ ] FSID 映射持久化，Sidecar 重启后仍能切回原会话
[ ] 注入内容带来源标记（区分用户输入 vs 联邦协作）
[ ] 未知 intent 一律 rejected，不猜测执行
[ ] 有注入限速
[ ] 崩溃不影响 App 本体
[ ] 本地 HTTP 有 token 保护
[ ] 跨域消息写审计（摘要 + 命中规则）
```

## 10. 待定项

| 问题 | 现状 | 计划 |
|---|---|---|
| 如何稳定读取 App 会话内**最新产出摘要**（闭源无 API） | 未解决 | Phase 1 按 App 逐个验证 Tier2/3 可行性 |
| Tier2 剪贴板方案在 App 有富文本输入时的格式损失 | 未解决 | 先只传纯文本 + 工件引用 |
| App 强制登录态失效时的重连语义 | 未定义 | 增加 `auth_expired` 状态与用户提示 |
