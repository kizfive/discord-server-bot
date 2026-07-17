import os
import re
import io
import json
import logging
import discord
from discord import Forbidden, HTTPException
from discord import app_commands
import aiohttp
import socket
import asyncio
from datetime import datetime, timedelta

try:
    import local_config
except Exception:
    local_config = None

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


def get_config_value(key: str, default=None):
    """优先读取 local_config.py，其次读取环境变量。"""
    if local_config is not None and hasattr(local_config, key):
        return getattr(local_config, key)
    return os.getenv(key, default)


def parse_int(value, default=None):
    """将配置值安全转换为整数。"""
    try:
        if value is None:
            return default
        value_str = str(value).strip()
        if not value_str:
            return default
        return int(value_str)
    except (ValueError, TypeError):
        return default


def parse_channel_ids(value) -> set:
    """解析逗号分隔的频道 ID。"""
    channel_ids = set()
    if value is None:
        return channel_ids
    for ch_id in str(value).split(','):
        parsed = parse_int(ch_id, default=None)
        if parsed and parsed != 0:
            channel_ids.add(parsed)
    return channel_ids


def load_watched_channel_ids(path: str):
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        channel_ids = data.get('channel_ids', [])
        if not isinstance(channel_ids, list):
            return None
        return {parsed for ch_id in channel_ids if (parsed := parse_int(ch_id, default=None))}
    except Exception as e:
        logger.warning(f'⚠️ 无法读取监听频道持久化文件 {path}: {e}')
        return None


def save_watched_channel_ids(path: str, channel_ids: set):
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'channel_ids': sorted(channel_ids)}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f'⚠️ 无法保存监听频道持久化文件 {path}: {e}')


def parse_report_time(value: str) -> tuple:
    """解析每日播报时间，格式 HH:MM。"""
    default_hour, default_minute = 9, 0
    try:
        raw = str(value).strip()
        match = re.match(r'^(\d{1,2}):(\d{1,2})$', raw)
        if not match:
            return default_hour, default_minute
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        pass
    return default_hour, default_minute


def parse_bool(value, default: bool = False) -> bool:
    """解析布尔配置。"""
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if normalized in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default


def chunk_text(text: str, max_len: int = 1800) -> list:
    """按固定长度切分字符串，避免超过 Discord 消息长度限制。"""
    if not text:
        return []
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


def is_image_attachment(attachment: discord.Attachment) -> bool:
    """判断附件是否为图片。"""
    content_type = (attachment.content_type or '').lower()
    if content_type.startswith('image/'):
        return True
    filename = (attachment.filename or '').lower()
    return filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'))


def is_configured_admin(user_id: int) -> bool:
    return ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID


def is_authorized_interaction(interaction: discord.Interaction) -> bool:
    return is_configured_admin(interaction.user.id)


def is_message_moderator(message: discord.Message) -> bool:
    if is_configured_admin(message.author.id):
        return True
    if message.guild and message.guild.owner_id == message.author.id:
        return True
    if getattr(message.channel, 'owner_id', None) == message.author.id:
        return True
    permissions = getattr(message.author, 'guild_permissions', None)
    return bool(
        permissions and
        (permissions.administrator or permissions.manage_messages or permissions.manage_channels)
    )


def save_current_watched_channels():
    save_watched_channel_ids(WATCHED_CHANNELS_FILE, CHANNEL_IDS)


def add_watched_channel(channel_id: int):
    CHANNEL_IDS.add(channel_id)
    save_current_watched_channels()


def remove_watched_channel(channel_id: int):
    CHANNEL_IDS.remove(channel_id)
    save_current_watched_channels()


def describe_channel(channel) -> str:
    channel_id = getattr(channel, 'id', 'Unknown')
    channel_name = getattr(channel, 'name', str(channel_id))
    guild = getattr(channel, 'guild', None)
    guild_name = getattr(guild, 'name', '未知服务器') if guild else '未知服务器'
    guild_id = getattr(guild, 'id', 'Unknown') if guild else 'Unknown'
    return f"#{channel_name} | 频道ID: {channel_id} | 服务器: {guild_name} ({guild_id})"


async def get_channel_description(channel_id: int) -> str:
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            channel = None
    if channel is None:
        return f"未知频道 | 频道ID: {channel_id} | 服务器: 未知/不可访问"
    return describe_channel(channel)


