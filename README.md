# Discord 链接检测机器人

功能：
- ✅ 监控指定频道（**支持多频道**）的新消息
- ✅ 检查消息是否包含链接
- ✅ 无链接消息自动删除并发送提示
- ✅ 管理员/版主消息豁免（不会被删除）
- ✅ **详细日志记录**（保存至本地文件）

## 新增功能详解

### 多频道支持
可以同时监听多个频道，用逗号分隔：
```
DISCORD_CHANNEL_ID=123456789,987654321,555666777
```

### 详细日志系统
每次消息处理都会记录：
- 📨 消息内容（前100字符）
- 👤 作者信息（用户名和 ID）
- 📍 服务器和频道信息
- ✅/❌ 规定检查结果
- 🔧 Bot 执行的操作
- ⚠️ 操作结果和失败原因

**日志文件位置**：`logs/bot_YYYYMMDD_HHMMSS.log`

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

### 监听所有频道
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
python .\bot1.py
```

## 在 Zeabur 上部署

1. **关联 GitHub 仓库**
   - 在 Zeabur Dashboard 上添加项目
   - 连接该 GitHub 仓库

2. **配置环境变量**
   - `DISCORD_TOKEN` = 你的 Bot Token
   - `DISCORD_CHANNEL_ID` = `123456789,987654321` （多频道用逗号分隔，或留空）

3. **查看日志**
   - Zeabur Dashboard 上实时查看运行日志
   - 本地日志文件会保存在 `logs/` 目录

## 日志示例

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

## 故障排查

| 问题 | 解决方案 |
|------|--------|
| Token 无效 | 检查环境变量 `DISCORD_TOKEN` 是否正确 |
| 无法删除消息 | 检查 Bot 权限和 Intent 是否启用 |
| 日志文件过大 | 定期删除 `logs/` 目录中的旧文件 |
| 多频道不生效 | 确认逗号分隔的频道 ID 格式正确 |

## 文件说明

- `bot1.py` - 主脚本（含日志和多频道支持）
- `logs/` - 日志文件目录（自动创建）
- `.gitignore` - Git 忽略规则
- `requirements.txt` - Python 依赖
- `README.md` - 本文件

