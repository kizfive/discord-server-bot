import os
import re
import logging
import discord
from discord import Forbidden, HTTPException
import aiohttp
import socket
import asyncio
from datetime import datetime, timedelta

# --- 日志系统配置 ---
def setup_logging():
    """设置控制台和文件日志"""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 创建日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 文件日志处理器（记录所有细节）
    file_handler = logging.FileHandler(
        os.path.join(log_dir, f'bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # 主日志记录器
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler]
    )
    
    return logging.getLogger('discord-link-moderator')

logger = setup_logging()

# --- URL 检测正则表达式 ---
URL_PATTERN = re.compile(r'https?://|www\.', re.IGNORECASE)

# --- 从环境变量读取配置（启动时必须设置）---
TOKEN = os.getenv('DISCORD_TOKEN')

# 支持多频道：用逗号分隔，如 "123456789,987654321,555666777"
CHANNEL_IDS_STR = os.getenv('DISCORD_CHANNEL_ID', '0')
CHANNEL_IDS = set()
try:
    for ch_id in CHANNEL_IDS_STR.split(','):
        ch_id = ch_id.strip()
        if ch_id and ch_id != '0':
            CHANNEL_IDS.add(int(ch_id))
except (ValueError, TypeError):
    CHANNEL_IDS = set()

# 日志接收用户 ID（用于私聊发送操作日志）
LOG_USER_ID = None
try:
    log_user = os.getenv('DISCORD_LOG_USER_ID', '')
    if log_user and log_user.strip():
        LOG_USER_ID = int(log_user.strip())
except (ValueError, TypeError):
    LOG_USER_ID = None

logger.info(f'监听的频道 ID 列表: {CHANNEL_IDS if CHANNEL_IDS else "所有频道"}')
if LOG_USER_ID:
    logger.info(f'日志将私聊发送至用户 ID: {LOG_USER_ID}')
else:
    logger.info('未配置日志接收用户，仅保存本地日志文件')

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


# --- 用户豁免期管理（60秒内允许发送任何内容） ---
user_exemptions = {}  # {user_id: {"expires_at": datetime, "channel_ids": set()}}

def is_user_exempt(user_id: int, channel_id: int) -> bool:
    """检查用户是否在豁免期内"""
    if user_id not in user_exemptions:
        return False
    
    exemption = user_exemptions[user_id]
    
    # 检查是否过期
    if datetime.now() > exemption["expires_at"]:
        del user_exemptions[user_id]
        return False
    
    # 检查是否在该频道有豁免
    return channel_id in exemption["channel_ids"]

def grant_exemption(user_id: int, channel_id: int, duration_seconds: int = 60):
    """授予用户豁免期（在指定频道内可以发送任何内容）"""
    expires_at = datetime.now() + timedelta(seconds=duration_seconds)
    
    if user_id not in user_exemptions:
        user_exemptions[user_id] = {
            "expires_at": expires_at,
            "channel_ids": set()
        }
    else:
        # 更新过期时间为更晚的时间
        user_exemptions[user_id]["expires_at"] = max(
            user_exemptions[user_id]["expires_at"],
            expires_at
        )
    
    # 添加频道
    user_exemptions[user_id]["channel_ids"].add(channel_id)
    logger.info(f"✅ 授予用户 {user_id} 在频道 {channel_id} 60秒的豁免期")

def cleanup_expired_exemptions():
    """清理过期的豁免期"""
    now = datetime.now()
    expired_users = [
        uid for uid, data in user_exemptions.items()
        if now > data["expires_at"]
    ]
    for uid in expired_users:
        del user_exemptions[uid]
    if expired_users:
        logger.debug(f"🧹 清理了 {len(expired_users)} 个过期的豁免期")


def message_has_link(message: discord.Message) -> bool:
    """检查消息是否包含链接：仅通过文本内的 URL 判断（不包括纯附件）"""
    # 只检查文本内容中的 URL
    if message.content and URL_PATTERN.search(message.content):
        return True
    # 嵌入内容中的链接
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


