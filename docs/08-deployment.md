---
id: FACP-008
title: 部署清单与运行环境
version: 0.1.0
status: draft
owner: 李富强
updated: 2026-11-07
related: [FACP-003, FACP-004, FACP-007]
---

# 部署清单与运行环境

> 目标平台：Windows 本机（Executor 必须运行在 Windows，UIA 依赖 Windows API）。
> 协作平面（NATS / FSHub / Registry / Observer）可与 Executor 同机，也可拆到内网另一台机器。

## 1. 组件与端口规划

| 组件 | 端口 | 必需 | 说明 |
|---|---|---|---|
| NATS Server | 4222 | ✅ | 消息总线；单文件可执行，无依赖 |
| FSHub | 8900 | ✅ | FSID 元数据、域策略、审计库（SQLite） |
| Registry | 8901 | ✅ | 节点注册、心跳、能力查询（SQLite） |
| Observer | 8902 | 建议 | Web 观测面板，旁路，挂了不影响协作 |
| Sidecar-* | 9101–91xx | ✅ | 每 App 一个，各自独立端口 |
| Executor | 无入站 | ✅ | 只订阅 NATS，不监听外网 |

> 所有服务默认仅绑定 `127.0.0.1`；跨机部署时才改为内网网卡地址，并加 HMAC/token。

## 2. 目录结构

```
D:\FACP\
├── nats\
│   └── nats-server.exe
├── hub\                  # FSHub
│   └── data\fshub.db
├── registry\
│   └── data\registry.db
├── observer\
├── sidecars\
│   ├── claude\           sidecar.yaml
│   ├── qoder-intl\
│   ├── qoder-cn\
│   ├── workbuddy-intl\
│   ├── workbuddy-cn\
│   ├── doubao-cn\
│   └── doubao-intl\
├── executor\
│   ├── .env
│   ├── log\
│   │   ├── exec.jsonl
│   │   └── snap\
│   └── main.py
└── backup\
```

## 3. 启动顺序（严格）

```
1. nats-server.exe -p 4222
2. FSHub        (8900)
3. Registry     (8901)
4. Observer     (8902，可选)
5. Sidecar(s)   （按需要，可分批）
6. Executor     （必须最后，避免无节点时被误调）
```

原因：Sidecar 注册依赖 Registry；Executor 提前启动会在 FSID 尚未建立时收到无效 CALL。

## 4. 环境准备

### 4.1 Python 侧

```bash
python -m venv .venv
.venv\Scripts\activate
pip install nats-py python-uiautomation pillow psutil python-dotenv fastapi uvicorn
```

> `python-uiautomation` 在部分 Python 版本上需匹配 wheel；若安装失败，检查 Python 版本（建议 3.10–3.12）与 VC++ 运行库。

### 4.2 Executor 运行要求

- **必须管理员权限运行**：否则 UIA 读不到许多窗口控件树。
- 建议单独一条计划任务以最高权限启动，避免每次手动提权。

## 5. Windows 开机自启（两种方案）

### 方案 A：任务计划程序（推荐，简单可靠）

对每个组件建一条任务：

| 配置项 | 值 |
|---|---|
| 触发器 | 「启动时」，延迟 30 秒（等网络与磁盘就绪） |
| 操作 | 启动对应 exe / python |
| 起始位置（重要） | 对应组件目录 |
| 条件 | 取消「仅在使用交流电时」 |
| 设置 | 勾选「不管用户是否登录都运行」；Executor 勾选「使用最高权限运行」 |
| 失败策略 | 勾选「如果任务失败，每 1 分钟重启，最多 3 次」 |

> `起始位置` 漏填是最常见故障：程序起来了但读不到同目录的配置文件。

### 方案 B：NSSM 封装为 Windows 服务

适合长期托管、需要统一的启停/日志重定向：

