"""Telegram Bot 设置模块"""
import traceback
from urllib import request
import os
import psutil
import platform
from datetime import datetime
import pytz

import requests
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from .handler import handle_any_message
from .application import set_application, get_application
from common_utils import auth_required, admin_required
from config import *
from logger import setup_logger

logger = setup_logger(__name__)

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': DATABASE_ID
}

# === 管理员消息相关函数 ===
async def send_message_to_admins(application: Application, text: str):
    """发送消息给所有管理员用户"""
    logger.debug(f"Sending message to admin users: {text}")
    for admin_id in ADMIN_USERS:
        try:
            await application.bot.send_message(chat_id=admin_id, text=text)
            logger.info(f"Message '{text}' sent to admin: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send message '{text}' to admin {admin_id}: {e}")
    logger.info("Messages sent to all admins")

async def after_bot_start(application: Application):
    """机器人上线后，给所有管理员发送消息"""
    await send_message_to_admins(application, "🤖 机器人已上线！")

async def before_bot_stop(application: Application):
    """机器人下线前，给所有管理员发送消息"""
    # render蓝绿机制，不适用
    # await send_message_to_admins(application, "🤖 机器人已下线！")
    pass

# === Webhook 相关函数 ===
async def setup_webhook(application: Application, webhook_url: str) -> None:
    """设置 webhook
    
    Args:
        application: Telegram 应用实例
        webhook_url: webhook URL
    """
    try:
        logger.info(f"Setting up webhook - url: {webhook_url}")
        
        # 设置 webhook
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=[
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "inline_query",
                "chosen_inline_result",
                "callback_query",
                "shipping_query",
                "pre_checkout_query",
                "poll",
                "poll_answer",
                "my_chat_member",
                "chat_member",
                "chat_join_request"
            ],
            drop_pending_updates=False,  # 丢弃待处理的更新
            max_connections=100,  # 最大连接数
            ip_address=None  # 自动检测IP地址
        )
        
        # 获取 webhook 信息
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook info - url: {webhook_info.url} - has_custom_certificate: {webhook_info.has_custom_certificate} - pending_update_count: {webhook_info.pending_update_count}")
        
    except Exception as e:
        logger.exception(f"Failed to setup webhook - error: {e}")
        raise

async def remove_webhook(application: Application) -> None:
    """移除 webhook
    
    Args:
        application: Telegram 应用实例
    """
    try:
        logger.info("Removing webhook")
        await application.bot.delete_webhook()
        logger.info("Webhook removed successfully")
    except Exception as e:
        logger.exception(f"Failed to remove webhook - error: {e}")
        raise

# === 命令处理函数 ===
async def start(update: Update, context) -> None:
    """处理 /start 命令"""
    user = update.effective_user
    logger.info(
        f"Received /start command - username: {user.username} - user_id: {user.id}"
    )

    await update.message.reply_text(
        f"欢迎使用 Notion 机器人，{user.first_name}！\n"
        "您可以直接发送消息，我会将它们保存到 Notion 中。"
    )
    logger.info(
        f"Start information sent to user - username: {user.username} - user_id: {user.id}"
    )

@auth_required
async def help_command(update: Update, context) -> None:
    """处理 /help 命令"""
    user = update.effective_user
    logger.info(
        f"Received /help command - username: {user.username} - user_id: {user.id}"
    )
        
    await update.message.reply_text(
        '使用说明：\n'
        '1. 直接发送消息，我会将它们保存到 Notion 中\n'
        '2. 发送文件，我会将它们上传到 Notion\n'
        '3. 发送图片，我会将它们保存到 Notion\n'
    )
    logger.info(
        f"Help information sent to user - username: {user.username} - user_id: {user.id}"
    )

