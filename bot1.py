import os
import re
import logging
import discord
from discord import Forbidden, HTTPException
import aiohttp
import socket
import asyncio

# --- URL 检测正则表达式 ---
URL_PATTERN = re.compile(r'https?://|www\.', re.IGNORECASE)

# --- 从环境变量读取配置（启动时必须设置）---
TOKEN = os.getenv('DISCORD_TOKEN')
try:
    CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
except (ValueError, TypeError):
    CHANNEL_ID = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord-link-moderator')

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)

# 强制使用 IPv4，避免 Windows 在 IPv6 上发生连接超时；启用 trust_env 以读取代理环境变量
try:
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    _aiohttp_session = aiohttp.ClientSession(trust_env=True, connector=connector)
    try:
        client.http.session = _aiohttp_session
    except Exception:
        try:
            client.http._session = _aiohttp_session
        except Exception:
            pass
except Exception:
    _aiohttp_session = None


def message_has_link(message: discord.Message) -> bool:
    """检查消息是否包含链接：通过文本内的 URL、附件、或嵌入内容中的链接"""
    if message.content and URL_PATTERN.search(message.content):
        return True
    if message.attachments:
        return True
    for emb in message.embeds:
        try:
            parts = []
            if getattr(emb, 'title', None):
                parts.append(emb.title)
            if getattr(emb, 'description', None):
                parts.append(emb.description)
            if getattr(emb, 'url', None):
                parts.append(str(emb.url))
            combined = ' '.join(parts)
            if combined and URL_PATTERN.search(combined):
                return True
        except Exception:
            continue
    return False


@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user} (id={client.user.id})')


@client.event
async def on_message(message: discord.Message):
    """监听消息事件：检测是否含有链接，没有则删除并发送短暂提示"""
    if message.author.bot:
        return
    if CHANNEL_ID and message.channel.id != CHANNEL_ID:
        return
    if message_has_link(message):
        return
    
    try:
        # 删除无链接消息
        await message.delete()
        logger.info(f'Deleted message from {message.author} in #{message.channel} — no link')
        
        # 发送临时提示消息（5秒后自动删除）
        try:
            tip = await message.channel.send(
                f'{message.author.mention} 此频道仅允许发送包含链接的消息，请勿闲聊。'
            )
            # 5秒后删除提示
            await asyncio.sleep(5)
            await tip.delete()
        except Exception as e:
            logger.warning(f'Failed to send or delete tip message: {e}')
    
    except Forbidden:
        logger.warning('Missing permission to delete messages in channel %s', getattr(message.channel, 'id', None))
    except HTTPException as e:
        logger.error('Failed to delete message: %s', e)


if __name__ == '__main__':
    if not TOKEN:
        print('❌ 错误：DISCORD_TOKEN 环境变量未设置')
        print('\n使用方法：')
        print('  PowerShell:')
        print('    $env:DISCORD_TOKEN="your_bot_token"')
        print('    $env:DISCORD_CHANNEL_ID="123456789012345678"')
        print('    python .\\bot1.py')
        print('\n  CMD:')
        print('    set DISCORD_TOKEN=your_bot_token')
        print('    set DISCORD_CHANNEL_ID=123456789012345678')
        print('    python bot1.py')
        print('\n  Linux/Mac:')
        print('    export DISCORD_TOKEN="your_bot_token"')
        print('    export DISCORD_CHANNEL_ID="123456789012345678"')
        print('    python bot1.py')
        raise SystemExit(1)
    client.run(TOKEN)
