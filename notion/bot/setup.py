"""Telegram Bot 设置模块"""
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from ..utils.logger import setup_logger
from .handler import handle_any_message
from common_utils import is_user_authorized
from config import *
# 配置日志
logger = setup_logger('notion.bot')

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

async def start(update: Update, context) -> None:
    """处理 /start 命令"""
    user = update.effective_user
    if is_user_authorized(user.id):
        await update.message.reply_text(
            f"欢迎使用 Notion 机器人，{user.first_name}！\n"
            "您可以直接发送消息，我会将它们保存到 Notion 中。"
        )
        logger.info(
            "Authorized user started the bot",
            extra={'username': user.username, 'user_id': user.id}
        )
    else:
        await update.message.reply_text("抱歉，您没有权限使用此机器人。")
        logger.warning(
            "Unauthorized user attempted to start the bot",
            extra={'username': user.username, 'user_id': user.id}
        )

async def help_command(update: Update, context) -> None:
    """处理 /help 命令"""
    if not is_user_authorized(update.effective_user.id):
        await update.message.reply_text('您没有权限使用此机器人。')
        return
    await update.message.reply_text(
        '使用说明：\n'
        '1. 直接发送消息，我会将它们保存到 Notion 中\n'
        '2. 发送文件，我会将它们上传到 Notion\n'
        '3. 发送图片，我会将它们保存到 Notion\n'
        '4. 发送语音，我会将它们转换为文本并保存'
    )

def setup_commands(app: Application) -> None:
    """设置机器人命令"""
    commands = [
        BotCommand('start', '开始使用机器人'),
        BotCommand('help', '获取帮助信息'),
    ]
    app.bot.set_my_commands(commands)

def setup_bot() -> Application:
    """设置机器人"""
    try:
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # 添加处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.ALL, lambda update, context: handle_any_message(update, context)))
        
        logger.info("Bot setup completed successfully")
        return application
        
    except Exception as e:
        logger.exception("Failed to setup bot")
        raise