@admin_required
async def deploy_command(update: Update, context) -> None:
    """执行重新部署实例的命令（管理员专用）"""
    user = update.effective_user
    logger.info(
        f"Received /deploy command - username: {user.username} - user_id: {user.id}"
    )
    
    await update.message.reply_text("🔄 正在重新部署实例...")
    
    try:
        # 构建请求数据
        url = DEPLOY_URL
        response = requests.get(url)
        
        if response.status_code == 200:
            await update.message.reply_text("✅ 部署请求已发送，请等待实例重新部署...")
        else:
            await update.message.reply_text(f"❌ 部署请求失败: {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"❌ 部署请求出错: {e}\n{traceback.format_exc()}")

    logger.info(
        f"Deploy command executed - username: {user.username} - user_id: {user.id}"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(
        f"Exception while handling an update - update_id: {getattr(update, 'update_id', None)} - "
        f"user_id: {getattr(update.effective_user, 'id', None) if update and hasattr(update, 'effective_user') else None}",
        exc_info=context.error
    )

    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("发生了一个错误，请稍后再试。")
            logger.info("Error message sent to user")
    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")

def format_datetime(dt: datetime) -> str:
    """将时间格式化为北京时间字符串
    
    Args:
        dt: 要格式化的时间对象
        
    Returns:
        str: 格式化后的北京时间字符串
    """
    if dt is None:
        return '无'
    beijing_tz = pytz.timezone('Asia/Shanghai')
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    beijing_time = dt.astimezone(beijing_tz)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

async def get_system_info() -> str:
    """获取系统信息"""
    try:
        logger.info("Getting system info...")
        # 获取北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(beijing_tz)
        
        # 系统信息
        system_info = f"🖥 系统信息:\n"
        system_info += f"• 系统: {platform.system()} {platform.release()}\n"
        system_info += f"• 架构: {platform.machine()}\n"
        system_info += f"• Python: {platform.python_version()}\n"
        
        # CPU 信息
        cpu_info = f"\n💻 CPU 信息:\n"
        cpu_info += f"• 物理核心数: {psutil.cpu_count(logical=False)}\n"
        cpu_info += f"• 逻辑核心数: {psutil.cpu_count()}\n"
        cpu_info += f"• CPU 使用率: {psutil.cpu_percent()}%\n"
        
        # 内存信息
        memory = psutil.virtual_memory()
        memory_info = f"\n🧠 内存信息:\n"
        memory_info += f"• 总内存: {memory.total / (1024**3):.2f} GB\n"
        memory_info += f"• 已用内存: {memory.used / (1024**3):.2f} GB\n"
        memory_info += f"• 内存使用率: {memory.percent}%\n"
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_info = f"\n💾 磁盘信息:\n"
        disk_info += f"• 总空间: {disk.total / (1024**3):.2f} GB\n"
        disk_info += f"• 已用空间: {disk.used / (1024**3):.2f} GB\n"
        disk_info += f"• 磁盘使用率: {disk.percent}%\n"
        
        # 进程信息
        process = psutil.Process(os.getpid())
        process_info = f"\n⚙️ 进程信息:\n"
        process_info += f"• PID: {process.pid}\n"
        process_info += f"• 进程内存: {process.memory_info().rss / (1024**2):.2f} MB\n"
        process_info += f"• CPU 使用率: {process.cpu_percent()}%\n"
        process_info += f"• 运行时间: {format_datetime(datetime.fromtimestamp(process.create_time()))}\n"
        
        # 网络信息
        net_info = f"\n🌐 网络信息:\n"
        net_io = psutil.net_io_counters()
        net_info += f"• 发送: {net_io.bytes_sent / (1024**2):.2f} MB\n"
        net_info += f"• 接收: {net_io.bytes_recv / (1024**2):.2f} MB\n"
        
        # 系统负载
        load1, load5, load15 = psutil.getloadavg()
        load_info = f"\n📊 系统负载:\n"
        load_info += f"• 1分钟: {load1:.2f}\n"
        load_info += f"• 5分钟: {load5:.2f}\n"
        load_info += f"• 15分钟: {load15:.2f}\n"
        
        return system_info + cpu_info + memory_info + disk_info + process_info + net_info + load_info
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        return f"获取系统信息失败: {str(e)}"

@admin_required
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /status 命令"""
    try:
        if not update or not update.message:
            logger.error("Invalid update object in status command", exc_info=True)
            return
            
        user = update.effective_user
        logger.debug(f"Received /status command - username: {user.username} - user_id: {user.id}")
        
        # 获取系统信息
        system_info = await get_system_info()
        
        # 获取 bot 状态
        application = get_application()
        if not application:
            await update.message.reply_text("❌ 无法获取 bot 状态：应用未初始化")
            return
            
        webhook_info = await application.bot.get_webhook_info()
        
        # 获取北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(beijing_tz)
        
        # 构建状态消息
        status_message = (
            "📊 系统状态报告\n"
            f"时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{system_info}\n\n"
            "🤖 Bot 状态:\n"
            f"• Webhook URL: {len(webhook_info.url) > 0}\n"
            f"• 连接数: {webhook_info.max_connections}\n"
            f"• 连接状态: {webhook_info.has_custom_certificate}\n"
            f"• 待处理更新: {webhook_info.pending_update_count}\n"
            f"• 最后错误时间: {format_datetime(webhook_info.last_error_date)}\n"
            f"• 最后错误: {webhook_info.last_error_message or '无'}\n"
            f"• 最后同步时间: {format_datetime(webhook_info.last_synchronization_error_date)}"
        )
        
        await update.message.reply_text(status_message)
        logger.info(f"Status information sent to user - username: {user.username} - user_id: {user.id}")
    except Exception as e:
        logger.error(f"Status command error: {e}", exc_info=True)
        if update and update.message:
            await update.message.reply_text(f"❌ 获取状态信息失败: {str(e)}")
        else:
            logger.error("Cannot send error message: invalid update object")

# === 机器人设置函数 ===
async def setup_commands(application: Application) -> Application:
    """设置机器人命令
    
    Args:
        application: Telegram 应用实例
        
    Returns:
        Application: 设置完成后的应用实例
    """
    logger.debug("Setting up bot commands")
    commands = [
        BotCommand('start', '开始使用机器人'),
        BotCommand('help', '获取帮助信息'),
        BotCommand('deploy', '部署'),
        BotCommand('status', '查看系统状态'),
    ]
    try:
        # 设置机器人命令
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully.")
    except Exception as e:
        logger.exception(f"Failed to set bot commands - error: {e}/n")
        raise
    logger.info("Bot commands setup completed")
    return application

def setup_bot() -> Application:
    """设置机器人
    
    Returns:
        Application: 配置完成的 Telegram 应用实例
    """
    try:
        logger.info("Starting bot setup")
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # 设置全局应用实例
        set_application(application)
        
        # 添加处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("deploy", deploy_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(MessageHandler(filters.ALL, lambda update, context: handle_any_message(update, context)))
        application.add_error_handler(error_handler)
        
        logger.info("Bot setup completed successfully")
        return application
    except Exception as e:
        logger.exception("Failed to setup bot: %s", e)
        raise