async def build_watched_channel_list() -> str:
    if not CHANNEL_IDS:
        return "当前监听：所有 Bot 可见频道（监听列表为空）"
    descriptions = [await get_channel_description(channel_id) for channel_id in sorted(CHANNEL_IDS)]
    return "当前监听频道：\n" + "\n".join(f"- {desc}" for desc in descriptions)


async def respond_unauthorized(interaction: discord.Interaction):
    await interaction.response.send_message('你没有权限使用这个命令。', ephemeral=True)

# --- URL 检测正则表达式 ---
URL_PATTERN = re.compile(r'https?://|www\.', re.IGNORECASE)

# --- 从环境变量读取配置（启动时必须设置）---
TOKEN = get_config_value('DISCORD_TOKEN')

# 支持多频道：用逗号分隔，如 "123456789,987654321,555666777"
CHANNEL_IDS_STR = get_config_value('DISCORD_CHANNEL_ID', '0')
WATCHED_CHANNELS_FILE = str(get_config_value('DISCORD_WATCHED_CHANNELS_FILE', 'data/watched_channels.json'))
PERSISTED_CHANNEL_IDS = load_watched_channel_ids(WATCHED_CHANNELS_FILE)
CHANNEL_IDS = PERSISTED_CHANNEL_IDS if PERSISTED_CHANNEL_IDS is not None else parse_channel_ids(CHANNEL_IDS_STR)

# 日志接收用户 ID（用于私聊发送操作日志）
LOG_USER_ID = parse_int(get_config_value('DISCORD_LOG_USER_ID', ''), default=None)

# Bot 管理员用户 ID（用于热更新监听频道，也视为审核管理员）
ADMIN_USER_ID = parse_int(get_config_value('DISCORD_ADMIN_USER_ID', ''), default=None)

# 每日播报配置：可指定频道或用户（二选一也可同时设置）
REPORT_CHANNEL_ID = parse_int(get_config_value('DISCORD_REPORT_CHANNEL_ID', ''), default=None)
REPORT_USER_ID = parse_int(get_config_value('DISCORD_REPORT_USER_ID', ''), default=None)
REPORT_TIME_RAW = str(get_config_value('DISCORD_REPORT_TIME', '09:00'))
REPORT_HOUR, REPORT_MINUTE = parse_report_time(REPORT_TIME_RAW)
DISCORD_PROXY = get_config_value('DISCORD_PROXY', None)

logger.info(f'监听的频道 ID 列表: {CHANNEL_IDS if CHANNEL_IDS else "所有频道"}')
logger.info(f'监听频道持久化文件: {WATCHED_CHANNELS_FILE}')
if LOG_USER_ID:
    logger.info(f'日志将私聊发送至用户 ID: {LOG_USER_ID}')
else:
    logger.info('未配置日志接收用户，仅保存本地日志文件')
if ADMIN_USER_ID:
    logger.info(f'Bot 管理员用户 ID: {ADMIN_USER_ID}')
else:
    logger.info('未配置 Bot 管理员用户 ID（DISCORD_ADMIN_USER_ID），频道热更新命令不可用')
if REPORT_CHANNEL_ID or REPORT_USER_ID:
    logger.info(
        f'每日播报已启用: 时间={REPORT_HOUR:02d}:{REPORT_MINUTE:02d}, '
        f'频道ID={REPORT_CHANNEL_ID}, 用户ID={REPORT_USER_ID}'
    )
else:
    logger.info('未配置每日播报目标（DISCORD_REPORT_CHANNEL_ID / DISCORD_REPORT_USER_ID）')

if DISCORD_PROXY:
    logger.info(f'已配置 Discord API 与 WebSocket 代理: {DISCORD_PROXY}')
else:
    logger.info('未配置代理，将使用直连')

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents, proxy=DISCORD_PROXY)
tree = app_commands.CommandTree(client)

startup_time = datetime.now()
daily_stats = {
    'date': datetime.now().date(),
    'checked': 0,
    'deleted': 0,
    'allowed_link': 0,
    'allowed_admin': 0,
    'allowed_exempt': 0,
    'errors': 0,
    'exemption_granted': 0,
}
total_deleted = 0
daily_report_task = None
slash_command_synced = False
EXEMPTION_SECONDS = 60


# --- 用户豁免期管理（60秒内允许发送任何内容） ---
user_exemptions = {}  # {user_id: {"expires_at": datetime, "channel_ids": set()}}
_exemption_lock = asyncio.Lock()  # 保护豁免期字典的并发访问

