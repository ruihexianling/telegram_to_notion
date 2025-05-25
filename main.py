import asyncio
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from werkzeug.middleware.proxy_fix import ProxyFix
from hypercorn.config import Config
from hypercorn.asyncio import serve as hypercorn_serve

from config import *
from notion_bot_utils import handle_any_message

# 配置日志记录
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG)

# Notion 配置
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

# 初始化 Flask 应用
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# 全局的 Application 实例，所有处理器都将注册到这个实例上
# IMPORTANT: Initialize it here and only once.
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

def setup_handlers(app_instance: Application):
    """设置 Telegram 应用并添加处理器。"""
    logging.info("Setting up Telegram handlers...")

    app_instance.add_handler(CommandHandler("start", start_command))
    app_instance.add_handler(CommandHandler("help", help_command))
    logging.info("Command handlers added.")

    bound_handle_any_message = partial(handle_any_message, notion_config=NOTION_CONFIG)
    app_instance.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, bound_handle_any_message))
    logging.info("Message handler added.")

async def setup_commands(app_instance: Application):
    """设置机器人的命令菜单。"""
    commands = [
        BotCommand('start', 'Start the bot'),
        BotCommand('help', 'Get help'),
    ]
    await app_instance.bot.set_my_commands(commands)
    logging.info("Telegram commands set.")

async def start_command(update: Update, context):
    """处理 /start 命令"""
    logging.info(f"Received /start command from user: {update.message.from_user.id}")
    await update.message.reply_text('Welcome to the bot!')
    logging.info(f"Replied to /start command for user: {update.message.from_user.id}")

async def help_command(update: Update, context):
    """处理 /help 命令"""
    logging.info(f"Received /help command from user: {update.message.from_user.id}")
    await update.message.reply_text('Here is how you can use the bot...')
    logging.info(f"Replied to /help command for user: {update.message.from_user.id}")

async def set_webhook(app_instance: Application):
    """设置 Telegram 机器人的 Webhook URL。"""
    webhook_url = f"{RENDER_WEBHOOK_URL.rstrip('/')}/{WEBHOOK_PATH}"
    if webhook_url:
        try:
            await app_instance.bot.set_webhook(webhook_url)
            logging.info(f"Webhook URL set to: {webhook_url}")
        except Exception as e:
            logging.error(f"Error setting Webhook URL: {e}", exc_info=True)
    else:
        logging.warning("RENDER_WEBHOOK_URL or WEBHOOK_PATH is not set. Cannot set webhook.")

# --- Flask 路由 ---

@app.route('/')
def index():
    """根路由，用于健康检查或简单访问"""
    logging.info(f"Received root request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return 'Hello, World!'

@app.route('/healthz', methods=['GET'])
def health():
    """健康检查路由"""
    logging.info(f"Received health check request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return jsonify({
        "status": "ok"
    }), 200

@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
async def save_to_notion_webhook():
    """处理 Telegram Webhook 更新"""
    logging.info(f"Received webhook POST request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    update_data = request.get_json()

    if not update_data:
        logging.warning("Received empty webhook update.")
        return 'ok'

    user_id = None
    if 'message' in update_data:
        user_id = update_data['message'].get('from', {}).get('id')
    elif 'callback_query' in update_data:
        user_id = update_data['callback_query'].get('from', {}).get('id')

    if user_id is None:
        logging.warning(f"Could not extract user_id from update: {update_data.keys()}")
        return 'ok'

    if not is_authorized(user_id):
        logging.warning(f"Unauthorized access attempt by user {user_id} with update: {update_data}")
        return jsonify({"error": "Unauthorized"}), 403

    logging.debug(f"Received webhook update data: {update_data}")

    try:
        # It's crucial that 'application' is already initialized at this point.
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        logging.info(f"Finished processing update for user {user_id}.")

    except Exception as e:
        logging.error(f"Error processing Telegram update: {e}", exc_info=True)
        return jsonify({"error": "Failed to process update"}), 500
    
    return 'ok'

@app.route('/webhook_status', methods=['GET'])
async def webhook_status():
    """获取 Webhook 状态"""
    logging.info(f"Received /webhook_status request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")

    try:
        info = await application.bot.get_webhook_info()
        statuses = {
            'webhook_url': info.url,
            'has_custom_certificate': info.has_custom_certificate,
            'pending_update_count': info.pending_update_count,
            'last_error_date': info.last_error_date,
            'last_error_message': info.last_error_message,
            'max_connections': info.max_connections,
            'allowed_updates': info.allowed_updates
        }
        logging.info(f"Webhook status: {statuses}")
        return jsonify(statuses)
    except Exception as e:
        logging.error(f"Error fetching webhook status: {e}", exc_info=True)
        return jsonify({"error": "Failed to get webhook status", "details": str(e)}), 500

def is_authorized(user_id):
    """检查用户是否在授权列表中"""
    if user_id in AUTHORIZED_USERS:
        return True
    return False

# --- Initialization function for both modes ---
async def initialize_application():
    """Initializes the Telegram Application instance."""
    logging.info("Initializing Telegram Application...")
    setup_handlers(application)
    await setup_commands(application)
    await application.initialize() # This is the crucial step

# --- Main entry point ---
async def main():
    """Runs the Telegram bot application."""
    try:
        logging.info("Application starting...")

        # Initialize the application once, regardless of mode
        await initialize_application()

        if USE_WEBHOOK:
            logging.info("USE_WEBHOOK is true. Preparing for webhook mode.")
            await set_webhook(application)

            logging.info(f"Starting Flask app with Hypercorn on port {PORT} for webhook mode.")
            config = Config()
            config.bind = [f"0.0.0.0:{PORT}"]
            # Use 'asyncio.run' for starting the Hypercorn server if this is the top-level entry point,
            # or ensure it runs within an existing asyncio event loop.
            # In your original code, you are calling hypercorn_serve directly within asyncio.run(main()), which is fine.
            await hypercorn_serve(app, config)
            
        else:
            logging.info("USE_WEBHOOK is false or not set. Running in long polling mode.")
            await application.run_polling(poll_interval=2)
            logging.info("Bot stopped long polling.")

    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)

    logging.info("Application finished.")

if __name__ == "__main__":
    try:
        _ = TELEGRAM_BOT_TOKEN
        _ = RENDER_WEBHOOK_URL
        _ = WEBHOOK_PATH
        _ = PORT
        _ = USE_WEBHOOK
        _ = AUTHORIZED_USERS
    except NameError as e:
        logging.critical(f"Configuration error: {e}. Please ensure all required variables are defined in config.py")
        exit(1)

    asyncio.run(main())