# Discord 链接检测机器人

功能：
- 监控指定频道的新消息
- 若消息中没有链接（或附件/嵌入含链接），则自动删除该消息
- 删除后短暂发送提示（5秒内自动删除）："此频道仅允许发送包含链接的消息，请勿闲聊"

## 安全性说明

- ✅ **环境变量方式**：敏感信息（Token、频道 ID）通过环境变量传递，不存储在代码中
- ✅ **適合云部署**：可直接在 Zeabur、Vercel、Heroku 等平台配置环境变量
- ✅ **Git 安全**：所有配置文件都在 `.gitignore` 中，不会泄露

## 准备工作

1. 在 Discord 开发者面板为 Bot 开启 **Message Content Intent**
2. 确保 Bot 在目标频道有 **删除消息权限** 和 **发送消息权限**

## 安装依赖

```bash
pip install -r requirements.txt
```

## 本地运行

使用 PowerShell：
```powershell
$env:DISCORD_TOKEN="your_bot_token_here"
$env:DISCORD_CHANNEL_ID="123456789012345678"
python .\bot1.py
```

使用 CMD：
```cmd
set DISCORD_TOKEN=your_bot_token_here
set DISCORD_CHANNEL_ID=123456789012345678
python bot1.py
```

使用 Linux/Mac：
```bash
export DISCORD_TOKEN="your_bot_token_here"
export DISCORD_CHANNEL_ID="123456789012345678"
python bot1.py
```

## 在 Zeabur 上部署

1. **关联 GitHub 仓库**
   - 在 Zeabur Dashboard 上添加项目
   - 连接你的 GitHub 账户并选择该仓库

2. **配置环境变量**
   - 在 Zeabur 的「Service 设置」→「环境变量」中添加：
     - `DISCORD_TOKEN` = 你的 Bot Token
     - `DISCORD_CHANNEL_ID` = 要监控的频道 ID
   - 保存后 Zeabur 会自动重启服务

3. **查看日志**
   - 在 Zeabur Dashboard 上可实时查看 Bot 运行日志

## 文件说明

- `bot1.py` - 主脚本
- `.gitignore` - Git 忽略规则（保护敏感文件）
- `requirements.txt` - Python 依赖
- `README.md` - 本文件

## 故障排查

- 若 Token 无效，检查环境变量 `DISCORD_TOKEN` 是否正确
- 若无法删除消息，检查 Bot 权限和 Intent 是否启用
- 在 Zeabur 上查看实时日志确认运行状态