async def is_user_exempt(user_id: int, channel_id: int) -> bool:
    """检查用户是否在豁免期内（线程安全）"""
    async with _exemption_lock:
        if user_id not in user_exemptions:
            return False

        exemption = user_exemptions[user_id]

        # 检查是否过期
        if datetime.now() > exemption["expires_at"]:
            del user_exemptions[user_id]
            return False

        # 检查是否在该频道有豁免
        return channel_id in exemption["channel_ids"]

async def grant_exemption(user_id: int, channel_id: int, duration_seconds: int = 60):
    """授予用户豁免期（在指定频道内可以发送任何内容）"""
    expires_at = datetime.now() + timedelta(seconds=duration_seconds)

    async with _exemption_lock:
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

    logger.info(f"✅ 授予用户 {user_id} 在频道 {channel_id} {duration_seconds}秒的豁免期")

async def cleanup_expired_exemptions():
    """清理过期的豁免期（线程安全）"""
    now = datetime.now()
    async with _exemption_lock:
        expired_users = [
            uid for uid, data in user_exemptions.items()
            if now > data["expires_at"]
        ]
        for uid in expired_users:
            try:
                del user_exemptions[uid]
            except KeyError:
                pass  # 其他协程可能已经删除了该条目
    if expired_users:
        logger.debug(f"🧹 清理了 {len(expired_users)} 个过期的豁免期")


async def get_exemption_remaining_seconds(user_id: int, channel_id: int) -> int:
    """返回用户在频道中的剩余豁免秒数。"""
    async with _exemption_lock:
        exemption = user_exemptions.get(user_id)
        if not exemption:
            return 0
        if channel_id not in exemption.get("channel_ids", set()):
            return 0
        remaining = int((exemption["expires_at"] - datetime.now()).total_seconds())
    return max(remaining, 0)


def ensure_daily_stats_date():
    """跨天时重置当日统计。"""
    today = datetime.now().date()
    if daily_stats['date'] == today:
        return
    daily_stats.update({
        'date': today,
        'checked': 0,
        'deleted': 0,
        'allowed_link': 0,
        'allowed_admin': 0,
        'allowed_exempt': 0,
        'errors': 0,
        'exemption_granted': 0,
    })


def get_next_report_time(now: datetime = None) -> datetime:
    """计算下一次日报发送时间（本地时区）。"""
    current = now or datetime.now()
    next_run = current.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
    if next_run <= current:
        next_run += timedelta(days=1)
    return next_run


