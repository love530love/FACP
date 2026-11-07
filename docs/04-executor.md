---
id: FACP-004
title: Executor 执行引擎（手脚）规范
version: 0.3.0
status: draft
owner: 李富强
updated: 2026-11-07
related: [FACP-002, FACP-007]
---

# Executor 执行引擎（手脚）规范

> 代号 `facp-executor-01`。这是整套系统**唯一能真正动用户电脑**的组件，也是风险最高的组件。
> 一句话定位：**Agent 出脑子，Executor 出手脚，人保留刹车。**

## 1. 定位与边界

| | Sidecar | Executor |
|---|---|---|
| 服务对象 | 唯一绑定的那个 App | 全网任意节点 |
| 能力范围 | 进程、窗口、会话、注入 | 任意窗口、任意程序、文件、命令 |
| 是否被 Agent 主动调用 | 是（作为该 App 的代表） | 是（作为工具节点） |
| 安全等级 | 中 | **高（默认锁死高危）** |

**三条硬边界：**

1. **不规划**：只执行传入的 `steps`，不推断"用户大概想干什么"。
2. **不外呼**：不发起任何 COLLAB_CALL（防止 Executor 自己变成调度器，形成递归）。
3. **不猜**：窗口/控件定位不到就失败返回，绝不"找最像的那个"点下去。

## 2. 节点注册

```json
{
  "node_id": "facp-executor-01",
  "app_name": "facp-executor",
  "edition": "local",
  "display_name": "FACP 执行手脚",
  "security_domain": "local",
  "capabilities": ["desktop_gui_execute", "file_op", "shell_run", "window_manage"],
  "transport_type": "native_local_api",
  "allowed_domains": ["cn", "intl"],
  "cross_domain_allow_list": ["cn", "intl"],
  "max_call_depth": 5,
  "network_isolation_tag": "host-local"
}
```

> 注意：Executor 声明可服务两域，但**调用方仍需通过自身域校验**——Executor 不豁免 FSID 的域策略。也就是说，`same-domain-only` 的会话里，CN 节点调 Executor 依然受限（见 §6 校验顺序）。

## 3. 动作集（原子步骤）

所有动作在 `payload.steps[]` 中串行声明，**一步一个动作，不做隐式组合**。

### 3.1 动作 Schema

```ts
type DesktopAction =
  | { action: "start_process"; path: string; args?: string[]; cwd?: string; window_title_hint?: string; wait_sec?: number }
  | { action: "find_window"; window_title: string; match_mode?: "exact" | "contains"; timeout_sec?: number }
  | { action: "activate_window"; window_title: string; match_mode?: "exact" | "contains" }
  | { action: "focus_control"; window_title: string; control_name?: string; control_type?: string }
  | { action: "type_text"; window_title: string; text: string; send_enter?: boolean; clear_first?: boolean }
  | { action: "hotkey"; keys: string[]; window_title?: string }        // ["ctrl","s"] / ["alt","tab"]
  | { action: "click"; window_title: string; control_name?: string; x?: number; y?: number }
  | { action: "screenshot"; window_title?: string; save_path?: string }
  | { action: "file_read"; path: string; encoding?: string }
  | { action: "file_write"; path: string; content: string; mode?: "overwrite" | "append" }
  | { action: "shell_run"; command: string; cwd?: string; timeout_sec?: number }
```

### 3.2 每个动作的前置与失败语义

| 动作 | 前置要求 | 失败条件 |
|---|---|---|
| `start_process` | `path` 存在 | 进程启动失败 / 超时未出窗口（若给了 hint） |
| `find_window` | — | 超时内未匹配到窗口 |
| `activate_window` | 窗口存在 | 激活后 1s 内 `GetForegroundWindow` 不是目标 |
| `focus_control` | 窗口存在、控件可按名/类型定位 | 控件不存在 |
| `type_text` | 目标窗口已在前台 | 前台不是目标窗口 / 输入后无内容变化（可检测） |
| `hotkey` | — | — |
| `click` | `control_name` 或 `(x,y)` 二选一 | 两者都缺 → 直接失败（不允许盲目点击） |
| `screenshot` | — | 保存失败 |
| `file_read` | 路径存在、非黑名单 | 不存在 / 无权限 |
| `file_write` | 通过高危校验（§5） | 拦截 / 无权限 |
| `shell_run` | 通过高危校验（§5） | 拦截 / 非零退出码 |

