# Discord 链接检测机器人

功能：
- ✅ 监控指定频道（**支持多频道**）的新消息
- ✅ 检查消息是否包含链接
- ✅ 无链接消息自动删除并发送提示
- ✅ 管理员/频道主/服务器所有者消息豁免（不会被删除）
- ✅ **审核顺序优化**：优先判定管理员/频道主身份，再检查内容合规性
- ✅ **热更新监听频道**：管理员可通过斜杠命令实时增删监听频道，无需重启
- ✅ **监听列表持久化**：热更新后的频道列表自动落盘，容器重启不丢失
- ✅ **详细日志记录**（保存至本地文件）
- ✅ 每条被监听消息都会上报审计结果（通过/豁免/撤回/失败）
- ✅ **撤回上报优化**：审计摘要卡片与原文/附件分开发送，附件以文件形式还原
- ✅ 支持 `local_config.py` 本地私密配置（避免上传敏感信息）
- ✅ 每日定时播报运行状态与撤回统计（频道或私聊）
- ✅ 支持私聊 `/ping` 命令检测在线与延迟
- ✅ 日志过期自动清理（默认 14 天），下载附件缓存自动清理（默认 7 天）

## 环境变量一览

| 变量 | 必填 | 说明 |
|------|------|------|
| `DISCORD_TOKEN` | ✅ | Bot Token |
| `DISCORD_CHANNEL_ID` | 可选 | 监听频道 ID，逗号分隔多频道；留空监听所有可见频道 |
| `DISCORD_ADMIN_USER_ID` | 推荐 | Bot 管理员用户 ID，可使用热更新命令，也视为审核豁免 |
| `DISCORD_LOG_USER_ID` | 可选 | 接收审计日志私聊的用户 ID |
| `DISCORD_REPORT_CHANNEL_ID` | 可选 | 每日播报目标频道 ID |
| `DISCORD_REPORT_USER_ID` | 可选 | 每日播报目标用户 ID（私聊） |
| `DISCORD_REPORT_TIME` | 可选 | 每日播报时间，格式 HH:MM，默认 09:00 |
| `DISCORD_WATCHED_CHANNELS_FILE` | 可选 | 监听列表持久化路径，默认 `data/watched_channels.json` |
| `DISCORD_PROXY` | 可选 | HTTP 代理地址 |
| `DISCORD_FORCE_IPV4` | 可选 | 强制 IPv4 |
| `DISCORD_TRUST_ENV_PROXY` | 可选 | 信任系统代理环境变量 |

## 准备工作

1. 在 Discord 开发者面板为 Bot 开启 **Message Content Intent**
2. 确保 Bot 在目标频道有 **删除消息权限** 和 **发送消息权限**

## 安装依赖

```bash
pip install -r requirements.txt
```

## 本地运行

### 单频道监听
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_CHANNEL_ID="123456789012345678"
python .\bot1.py
```

### 多频道监听（推荐）
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_CHANNEL_ID="123456789,987654321,555666777"
python .\bot1.py
```

### 启用私聊日志通知
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_CHANNEL_ID="123456789,987654321"
$env:DISCORD_LOG_USER_ID="你的用户ID"
python .\bot1.py
```

### 启用每日定时播报

可播报到频道或私聊（也可以同时设置）：

```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_REPORT_CHANNEL_ID="123456789012345678"
$env:DISCORD_REPORT_TIME="09:00"
python .\bot1.py
```

或播报到私聊：

```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_REPORT_USER_ID="123456789012345678"
$env:DISCORD_REPORT_TIME="09:00"
python .\bot1.py
```

### 监听所有频道
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
python .\bot1.py
```

## 隐私配置（可选）

项目已支持读取 `local_config.py`，并且该文件已加入 Git 忽略，不会提交到仓库。

1. 复制样例文件：
```powershell
Copy-Item .\local_config.example.py .\local_config.py
```

2. 编辑 `local_config.py`，填写各个 `DISCORD_*` 配置项。

3. 运行：
```powershell
python .\bot1.py
```

`bot1.py` 会优先读取 `local_config.py`；若未配置，再读取环境变量。

## Docker 部署

项目已包含 `Dockerfile`、`docker-compose.yml` 和 `.dockerignore`。

### 1Panel / Docker Compose

在 1Panel 中使用 Compose 编排或 `docker compose` 部署即可，不需要暴露端口。

环境变量直接在 1Panel 界面或命令行配置（**不需要**创建 `.env` 文件）。必填项是 `DISCORD_TOKEN`，建议至少再填 `DISCORD_ADMIN_USER_ID`。

数据卷：
- `./logs` → `/app/logs`：Bot 日志
- `./data` → `/app/data`：监听列表持久化 + 附件下载缓存