async def send_daily_report(reason: str = '定时播报'):
    """发送每日状态报告到指定频道或私聊。"""
    if not REPORT_CHANNEL_ID and not REPORT_USER_ID:
        return

    ensure_daily_stats_date()

    target = None
    target_name = 'Unknown'

    if REPORT_CHANNEL_ID:
        target = client.get_channel(REPORT_CHANNEL_ID)
        if target is None:
            try:
                target = await client.fetch_channel(REPORT_CHANNEL_ID)
            except Exception as e:
                logger.warning(f'⚠️ 无法获取日报频道 {REPORT_CHANNEL_ID}: {e}')
        if target is not None:
            target_name = f'频道 #{getattr(target, "name", REPORT_CHANNEL_ID)}'

    if target is None and REPORT_USER_ID:
        try:
            target = await client.fetch_user(REPORT_USER_ID)
            target_name = f'用户 {REPORT_USER_ID} 私聊'
        except Exception as e:
            logger.warning(f'⚠️ 无法获取日报用户 {REPORT_USER_ID}: {e}')

    if target is None:
        logger.warning('⚠️ 日报目标无效，跳过本次播报')
        return

    uptime = datetime.now() - startup_time
    status_text = '✅ 正常运行' if client.is_ready() else '❌ 异常'

    embed = discord.Embed(
        title='📊 Discord 频道守护日报',
        description=f'触发方式: {reason}',
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.add_field(name='🤖 运行状态', value=status_text, inline=False)
    embed.add_field(name='⏱️ 运行时长', value=str(uptime).split('.')[0], inline=True)
    embed.add_field(name='📅 统计日期', value=str(daily_stats['date']), inline=True)
    embed.add_field(name='👀 当日检查消息数', value=str(daily_stats['checked']), inline=True)
    embed.add_field(name='🗑️ 当日撤回消息数', value=str(daily_stats['deleted']), inline=True)
    embed.add_field(name='✅ 含链接通过', value=str(daily_stats['allowed_link']), inline=True)
    embed.add_field(name='🛡️ 管理员豁免通过', value=str(daily_stats['allowed_admin']), inline=True)
    embed.add_field(name='⏳ 豁免期通过', value=str(daily_stats['allowed_exempt']), inline=True)
    embed.add_field(name='🎟️ 当日发放豁免次数', value=str(daily_stats['exemption_granted']), inline=True)
    embed.add_field(name='⚠️ 当日错误次数', value=str(daily_stats['errors']), inline=True)
    embed.add_field(name='📦 累计撤回总数', value=str(total_deleted), inline=True)
    embed.set_footer(text='discord-link-moderator')

    await target.send(embed=embed)
    logger.info(f'✅ 日报已发送到 {target_name}')


async def cleanup_old_files_loop():
    """后台循环：每天清理 logs/ 中超过 14 天的日志文件。"""
    await client.wait_until_ready()
    log_dir = 'logs'
    retention_days = 14
    while not client.is_closed():
        try:
            now = datetime.now()
            count = 0
            if os.path.isdir(log_dir):
                for filename in os.listdir(log_dir):
                    if not filename.endswith('.log'):
                        continue
                    filepath = os.path.join(log_dir, filename)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if (now - mtime).days >= retention_days:
                            os.remove(filepath)
                            count += 1
                    except OSError:
                        pass
            if count:
                logger.info(f'🧹 已清理 {count} 个超过 {retention_days} 天的日志文件')
        except Exception as e:
            logger.warning(f'⚠️ 日志清理失败: {e}')
        await asyncio.sleep(86400)


async def daily_report_loop():
    """后台循环：每天在指定时间发送状态报告。"""
    await client.wait_until_ready()
    while not client.is_closed():
        if not REPORT_CHANNEL_ID and not REPORT_USER_ID:
            await asyncio.sleep(300)
            continue

        next_run = get_next_report_time()
        seconds_to_wait = max((next_run - datetime.now()).total_seconds(), 1)
        logger.info(
            f'⏰ 下次日报时间: {next_run.strftime("%Y-%m-%d %H:%M:%S")} '
            f'(约 {int(seconds_to_wait)} 秒后)'
        )
        await asyncio.sleep(seconds_to_wait)

        try:
            await send_daily_report(reason='每日定时')
        except Exception as e:
            daily_stats['errors'] += 1
            logger.error(f'❌ 日报发送失败: {e}')


def message_has_link(message: discord.Message) -> bool:
    """检查消息是否包含链接：通过文本内容和嵌入内容判断"""
    # 检查消息文本中的 URL
    if message.content and URL_PATTERN.search(message.content):
        return True

    # 检查嵌入内容中的链接
    for emb in message.embeds:
        try:
            parts = []
            if getattr(emb, 'title', None):
                parts.append(emb.title)
            if getattr(emb, 'description', None):
                parts.append(emb.description)
            if getattr(emb, 'url', None):
                parts.append(str(emb.url))
            # 检查 embed 字段中的链接
            for field in getattr(emb, 'fields', []):
                if getattr(field, 'name', None):
                    parts.append(field.name)
                if getattr(field, 'value', None):
                    parts.append(field.value)
            # 检查 embed footer
            footer = getattr(emb, 'footer', None)
            if footer and getattr(footer, 'text', None):
                parts.append(footer.text)
            # 检查 embed author
            author = getattr(emb, 'author', None)
            if author:
                if getattr(author, 'name', None):
                    parts.append(author.name)
                if getattr(author, 'url', None):
                    parts.append(str(author.url))

            combined = ' '.join(parts)
            if combined and URL_PATTERN.search(combined):
                return True
        except Exception:
            continue
    return False


def format_author(message: discord.Message) -> str:
    """格式化作者显示名，兼容新旧用户名系统"""
    try:
        return str(message.author)
    except Exception:
        return f"{message.author.name}#{getattr(message.author, 'discriminator', '0000')}"

def log_message_info(message: discord.Message, has_link: bool, reason: str = None):
    """记录消息处理的详细信息"""
    channel_name = getattr(message.channel, 'name', 'Unknown')
    guild_name = getattr(message.guild, 'name', 'Unknown Guild')
    author_name = format_author(message)
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


async def build_attachment_files(attachments: list[discord.Attachment]) -> tuple[list[discord.File], list[str]]:
    files = []
    failed = []
    for attachment in attachments:
        if not is_image_attachment(attachment):
            continue
        try:
            data = await attachment.read(use_cached=True)
            files.append(discord.File(io.BytesIO(data), filename=attachment.filename))
        except Exception as e:
            failed.append(f'{attachment.filename} | {attachment.size} bytes | {attachment.url}')
            logger.warning(f'⚠️ 无法还原附件 {attachment.filename}: {e}')
    return files, failed


async def send_deleted_message_content(log_user: discord.User, message: discord.Message):
    header = (
        f"📝 被撤回消息原文\n"
        f"发送者: {message.author.mention} ({message.author.id})\n"
        f"频道: #{getattr(message.channel, 'name', 'DM')} ({message.channel.id})"
    )
    chunks = chunk_text(message.content, max_len=1700) if message.content else ['（空文本消息）']
    files, failed = await build_attachment_files(message.attachments)

    for idx, chunk in enumerate(chunks, 1):
        chunk_header = header if idx == 1 else f"📝 被撤回消息原文续 ({idx}/{len(chunks)})"
        send_files = files[:10] if idx == 1 and files else None
        await log_user.send(content=f"{chunk_header}\n>>> {chunk}", files=send_files)

    if len(files) > 10:
        for index in range(10, len(files), 10):
            await log_user.send(content='📦 被撤回消息附件还原（续）', files=files[index:index + 10])

    if message.attachments:
        attachment_lines = []
        for index, attachment in enumerate(message.attachments, 1):
            attachment_lines.append(f"{index}. {attachment.filename} | {attachment.size} bytes | {attachment.url}")
        for chunk in chunk_text('\n'.join(attachment_lines), max_len=1800):
            await log_user.send(f"📎 被撤回消息附件列表\n```\n{chunk}\n```")

    if failed:
        for chunk in chunk_text('\n'.join(failed), max_len=1800):
            await log_user.send(f"⚠️ 以下附件未能重新上传，仅保留原链接\n```\n{chunk}\n```")

    if message.attachments and not files:
        for attachment in message.attachments:
            if is_image_attachment(attachment):
                img_embed = discord.Embed(title=f"🖼️ 图片预览：{attachment.filename}", color=discord.Color.red())
                img_embed.set_image(url=attachment.url)
                await log_user.send(embed=img_embed)


async def send_dm_log(message: discord.Message, action: str, result: str):
    """发送消息审计日志到指定用户的 DM。"""
    if not LOG_USER_ID:
        return

    try:
        log_user = await client.fetch_user(LOG_USER_ID)

        has_link = message_has_link(message)

        embed = discord.Embed(
            title="📡 消息审计上报",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

        embed.add_field(
            name="👤 用户",
            value=f"{message.author.mention}\n{format_author(message)}\nID: {message.author.id}",
            inline=False
        )

        guild_name = getattr(message.guild, 'name', 'Direct Message')
        channel_name = getattr(message.channel, 'name', 'DM')
        embed.add_field(
            name="📍 位置",
            value=f"服务器: {guild_name}\n频道: #{channel_name}\n频道ID: {message.channel.id}",
            inline=False
        )

        embed.add_field(
            name="🔎 链接检测",
            value="包含链接" if has_link else "不包含链接",
            inline=True
        )

        content_preview = (message.content[:200] + '...') if len(message.content) > 200 else message.content
        embed.add_field(
            name="💬 原消息内容",
            value=f"```\n{content_preview}\n```" if content_preview else "（空消息）",
            inline=False
        )

        embed.add_field(
            name="📎 附件",
            value=f"{len(message.attachments)} 个" if message.attachments else "无",
            inline=True
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

        embed.set_footer(text=f"Notess's Discord Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await log_user.send(embed=embed)

        # 仅被撤回/删除的消息转发原文和附件（通过的消息只保留在 embed 预览中）
        if ('撤回' in action) or ('删除' in action):
            await send_deleted_message_content(log_user, message)

        logger.info(f"✅ 日志已私聊发送至用户 ID {LOG_USER_ID}")

    except discord.NotFound:
        logger.error(f"❌ 无法发送日志 DM: 用户 {LOG_USER_ID} 不存在")
    except discord.Forbidden:
        logger.error(f"❌ 无法发送日志 DM: Bot 被禁止向用户 {LOG_USER_ID} 发送私聊（用户可能关闭了「允许来自服务器成员的私聊」）")
    except Exception as e:
        logger.error(f"❌ 无法发送日志 DM: {type(e).__name__} - {e}")


@tree.command(name='ping', description='检查机器人运行状态与延迟')
async def ping_command(interaction: discord.Interaction):
    """私聊命令：/ping -> pong + 延迟。"""
    if interaction.guild is not None:
        await interaction.response.send_message('请在私聊中使用 /ping。', ephemeral=True)
        return

    loop = asyncio.get_running_loop()
    start = loop.time()

    await interaction.response.send_message('pong! 正在计算延迟...')

    response_ms = (loop.time() - start) * 1000
    gateway_ms = client.latency * 1000 if client.latency is not None else -1

    await interaction.edit_original_response(
        content=f'pong! 网关延迟: {gateway_ms:.1f}ms | 响应耗时: {response_ms:.1f}ms'
    )


@tree.command(name='list', description='查看当前正在监听的频道')
async def list_command(interaction: discord.Interaction):
    if not is_authorized_interaction(interaction):
        await respond_unauthorized(interaction)
        return

    await interaction.response.send_message(await build_watched_channel_list(), ephemeral=True)


@tree.command(name='watch_add', description='通过频道 ID 添加监听频道')
@app_commands.describe(channel_id='要添加监听的频道 ID')
async def watch_add_command(interaction: discord.Interaction, channel_id: str):
    if not is_authorized_interaction(interaction):
        await respond_unauthorized(interaction)
        return

    parsed_channel_id = parse_int(channel_id, default=None)
    if not parsed_channel_id:
        await interaction.response.send_message('频道 ID 格式不正确。', ephemeral=True)
        return

    already_watched = parsed_channel_id in CHANNEL_IDS
    add_watched_channel(parsed_channel_id)
    description = await get_channel_description(parsed_channel_id)
    watched_text = await build_watched_channel_list()
    status = '已在监听列表中' if already_watched else '已添加监听'
    logger.info(f'✅ {status}: {parsed_channel_id} by {interaction.user.id}')
    await interaction.response.send_message(f'{status}：{description}\n\n{watched_text}', ephemeral=True)


@tree.command(name='watch_remove', description='通过频道 ID 移除监听频道')
@app_commands.describe(channel_id='要移除监听的频道 ID')
async def watch_remove_command(interaction: discord.Interaction, channel_id: str):
    if not is_authorized_interaction(interaction):
        await respond_unauthorized(interaction)
        return

    parsed_channel_id = parse_int(channel_id, default=None)
    if not parsed_channel_id:
        await interaction.response.send_message('频道 ID 格式不正确。', ephemeral=True)
        return

    if parsed_channel_id not in CHANNEL_IDS:
        await interaction.response.send_message(f'该频道 ID 不在监听列表中：{parsed_channel_id}', ephemeral=True)
        return

    description = await get_channel_description(parsed_channel_id)
    remove_watched_channel(parsed_channel_id)
    watched_text = await build_watched_channel_list()
    extra = '\n注意：监听列表已为空，Bot 将监听所有可见频道。' if not CHANNEL_IDS else ''
    logger.info(f'✅ 已移除监听频道 ID: {parsed_channel_id} by {interaction.user.id}')
    await interaction.response.send_message(f'已移除监听：{description}{extra}\n\n{watched_text}', ephemeral=True)


@client.event
async def on_ready():
    global daily_report_task, slash_command_synced
    logger.info(f"✅ Bot 已登录: {client.user} (ID: {client.user.id})")

    if not slash_command_synced:
        try:
            synced = await tree.sync()
            slash_command_synced = True
            logger.info(f"✅ 已同步斜杠命令数量: {len(synced)}")
        except Exception as e:
            logger.error(f"❌ 同步斜杠命令失败: {e}")

    if daily_report_task is None or daily_report_task.done():
        daily_report_task = asyncio.create_task(daily_report_loop())
        logger.info('✅ 每日播报任务已启动')

    if not hasattr(client, '_cleanup_task_started'):
        client._cleanup_task_started = True
        asyncio.create_task(cleanup_old_files_loop())
        logger.info('✅ 日志自动清理任务已启动（保留 7 天）')


@client.event
async def on_disconnect():
    logger.warning('⚠️ 与 Discord 网关断开连接')


@client.event
async def on_resumed():
    logger.info('✅ 与 Discord 网关恢复会话')


@client.event
async def on_message(message: discord.Message):
    """监听消息事件：检测是否含有链接，没有则删除并发送短暂提示"""
    try:
        # 跳过 Bot 消息
        if message.author.bot:
            return

        # 跳过私聊消息（Bot 只处理服务器频道中的消息）
        if not message.guild:
            return

        # 检查是否监听此频道
        if CHANNEL_IDS and message.channel.id not in CHANNEL_IDS:
            return

        ensure_daily_stats_date()
        daily_stats['checked'] += 1

        # 清理过期的豁免期
        await cleanup_expired_exemptions()

        # 先判断发送者是否为管理员/频道主（豁免所有合规检查）
        if is_message_moderator(message):
            has_link = message_has_link(message)
            log_message_info(message, has_link, "✅ 已通过 - 发送者为管理员/频道主（豁免规则）")
            daily_stats['allowed_admin'] += 1
            await send_dm_log(
                message,
                "发送者为管理员/频道主，跳过内容合规性处理",
                "✅ 已通过（管理员/频道主豁免）"
            )
            return

        # 检查用户是否在豁免期内
        is_exempt = await is_user_exempt(message.author.id, message.channel.id)
        if is_exempt:
            remaining_seconds = await get_exemption_remaining_seconds(message.author.id, message.channel.id)
            has_link = message_has_link(message)
            log_message_info(message, has_link, f"✅ 已通过 - 发送者在豁免期内")
            daily_stats['allowed_exempt'] += 1
            await send_dm_log(
                message,
                "用户发送消息，处于豁免期",
                f"✅ 已通过（剩余豁免约 {remaining_seconds} 秒）"
            )
            return

        has_link = message_has_link(message)

        # 记录包含链接的消息（直接通过）
        if has_link:
            log_message_info(message, True, "✅ 已通过 - 消息包含有效链接")
            # 授予发送者 60 秒豁免期，允许发送任何内容
            await grant_exemption(message.author.id, message.channel.id, duration_seconds=EXEMPTION_SECONDS)
            daily_stats['allowed_link'] += 1
            daily_stats['exemption_granted'] += 1
            await send_dm_log(
                message,
                "用户发送消息，包含链接，给予通过并授予豁免期",
                f"✅ 已通过，并获得 {EXEMPTION_SECONDS} 秒豁免期"
            )
            return

        # 需要删除的消息
        log_message_info(message, False, "⏳ 正在删除无链接消息...")

        try:
            global total_deleted

            # 先发送删除操作日志（含附件下载），再删除消息
            await send_dm_log(
                message,
                "用户发送消息，不包含链接，已撤回消息并附带原消息内容",
                "✅ 消息已成功撤回"
            )

            await message.delete()
            logger.info(f"✅ 操作成功：消息已删除")
            daily_stats['deleted'] += 1
            total_deleted += 1

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
                reminder_embed.set_footer(text="此提醒将在5秒后自动删除")

                # 在频道发送提醒给用户
                await message.channel.send(
                    f'{message.author.mention}',
                    embed=reminder_embed,
                    delete_after=5  # 5秒后自动删除提醒
                )
                logger.info(f"✅ 删除提醒 Embed 已发送")
            except Exception as e:
                logger.warning(f"⚠️ 无法发送删除提醒 Embed: {e}")

        except Forbidden:
            daily_stats['errors'] += 1
            error_msg = (
                f"❌ 操作失败：Bot 缺少删除消息权限\n"
                f"  频道 ID: {message.channel.id}\n"
                f"  频道名: {getattr(message.channel, 'name', 'Unknown')}\n"
                f"  请确保 Bot 在该频道有 '删除消息' 权限"
            )
            logger.error(error_msg)
            await send_dm_log(
                message,
                "用户发送消息，不包含链接，尝试撤回消息",
                "❌ 撤回失败 - Bot 缺少删除消息权限"
            )
        except HTTPException as e:
            daily_stats['errors'] += 1
            error_msg = f"❌ 操作失败：HTTP 错误 - {str(e)}"
            logger.error(error_msg)
            await send_dm_log(
                message,
                "用户发送消息，不包含链接，尝试撤回消息",
                f"❌ 撤回失败 - HTTP 错误: {str(e)}"
            )

    except Exception as e:
        daily_stats['errors'] += 1
        # 记录消息信息便于排查
        msg_id = getattr(message, 'id', 'N/A')
        msg_author = getattr(message.author, 'id', 'N/A') if hasattr(message, 'author') else 'N/A'
        msg_ch = getattr(message.channel, 'id', 'N/A') if hasattr(message, 'channel') else 'N/A'
        logger.error(
            f"❌ on_message 未预期异常 (msg_id={msg_id}, author={msg_author}, channel={msg_ch}): "
            f"{type(e).__name__}: {e}",
            exc_info=True
        )
        try:
            if 'message' in dir() and message.guild:
                await send_dm_log(
                    message,
                    "处理消息时发生异常",
                    f"❌ 未预期错误: {type(e).__name__}"
                )
        except Exception:
            pass


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """监听消息编辑事件：编辑后移除链接也需要处理"""
    try:
        # 跳过 Bot 消息
        if after.author.bot:
            return

        # 跳过私聊
        if not after.guild:
            return

        # 检查是否监听此频道
        if CHANNEL_IDS and after.channel.id not in CHANNEL_IDS:
            return

        # 如果编辑后内容没变，不需要处理
        if before.content == after.content:
            return

        has_link_now = message_has_link(after)

        # 编辑后有了链接，授予豁免期（让它通过）
        if has_link_now:
            log_message_info(after, True, "✅ 编辑后已通过 - 消息包含有效链接")
            await grant_exemption(after.author.id, after.channel.id, duration_seconds=EXEMPTION_SECONDS)
            return

        # 编辑后没有链接 → 检查用户是否有豁免
        if is_message_moderator(after):
            log_message_info(after, False, "✅ 编辑后已通过 - 发送者为管理员/频道主")
            return

        is_exempt = await is_user_exempt(after.author.id, after.channel.id)
        if is_exempt:
            log_message_info(after, False, f"✅ 编辑后已通过 - 发送者在豁免期内")
            return

        # 编辑后不符合规则 → 删除
        log_message_info(after, False, "⏳ 编辑后无链接，正在删除...")
        await after.delete()
        logger.info(f"✅ 编辑后消息 {after.id} 已删除")
        await send_dm_log(after, "删除编辑后无链接的消息", "✅ 消息已成功删除")

        # 发送提醒
        try:
            reminder_embed = discord.Embed(
                title="❌ 消息已删除",
                description="你的消息编辑后不符合频道规则（必须包含链接）已被删除。",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            reminder_embed.set_footer(text="此提醒将在5秒后自动删除")
            await after.channel.send(
                f'{after.author.mention}',
                embed=reminder_embed,
                delete_after=5
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"❌ on_message_edit 异常: {type(e).__name__}: {e}",
            exc_info=True
        )


if __name__ == '__main__':
    if not TOKEN:
        error_msg = (
            '❌ 错误：未设置 DISCORD_TOKEN（可在 local_config.py 或环境变量中配置）\n'
            '\n使用方法（支持多频道）：\n'
            '  PowerShell:\n'
            '    $env:DISCORD_TOKEN="your_bot_token"\n'
            '    $env:DISCORD_CHANNEL_ID="123456789,987654321"  # 逗号分隔多频道，或留空监听所有\n'
            '    $env:DISCORD_LOG_USER_ID="用户ID"  # 可选：指定接收删除日志的用户\n'
            '    $env:DISCORD_REPORT_CHANNEL_ID="频道ID"  # 可选：日报接收频道\n'
            '    $env:DISCORD_REPORT_USER_ID="用户ID"  # 可选：日报接收私聊用户\n'
            '    $env:DISCORD_REPORT_TIME="09:00"  # 可选：每日播报时间（HH:MM）\n'
            '    python .\\bot1.py\n'
            '\n  CMD:\n'
            '    set DISCORD_TOKEN=your_bot_token\n'
            '    set DISCORD_CHANNEL_ID=123456789,987654321\n'
            '    set DISCORD_LOG_USER_ID=用户ID\n'
            '    set DISCORD_REPORT_CHANNEL_ID=频道ID\n'
            '    set DISCORD_REPORT_USER_ID=用户ID\n'
            '    set DISCORD_REPORT_TIME=09:00\n'
            '    python bot1.py\n'
            '\n  Linux/Mac:\n'
            '    export DISCORD_TOKEN="your_bot_token"\n'
            '    export DISCORD_CHANNEL_ID="123456789,987654321"\n'
            '    export DISCORD_LOG_USER_ID="用户ID"\n'
            '    export DISCORD_REPORT_CHANNEL_ID="频道ID"\n'
            '    export DISCORD_REPORT_USER_ID="用户ID"\n'
            '    export DISCORD_REPORT_TIME="09:00"\n'
            '    python bot1.py'
        )
        print(error_msg)
        logger.error(error_msg)
        raise SystemExit(1)
    
    logger.info("🚀 正在启动 Discord Bot...")
    try:
        client.run(TOKEN)
    except Exception:
        logger.exception('❌ Bot 进程异常退出')
        raise