### 3.3 为什么强制"每步带窗口标识"

`type_text` 不打目标窗口，就等于往当前焦点窗口盲打。用户切了一下窗口，文字就打到微信里去了。**这是这类系统最常见的事故形态。**

## 4. 执行语义

```
run_steps(steps):
  results = []
  for idx, step in steps:
      risk, reason = SecurityCheck(step)          # §5，先于执行
      if risk: return fail(idx, reason, snapshot)

      if step.action == "activate_window" or "type_text" or "focus_control":
          assert_window_matches(step.window_title)   # 执行前再校验一次

      r = execute(step)
      results.append(r)
      if not r.ok:
          return { status: "failed", failed_step_idx: idx, step_results: results, snapshot: snap() }

      if step.action in ("click", "type_text", "hotkey", "start_process"):
          verify_effect(step)        # 轻量效果校验，见 §4.1

  return { status: "success", step_results: results, snapshot: snap() }
```

### 4.1 效果校验（verify_effect）

| 动作 | 校验方式 |
|---|---|
| `type_text` | 对可读控件比对文本；不可读则跳过（记录 `verified: false`） |
| `click` | 若给了预期结果（可选字段 `expect`），校验窗口标题/控件状态变化 |
| `start_process` | 校验进程句柄存活 |
| `hotkey` | 无校验（记录即可） |

> 不要求 100% 可校验，但**必须显式标出哪些步骤是未校验的**，让上层 Agent 知道结果的可信度。

### 4.2 硬性执行约束

- **串行**，不允许并行执行 steps（并发操作同一桌面必然打架）。
- **单实例互斥**：一台机器同一时刻只允许一个 Executor 任务在执行；其他 CALL 返回 `rejected(reason=busy)`。
- **超时**：单步默认 10s，整任务受 CALL 的 `ttl_seconds` 约束。
- **截图策略**：失败必截图；成功时按 `screenshot_policy`（`always` / `on_fail` / `never`）执行，默认 `on_fail`。

### 4.3 执行中急停（在途任务）

FACP-002 §5.1 的 `suspended` 只覆盖「拒绝新的 CALL」。但一个任务跑起来可能持续十几秒到几分钟，中途用户改主意了、或者发现它正在往错误的地方点，**已经开始的步骤序列也必须能停下来**。这一节定义那个通道。

**信号源**：`FSID.user_suspend`（FACP-002 §3.1 的会话元数据），不新增消息类型。

**传导方式**：本地状态文件，而不是 NATS 控制消息。

FACP-002 §1 把消息类型钉死为 `COLLAB_CALL` / `COLLAB_REPLY` 两类，加第三类等于动协议地基；而 Executor 与 Sidecar 本就同机（单节点模型的前提），一个 JSON 文件足够：

```json
{
  "fs-demo-001": { "suspended": true, "updated_at": "2026-11-07T19:51:53+08:00", "reason": "发现它在乱点" }
}
```

- 路径：`%LOCALAPPDATA%\FACP\suspend.json`（Linux 为 `$XDG_STATE_HOME/facp/suspend.json`），可用 `FACP_SUSPEND_FILE` 覆盖。
- 写入方：Sidecar 收到 `POST /suspend`（FACP-003 §5）时写入；也可以由 [scripts/facp_suspend.py](../scripts/facp_suspend.py) 直接写。
- 读取方：Executor。原子替换写入（先写 `.tmp` 再 `os.replace`），读取按 mtime 缓存，每个检查点不会真去打一次磁盘。

**检查点**：两处。

| 时机 | 结果 |
|---|---|
| 收到 CALL 的预检阶段（FACP-002 §6 第 4 步） | 直接回 `status=suspended`，一步都不执行 |
| **每一步执行前** | 停止后续步骤，返回 `status=suspended` + `error.code=4012`，`failed_step_idx` 指向被拦下的那一步 |