```powershell
nssm install FACP-NATS     D:\FACP\nats\nats-server.exe "-p 4222"
nssm install FACP-FSHub    python.exe "D:\FACP\hub\main.py"
nssm install FACP-Registry python.exe "D:\FACP\registry\main.py"
nssm install FACP-Executor python.exe "D:\FACP\executor\main.py"

# 设置工作目录
nssm set FACP-Executor AppDirectory D:\FACP\executor
```

Executor 用 NSSM 时需注意：服务默认在 Session 0 运行，**无法操作用户桌面窗口**。
> 这是硬限制：Executor 若要操作可见桌面，**不能用服务方式**，必须用方案 A 且以登录用户身份运行。

## 6. 配置要点

### 6.1 Executor `.env`

```env
NODE_ID=facp-executor-01
NATS_URL=nats://127.0.0.1:4222
ALLOW_HIGH_RISK=false
SNAPSHOT_ROOT=./log/snap
SCREENSHOT_POLICY=on_fail          # always / on_fail / never
SINGLE_TASK_LOCK=true
STEP_TIMEOUT_SEC=10
```

### 6.2 Sidecar `sidecar.yaml`

见 [FACP-003 §7](03-sidecar.md#7-sdk-配置文件)。要点复述：

- `node_id` 含版本后缀（`-cn` / `-intl`）
- `edition` 与 `security_domain` 必须一致
- `allow_ui_automation: false`
- `inject_rate_limit` 必须配

## 7. 验证步骤（部署完必跑）

```bash
# 1 总线连通
nats pub test "hello"
nats sub test

# 2 节点注册
curl http://127.0.0.1:8901/nodes    # 应看到所有 Sidecar 与 Executor

# 3 单 Sidecar 健康
curl -H "X-FACP-Token: <token>" http://127.0.0.1:9101/health

# 4 Executor 最小动作（用文档里的样例报文）
nats pub node.facp-executor-01 '<COLLAB_CALL JSON>'
```

**烟测用例（照抄 FACP-002 §9 的样例，把路径换成 notepad.exe）** 应看到：记事本被拉起、窗口激活、文字输入成功、回执 `status=success`。

## 8. 备份与恢复

| 对象 | 频率 | 方式 |
|---|---|---|
| `fshub.db` / `registry.db` | 每日 | 文件复制到 `D:\FACP\backup\<date>\` |
| Sidecar 配置与 `session_map` | 每周 | 目录打包 |
| Executor 审计日志 | 每周 | 归档，保留 180 天 |
| 截图 | 每日清理 | 保留 7 天 |

**恢复流程：**
1. 停所有组件
2. 还原 `data/` 与各 `sidecar.yaml`
3. 按 §3 顺序启动
4. 检查 `/nodes` 数量是否与备份前一致
5. 抽查 1 个 FSID 能否正确切回原会话（验证 `session_map` 完整）

## 9. 常见故障排查

| 现象 | 排查顺序 |
|---|---|
| Sidecar 注册不上 | Registry 是否启动 → `registry_url` 是否正确 → 有无端口占用 |
| COLLAB_CALL 无响应 | `nats sub node.<id>` 是否收到 → 是否被前置校验拒（看审计） → Agent 是否真输出了 `fcp` 块 |
| Executor 报"窗口未找到" | 窗口标题是否精确（含后缀如 `- 记事本`） → 是否最小化 → UIA 能否枚举该进程窗口 |
| 激活失败但窗口存在 | 目标窗口是否被其他置顶窗口遮挡 → 是否为管理员权限层级问题（UIPI） |
| 切换会话后内容错乱 | `session_map` 是否串号 → 切换后断言是否生效 |
| 开机后全部离线 | 计划任务起始位置是否为空 → 是否以错误用户身份运行 |

## 10. 安全部署注意

1. `.env` 与 `sidecar.yaml` 含 token，**不入版本库**（.gitignore）。
2. 跨机部署时，NATS 启用账号密码与 TLS，FSHub/Registry 加 HMAC。
3. 不要把 8900–8902 暴露到公网，哪怕改了端口。
4. Executor 所在机器应有独立磁盘分区放截图与日志，避免影响系统盘。
5. 定期轮换本机 token 与节点密钥（建议季度）。
