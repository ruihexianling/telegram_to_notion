"""Telegram Bot 设置模块"""
from urllib import request

import requests
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from .handler import handle_any_message
from common_utils import auth_required, is_auth_user, admin_required
from config import *
from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

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
            ]
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

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

async def start(update: Update, context) -> None:
    """处理 /start 命令"""
    user = update.effective_user
    logger.debug(
        f"Received /start command - username: {user.username} - user_id: {user.id}"
    )
    
    if is_auth_user(user.id):
        await update.message.reply_text(
            f"欢迎使用 Notion 机器人，{user.first_name}！\n"
            "您可以直接发送消息，我会将它们保存到 Notion 中。"
        )
        logger.info(
            f"Authorized user started the bot - username: {user.username} - user_id: {user.id}"
        )
    else:
        await update.message.reply_text("抱歉，您没有权限使用此机器人。")
        logger.warning(
            f"Unauthorized user attempted to start the bot - username: {user.username} - user_id: {user.id}"
        )

@auth_required
async def help_command(update: Update, context) -> None:
    """处理 /help 命令"""
    user = update.effective_user
    logger.debug(
        f"Received /help command - username: {user.username} - user_id: {user.id}"
    )
        
    await update.message.reply_text(
        '使用说明：\n'
        '1. 直接发送消息，我会将它们保存到 Notion 中\n'
        '2. 发送文件，我会将它们上传到 Notion\n'
        '3. 发送图片，我会将它们保存到 Notion\n'
        '4. 发送语音，我会将它们转换为文本并保存'
    )
    logger.info(
        f"Help information sent to user - username: {user.username} - user_id: {user.id}"
    )

@admin_required
async def deploy_command(update: Update, context) -> None:
    """执行重新部署实例的命令（管理员专用）"""
    user = update.effective_user
    logger.debug(
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
        await update.message.reply_text(f"❌ 部署请求出错: {e}")

    logger.info(
        f"Deploy command executed - username: {user.username} - user_id: {user.id}"
    )

async def setup_commands(app: Application) -> Application:
    """设置机器人命令"""
    logger.debug("Setting up bot commands")
    commands = [
        BotCommand('start', '开始使用机器人'),
        BotCommand('help', '获取帮助信息'),
        BotCommand('deploy', '部署'),
    ]
    try:
        # 设置机器人命令
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully.")
    except Exception as e:
        logger.exception(f"Failed to set bot commands - error: {e}/n")
        raise
    logger.info("Bot commands setup completed")
    return app

def setup_bot() -> Application:
    """设置机器人"""
    try:
        logger.debug("Starting bot setup")
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # 添加处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("deploy", deploy_command))
        application.add_handler(MessageHandler(filters.ALL, lambda update, context: handle_any_message(update, context)))
        application.add_error_handler(error_handler)
        
        logger.info("Bot setup completed successfully")
        return application
        
    except Exception as e:
        logger.exception("Failed to setup bot")
        raise