检查点放在「执行前」而不是「执行后」，是因为急停的语义是**不再发起新动作**：已经做完的步骤照常计入 `step_results`，调用方据此知道停在哪、已经造成了什么影响。

**不保证的事**：单步一旦开始就不会被打断（比如一个 10 秒的超时等待）。急停只在步与步之间生效。要打断正在进行的单步，只能靠该动作自己的 `timeout_sec`——这是刻意取舍：半途打断一个已发出的 UIA 点击，比让它跑完更容易留下不一致的界面状态。

**回执示例**：

```json
{
  "status": "suspended",
  "payload": { "failed_step_idx": 2, "step_results": [ ...前两步... ] },
  "error": { "code": "4012", "reason": "session_suspended",
             "message": "第 2 步执行前收到会话急停，已停止后续动作",
             "failed_step_idx": 2, "retryable": false }
}
```

## 5. 安全层（本规范的核心）

### 5.1 三级风险分级

| 级别 | 动作 | 默认策略 |
|---|---|---|
| L0 只读 | `find_window` / `screenshot` / `file_read` | 允许 |
| L1 常规写 | `start_process` / `activate_window` / `focus_control` / `type_text` / `hotkey` / `click` | 允许（受窗口校验约束） |
| L2 高危 | `file_write` / `shell_run` | **默认禁止**，需双开关 |

### 5.2 L2 放行的双开关

1. 全局：`.env` 中 `ALLOW_HIGH_RISK=true`
2. 会话级：CALL 的 `payload.risk_level == "high"` 且 FSID 在 Observer 上被授予「高危执行权限」

两者同时满足才执行；否则返回 `forbidden`。

> **实现约定**：Executor 不自行判定 FSID 权限（它没有 Observer 的授信视图）。第二条由
> Sidecar 依据 Observer 的授信结论收敛成一个布尔字段 `payload.session_high_risk_granted`，
> 随 CALL 一起送达；`ALLOW_HIGH_RISK=false` 或该字段缺失/为 `false` 时，一切 L2 动作返回
> `forbidden`，且不执行任何步骤（预检阶段即整体拒绝）。

### 5.3 路径与命令黑名单（默认）

```python
BLACKLIST_PATH_PREFIX = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\ProgramData",
    r"C:\Users\*\AppData\Roaming\Microsoft",
]
SHELL_DENY_PATTERNS = [
    r"rm\s+-rf", r"del\s+/f", r"format\s+", r"diskpart",
    r"reg\s+delete", r"regedit", r"shutdown", r"bcdedit",
    r"netsh\s+firewall", r"sc\s+delete",
]
```

> 黑名单是**最后一道**，不是唯一一道。真正的防线是：Agent 不该有能力生成"删库"级别的 steps——这靠提示词约束 + 上层意图审查。

### 5.4 人工确认（require_confirm）

`payload.require_confirm == true` 时，Executor 在执行前把 steps 摘要推给 Observer，等待用户点击「执行 / 取消」，超时（默认 120s）视为取消。

建议对以下场景**强制** `require_confirm=true`（可由 FSHub 侧策略注入）：

- 任何 `file_write` 覆盖已存在文件
- 任何 `shell_run`
- steps 数量 > 8
- 目标窗口标题包含"设置 / 钱包 / 支付 / 提交"等关键词

### 5.5 审计

每一步落一条记录：

```json
{
  "trace_id": "tr-7d21c0e4",
  "fsid": "fs-triton-kernel-dev-001",
  "caller_node_id": "claude-desktop-01",
  "step_idx": 3,
  "action": "type_text",
  "window_title": "kernel.py",
  "payload_digest": "sha256:...",
  "ok": true,
  "verified": false,
  "elapsed_ms": 412,
  "snapshot": "D:/FACP/executor/log/snap/tr-7d21c0e4_step3.png",
  "ts": "2026-11-07T11:41:03+08:00"
}
```

> 审计记录里 `payload_digest` 而不是明文，避免日志泄露敏感内容；截图保留天数可配置。

## 6. 收到 CALL 的校验顺序