def log_message_info(message: discord.Message, has_link: bool, reason: str = None):
    """记录消息处理的详细信息"""
    channel_name = getattr(message.channel, 'name', 'Unknown')
    guild_name = getattr(message.guild, 'name', 'Unknown Guild')
    author_name = f"{message.author.name}#{message.author.discriminator}"
    content_preview = (message.content[:100] + '...') if len(message.content) > 100 else message.content
    
    compliance = "✅ 合规（含链接）" if has_link else "❌ 不合规（无链接）"
    
    log_msg = (
        f"\n{'='*80}\n"
        f"📨 新消息\n"
        f"  服务器: {guild_name}\n"
        f"  频道: #{channel_name} (ID: {message.channel.id})\n"
        f"  作者: {author_name} (ID: {message.author.id})\n"
        f"  内容: {content_preview}\n"
        f"  附件: {len(message.attachments)} 个\n"
        f"  规定检查: {compliance}\n"
    )
    
    if reason:
        log_msg += f"  操作结果: {reason}\n"
    
    log_msg += f"{'='*80}"
    logger.info(log_msg)


async def send_dm_log(message: discord.Message, action: str, result: str):
    """发送删除操作日志到指定用户的 DM"""
    if not LOG_USER_ID:
        return
    
    try:
        log_user = await client.fetch_user(LOG_USER_ID)
        
        embed = discord.Embed(
            title="🚨 消息删除日志",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="👤 违规用户",
            value=f"{message.author.mention}\n{message.author.name}#{message.author.discriminator}\nID: {message.author.id}",
            inline=False
        )
        
        embed.add_field(
            name="📍 位置",
            value=f"服务器: {message.guild.name}\n频道: #{message.channel.name}\n频道ID: {message.channel.id}",
            inline=False
        )
        
        content_preview = (message.content[:200] + '...') if len(message.content) > 200 else message.content
        embed.add_field(
            name="💬 原消息内容",
            value=f"```\n{content_preview}\n```" if content_preview else "（空消息）",
            inline=False
        )
        
        embed.add_field(
            name="🔧 执行的操作",
            value=action,
            inline=False
        )
        
        embed.add_field(
            name="✅ 操作结果",
            value=result,
            inline=False
        )
        
        embed.set_footer(text=f"Zeabur Discord Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await log_user.send(embed=embed)
        logger.info(f"✅ 日志已私聊发送至用户 ID {LOG_USER_ID}")
        
    except Exception as e:
        logger.error(f"❌ 无法发送日志 DM: {e}")


@client.event
async def on_ready():
    logger.info(f"✅ Bot 已登录: {client.user} (ID: {client.user.id})")


@client.event
async def on_message(message: discord.Message):
    """监听消息事件：检测是否含有链接，没有则删除并发送短暂提示"""
    
    # 清理过期的豁免期
    cleanup_expired_exemptions()
    
    # 跳过 Bot 消息
    if message.author.bot:
        return
    
    # 检查是否监听此频道
    if CHANNEL_IDS and message.channel.id not in CHANNEL_IDS:
        return
    
    has_link = message_has_link(message)
    
    # 检查是否为管理员或拥有管理消息权限
    is_admin = (
        hasattr(message.author, 'guild_permissions') and
        (message.author.guild_permissions.administrator or 
         message.author.guild_permissions.manage_messages)
    )
    
    # 检查用户是否在豁免期内
    is_exempt = is_user_exempt(message.author.id, message.channel.id)
    
    # 记录包含链接的消息（直接通过）
    if has_link:
        log_message_info(message, True, "✅ 已通过 - 消息包含有效链接")
        # 授予发送者 60 秒豁免期，允许发送任何内容
        grant_exemption(message.author.id, message.channel.id, duration_seconds=60)
        return
    
    # 记录不含链接但是管理员的消息（直接通过）
    if is_admin:
        log_message_info(message, False, "✅ 已通过 - 发送者为管理员/版主（豁免规则）")
        return
    
    # 如果用户在豁免期内，允许发送任何内容（包括纯文本、图片等）
    if is_exempt:
        log_message_info(message, False, f"✅ 已通过 - 发送者在豁免期内")
        return
    
    # 需要删除的消息
    log_message_info(message, False, "⏳ 正在删除无链接消息...")
    
    try:
        # 删除无链接消息
        await message.delete()
        logger.info(f"✅ 操作成功：消息已删除")
        
        # 发送删除操作日志到指定用户
        await send_dm_log(message, "删除无链接消息", "✅ 消息已成功删除")
        
        # 在频道中发送删除提醒 Embed（仅用户短时间内可见）
        try:
            reminder_embed = discord.Embed(
                title="❌ 消息已删除",
                description="你的消息因为不符合频道规则而被删除。",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            reminder_embed.add_field(
                name="📋 规则",
                value="此频道仅允许发送包含链接的消息。",
                inline=False
            )
            # reminder_embed.add_field(
            #     name="✅ 解决办法",
            #     value="发送一条**包含链接的消息**后，你将获得60秒的豁免期，期间可以发送任何内容（包括纯图片）。",
            #    inline=False
            # )
            reminder_embed.set_footer(text="此提醒将在5秒后自动删除")
            
            # 在频道发送提醒给用户
            tip = await message.channel.send(
                f'{message.author.mention}',
                embed=reminder_embed,
                delete_after=5  # 5秒后自动删除提醒
            )
            logger.info(f"✅ 删除提醒 Embed 已发送")
    
    except Forbidden:
        error_msg = (
            f"❌ 操作失败：Bot 缺少删除消息权限\n"
            f"  频道 ID: {message.channel.id}\n"
            f"  频道名: {getattr(message.channel, 'name', 'Unknown')}\n"
            f"  请确保 Bot 在该频道有 '删除消息' 权限"
        )
        logger.error(error_msg)
        await send_dm_log(message, "尝试删除无链接消息", f"❌ 失败 - Bot 缺少删除消息权限")
    except HTTPException as e:
        error_msg = f"❌ 操作失败：HTTP 错误 - {str(e)}"
        logger.error(error_msg)
        await send_dm_log(message, "尝试删除无链接消息", f"❌ 失败 - HTTP 错误: {str(e)}")


if __name__ == '__main__':
    if not TOKEN:
        error_msg = (
            '❌ 错误：DISCORD_TOKEN 环境变量未设置\n'
            '\n使用方法（支持多频道）：\n'
            '  PowerShell:\n'
            '    $env:DISCORD_TOKEN="your_bot_token"\n'
            '    $env:DISCORD_CHANNEL_ID="123456789,987654321"  # 逗号分隔多频道，或留空监听所有\n'
            '    $env:DISCORD_LOG_USER_ID="用户ID"  # 可选：指定接收删除日志的用户\n'
            '    python .\\bot1.py\n'
            '\n  CMD:\n'
            '    set DISCORD_TOKEN=your_bot_token\n'
            '    set DISCORD_CHANNEL_ID=123456789,987654321\n'
            '    set DISCORD_LOG_USER_ID=用户ID\n'
            '    python bot1.py\n'
            '\n  Linux/Mac:\n'
            '    export DISCORD_TOKEN="your_bot_token"\n'
            '    export DISCORD_CHANNEL_ID="123456789,987654321"\n'
            '    export DISCORD_LOG_USER_ID="用户ID"\n'
            '    python bot1.py'
        )
        print(error_msg)
        logger.error(error_msg)
        raise SystemExit(1)
    
    logger.info("🚀 正在启动 Discord Bot...")
    client.run(TOKEN)