```bash
docker compose up -d --build
docker compose logs -f
```

## 斜杠命令

### /ping

在 Discord 中私聊 Bot，输入 `/ping`，Bot 会返回：
- `pong!`
- 网关延迟（ms）
- 命令响应耗时（ms）

### /list

**权限**：仅 `DISCORD_ADMIN_USER_ID` 指定的用户可用。

查看当前正在监听的所有频道，每项显示频道名、频道 ID、所在服务器名和服务器 ID。如果监听列表为空，显示"监听所有 Bot 可见频道"。

### /watch_add <频道ID>

**权限**：仅 `DISCORD_ADMIN_USER_ID` 指定的用户可用。

添加一个监听频道。如果频道已在监听列表中，会提示"已在监听列表中"。修改后自动持久化，重启容器不丢失。

### /watch_remove <频道ID>

**权限**：仅 `DISCORD_ADMIN_USER_ID` 指定的用户可用。

移除一个监听频道。如果监听列表变为空，会提示"Bot 将监听所有可见频道"。修改后自动持久化。

## 审核流程

处理每条消息时，按以下顺序判定：

1. **管理员/频道主豁免**：发送者是 `DISCORD_ADMIN_USER_ID`、服务器所有者、Thread 所有者，或拥有管理员/管理消息/管理频道权限的用户 → 直接通过，不检查内容
2. **豁免期通过**：用户在 60 秒内发过含链接的消息 → 直接通过
3. **含链接**：消息文本或 Embed 中包含 URL → 通过，并授予 60 秒豁免期
4. **无链接**：删除消息，审计上报至 `DISCORD_LOG_USER_ID`（如已配置）

## 撤回消息上报

当消息被撤回时，`DISCORD_LOG_USER_ID` 指定的用户会收到：

1. **审计摘要卡片**（Embed）：发送者、位置、链接检测结果、文本长度、附件数量、操作结果
2. **被撤回消息原文**（单独消息）：使用引用样式完整展示，长文本自动分片
3. **图片附件还原**：图片附件以文件形式重新上传到 DM
4. **非图片附件**：展示文件名、大小、原 URL 列表，不下载非图片附件
5. **图片预览兜底**：如果文件还原失败，用 Embed 图片 URL 预览兜底

所有 DM 上报与原内容分开发送，方便管理员直接阅读被撤回内容。

## 文件自动清理

- **日志文件**（`logs/`）：超过 **14 天** 的 `.log` 文件每天自动删除一次
- **附件缓存**（`data/attachments/`）：超过 **7 天** 的下载附件每天自动删除一次

## 如何获取用户 ID？

1. **在 Discord 启用开发者模式**
   - 用户设置 → 高级 → 启用"开发者模式"

2. **右键点击用户头像**
   - 选择"复制用户 ID"

## 故障排查

| 问题 | 解决方案 |
|------|--------|
| Token 无效 | 检查环境变量 `DISCORD_TOKEN` 是否正确 |
| 无法删除消息 | 检查 Bot 权限和 Intent 是否启用 |
| `/list` 不在命令列表 | 新命令同步到 Discord 可能需要几分钟；检查 Bot 启动日志是否显示"已同步斜杠命令" |
| `/list` 提示无权限 | 确认 `DISCORD_ADMIN_USER_ID` 已配置且值为你的 Discord 用户 ID |
| 重启后监听列表丢失 | 确认 `docker-compose.yml` 中 `./data:/app/data` 卷已正确挂载 |
| 多频道不生效 | 确认逗号分隔的频道 ID 格式正确，或使用 `/watch_add` 命令添加 |
| 无法接收私聊日志 | 检查 `DISCORD_LOG_USER_ID` 是否正确，确保该用户允许 Bot 私聊 |
| 私聊日志发送失败 | 检查隐私设置：用户设置 → 隐私与安全 → 允许来自服务器成员的私聊 |
| Docker 代理报错 | 容器内 `127.0.0.1` 指向自身；删除 `DISCORD_PROXY` 直接连接，或用 `172.17.0.1` |
| `Duplicate 'Server' header found` | 关闭代理软件后重试，或在需要时启用 `DISCORD_FORCE_IPV4` |

## 文件说明

- `bot1.py` - 主脚本
- `local_config.py` - 本地私密配置（已忽略提交）
- `local_config.example.py` - 配置样例
- `Dockerfile` - Docker 镜像构建
- `docker-compose.yml` - Docker Compose 编排
- `.env.example` - 环境变量样例
- `.dockerignore` - Docker 构建忽略
- `logs/` - 日志文件目录（自动创建）
- `data/` - 持久化数据 + 附件缓存（Docker 卷挂载）
- `.gitignore` - Git 忽略规则
- `requirements.txt` - Python 依赖
- `README.md` - 本文件