```
1. 信封结构               → 4001
2. caller 在注册表         → 4008
3. fsid 存在且未归档       → 4005
4. fsid.user_suspend      → suspended
5. 域：按调用方域策略     → 4002 / 4003   （Executor 不豁免）
6. call_depth             → 4004
7. intent == desktop_execute → rejected
8. steps 非空且每个 action 合法 → rejected
9. 逐条 L2 高危预检        → forbidden
10. 单实例互斥锁            → rejected(busy)
11. require_confirm?       → 等待人工
12. 执行
```

## 7. 回执格式

```json
{
  "msg_type": "COLLAB_REPLY",
  "reply_to": "a1b2c3d4-0001",
  "trace_id": "tr-7d21c0e4",
  "fsid": "fs-triton-kernel-dev-001",
  "responder_node_id": "facp-executor-01",
  "responder_domain": "local",
  "status": "failed",
  "elapsed_ms": 6200,
  "payload": {
    "failed_step_idx": 2,
    "step_results": [
      { "step_idx": 0, "action": "start_process", "ok": true,  "verified": true,  "window_handle": "0x1A2B" },
      { "step_idx": 1, "action": "find_window",   "ok": true,  "verified": true,  "window_handle": "0x1A2B" },
      { "step_idx": 2, "action": "activate_window","ok": false, "verified": false, "msg": "激活后前台仍为 'Claude'，目标 'kernel.py' 未取得焦点" }
    ],
    "snapshot_path": "D:/FACP/executor/log/snap/tr-7d21c0e4_fail_step2.png"
  },
  "error": { "code": "5002", "reason": "step_failed", "message": "activate_window 失败", "retryable": true }
}
```

## 8. 技术选型

| 能力 | 首选 | 备选 | 理由 |
|---|---|---|---|
| 窗口/控件定位 | **Windows UI Automation (UIA)** | Win32 `EnumWindows` + 标题匹配 | UIA 可按控件名/类型定位，不依赖像素坐标，抗分辨率变化 |
| 输入 | UIA `SendKeys` / `SendInput` | — | 后者更快但易丢字符，前者更稳 |
| 截图 | `PIL.ImageGrab` | `mss`（更快） | 简单可靠 |
| 进程管理 | `subprocess` + `psutil` | win32process | psutil 便于判断存活 |
| 语言/框架 | Python（原型） → Rust/C#（产品化） | — | 原型求快；产品化求 UIA 稳定与打包体积 |

> **不推荐**像素级图像识别作为主路径：桌面缩放、主题、字体一变就失效，且无法给出有意义的失败原因。

## 9. 与其他组件的交互

- **与 Sidecar**：无直接交互；Sidecar 不会调用 Executor（避免 App 适配器获得通用执行权）。
- **与 FSHub**：上报审计事件（`audit.executor_step`）。
- **与 Observer**：接收人工确认指令；上报当前执行状态与截图。
- **与 Agent**：仅通过 COLLAB_CALL/REPLY。

## 10. 检查清单

```
[ ] 默认 ALLOW_HIGH_RISK=false，且 .env 未提交到仓库
[ ] type_text / focus_control / click 执行前校验前台窗口
[ ] 未给 control_name 也未有 (x,y) 的 click 被拒绝
[ ] 失败必截图，且截图路径可追溯 trace_id + step_idx
[ ] 单实例互斥锁生效（并发 CALL 返回 busy）
[ ] 黑名单路径与命令生效，并有单测覆盖
[ ] 审计每步落库，payload 只存 digest
[ ] Executor 代码中不存在任何调用其他节点的逻辑
[ ] 日志与截图有保留天数与清理任务
```

## 11. 已知风险（详见 FACP-007）

| 风险 | 说明 |
|---|---|
| 焦点竞争 | 用户同时操作电脑时，前台窗口可能在 Executor 校验通过后被抢走 |
| UIA 兼容性 | 部分自绘 UI（Electron 某些控件、游戏）UIA 树不完整，只有像素可点 |
| 权限 | 需管理员权限才能读到部分窗口控件，但高权限本身放大风险 |
| 误操作不可逆 | `file_write` 覆盖、`shell_run` 删除类命令，一旦执行无法回滚 |
