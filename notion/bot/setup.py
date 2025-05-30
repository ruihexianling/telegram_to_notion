"""Telegram Bot 设置模块"""
from datetime import datetime

import pytz
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from .handler import handle_any_message
from .application import set_application, get_application
from .tools import (
    send_message_to_admins,
    after_bot_start,
    before_bot_stop,
    setup_webhook,
    remove_webhook,
    get_system_info,
    format_datetime,
    trigger_deploy
)
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
    
    success, message = await trigger_deploy()
    await update.message.reply_text(message)

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
