from telegram.ext import Application, CommandHandler, MessageHandler, filters
from functools import partial
from notion_bot_utils import handle_any_message
from config import *

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}
# === 命令处理函数 ===
async def start_command(update, context):
    await update.message.reply_text('Welcome to the bot!')

async def help_command(update, context):
    await update.message.reply_text('Here is how you can use the bot...')

async def setup_commands(app):
    commands = [
        BotCommand('start', 'Start the bot'),
        BotCommand('help', 'Get help'),
    ]
    await app.bot.set_my_commands(commands)

def setup_bot(token):
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, partial(handle_any_message, notion_config=NOTION_CONFIG)))
    return application