import discord
from discord.ext import commands
import re
import asyncio
import aiohttp
import sys

# --- 关键修复：针对 Windows 平台的异步兼容性处理 ---
if sys.platform == 'win32':
    # 强制使用传统的选择器循环，避免 Windows Proactor 的 WinError 64 错误
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==================== 配置区域 ====================
TOKEN = 'MTQ3MDk1NDY2NjQ4ODc2MjQwMA.G8jJHC.ElSiXImrQjxdp48qZ9yU2tSgD9ybU-jqzitYnA(已更改api)'
PROXY = "http://127.0.0.1:7897"  # 请确保端口正确
TARGET_CHANNEL_ID = 1468099833788370957 
# =================================================
URL_PATTERN = r'(https?://[^\s]+)'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'已成功登录: {bot.user.name}')

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if message.channel.id == TARGET_CHANNEL_ID:
        if message.author.guild_permissions.administrator: return
        if not re.search(URL_PATTERN, message.content):
            try:
                await message.delete()
                await message.channel.send(f"⚠️ {message.author.mention}, 此频道必须包含链接！", delete_after=5)
            except: pass

bot.run(TOKEN)
