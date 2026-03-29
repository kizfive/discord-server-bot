# Discord 链接检测机器人

功能：
- ✅ 监控指定频道（**支持多频道**）的新消息
- ✅ 检查消息是否包含链接
- ✅ 无链接消息自动删除并发送提示
- ✅ 管理员/版主消息豁免（不会被删除）
- ✅ **详细日志记录**（保存至本地文件）
- ✅ 每条被监听消息都会上报审计结果（通过/豁免/撤回/失败）
- ✅ 支持 `local_config.py` 本地私密配置（避免上传敏感信息）
- ✅ 每日定时播报运行状态与撤回统计（频道或私聊）
- ✅ 撤回日志完整展示文本与图片附件（不再只显示“[图片]”）
- ✅ 支持私聊 `/ping` 命令检测在线与延迟

## 隐私配置（推荐）

项目已支持读取 `local_config.py`，并且该文件已加入 Git 忽略，不会提交到仓库。

1. 复制样例文件：
```powershell
Copy-Item .\local_config.example.py .\local_config.py
```

2. 编辑 `local_config.py`，填写：
- `DISCORD_TOKEN`
- `DISCORD_CHANNEL_ID`（可选，多频道用逗号分隔）
- `DISCORD_LOG_USER_ID`（可选）
- `DISCORD_REPORT_CHANNEL_ID` / `DISCORD_REPORT_USER_ID`（可选，日报目标）
- `DISCORD_REPORT_TIME`（可选，格式 HH:MM）

3. 运行：
```powershell
python .\bot1.py
```

说明：
- `bot1.py` 会优先读取 `local_config.py`；若未配置，再读取环境变量。

## 新增功能详解

### 多频道支持
可以同时监听多个频道，用逗号分隔：
```
DISCORD_CHANNEL_ID=123456789,987654321,555666777
```

### 详细日志系统

#### 本地日志文件
每次消息处理都会记录到 `logs/bot_YYYYMMDD_HHMMSS.log`：
- 📨 消息内容（前100字符）
- 👤 作者信息（用户名和 ID）
- 📍 服务器和频道信息
- ✅/❌ 规定检查结果
- 🔧 Bot 执行的操作
- ⚠️ 操作结果和失败原因

#### 私聊日志通知（新增）
可以让 Bot 在删除消息时，自动私聊（DM）指定的管理员用户，发送操作摘要。

**优势**：
- ✅ 实时通知管理员
- ✅ 不会在公开频道显示
- ✅ 详细的 Embed 格式日志
- ✅ 包含违规用户、消息内容、操作结果等信息

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

说明：
- 只要消息进入监听范围，Bot 都会向 `DISCORD_LOG_USER_ID` 上报审计结果。
- 上报类型包括：
   - 用户发送了包含链接的消息，已通过并授予豁免期
   - 用户发送了不含链接消息，但为管理员，直接通过
   - 用户发送了不含链接消息，但处于豁免期，直接通过
   - 用户发送了不含链接消息，已撤回（并附完整原文/附件/图片预览）

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

### 私聊命令：/ping

在 Discord 中私聊 Bot，输入 `/ping`，Bot 会返回：
- `pong!`
- 网关延迟（ms）
- 命令响应耗时（ms）

### 监听所有频道
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
python .\bot1.py
```

### 如何获取用户 ID？

1. **在 Discord 启用开发者模式**
   - 用户设置 → 高级 → 启用"开发者模式"

2. **右键点击用户头像**
   - 选择"复制用户 ID"
   - 粘贴到 `DISCORD_LOG_USER_ID` 环境变量

3. **或者在聊天框输入**
   ```
   @用户名#0000
   ```
   - 最后会显示 `<@用户ID>`，复制其中的数字

## 在 Zeabur 上部署

1. **关联 GitHub 仓库**
   - 在 Zeabur Dashboard 上添加项目
   - 连接该 GitHub 仓库

2. **配置环境变量**
   - `DISCORD_TOKEN` = 你的 Bot Token
   - `DISCORD_CHANNEL_ID` = `123456789,987654321` （多频道用逗号分隔，或留空）
   - `DISCORD_LOG_USER_ID` = 你的用户 ID（可选，用于接收删除日志）

3. **查看日志**
   - Zeabur Dashboard 上实时查看运行日志
   - 本地日志文件会保存在 `logs/` 目录
   - 私聊日志会发送到指定用户的 Discord DM

## 日志示例

### 本地文件日志（保存在 logs/ 目录）

```
================================================================================
📨 新消息
  服务器: Your Server
  频道: #general (ID: 123456789012345678)
  作者: username#1234 (ID: 987654321098765432)
  内容: 这是一条测试消息...
  附件: 0 个
  规定检查: ❌ 不合规（无链接）
  操作结果: ✅ 已删除
================================================================================
```

### 私聊日志（DM 消息）

当启用 `DISCORD_LOG_USER_ID` 时，Bot 会发送 Embed 格式的日志消息：

**标题**：🚨 消息删除日志

**内容包括**：
- 👤 违规用户（用户名、ID、头像）
- 📍 位置（服务器名、频道名、频道ID）
- 💬 原消息内容（完整文本，自动分片发送）
- 📎 原附件列表（文件名 + URL）
- 🖼️ 图片附件可视化预览（直接显示图片）
- 🔧 执行的操作（删除原因）
- ✅ 操作结果（成功/失败及失败原因）
- ⏰ 操作时间戳

**示例**：如果违规用户 `alice#1234` 发送了无链接消息，管理员会收到一条 DM，详细记录这次删除操作。

## 故障排查

| 问题 | 解决方案 |
|------|--------|
| Token 无效 | 检查环境变量 `DISCORD_TOKEN` 是否正确 |
| 无法删除消息 | 检查 Bot 权限和 Intent 是否启用 |
| 日志文件过大 | 定期删除 `logs/` 目录中的旧文件 |
| 多频道不生效 | 确认逗号分隔的频道 ID 格式正确 |
| 无法接收私聊日志 | 检查 `DISCORD_LOG_USER_ID` 是否正确，确保该用户允许 Bot 私聊 |
| 私聊日志发送失败 | 检查隐私设置：用户设置 → 隐私与安全 → 允许来自服务器成员的私聊 |
| `Duplicate 'Server' header found` 连接失败 | 通常是本地网络代理/中间层导致；默认已关闭自定义代理读取。若仍失败，关闭代理软件后重试，或切换网络；仅在需要时再启用 `DISCORD_FORCE_IPV4` / `DISCORD_TRUST_ENV_PROXY` |

## 文件说明

- `bot1.py` - 主脚本（含日志和多频道支持）
- `local_config.py` - 本地私密配置（已忽略提交）
- `local_config.example.py` - 配置样例（可提交）
- `logs/` - 日志文件目录（自动创建）
- `.gitignore` - Git 忽略规则
- `requirements.txt` - Python 依赖
- `README.md` - 本文件

