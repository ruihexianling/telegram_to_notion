import asyncio
import os
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from werkzeug.middleware.proxy_fix import ProxyFix

from config import *
from notion_bot_utils import handle_any_message

# 配置日志记录
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Notion 配置
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

# 初始化 Flask 应用
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# 全局的 Application 实例
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# 用于标记初始化状态的全局变量
# 这对于多进程环境可能不完美，但对于单进程模式下的错误排查有帮助
_application_initialized = False


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
    try:
        await app_instance.bot.set_my_commands(commands)
        logging.info("Telegram commands set.")
    except Exception as e:
        logging.error(f"Error setting Telegram commands: {e}", exc_info=True)


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
            current_webhook_info = await app_instance.bot.get_webhook_info()
            if current_webhook_info.url != webhook_url:
                await app_instance.bot.set_webhook(webhook_url)
                logging.info(f"Webhook URL set to: {webhook_url}")
            else:
                logging.info(f"Webhook URL already set to: {webhook_url}. No change needed.")
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
        "status": "ok",
        "app_initialized": _application_initialized # 添加初始化状态，方便调试
    }), 200

@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
async def save_to_notion_webhook():
    """处理 Telegram Webhook 更新"""
    global _application_initialized
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
        return 'ok'

    logging.debug(f"Received webhook update data: {update_data}")

    # **关键改动：在处理 webhook 之前，确保 application 已初始化**
    # 针对可能的多进程或状态丢失问题，这里增加一个检查和延迟初始化机制
    if not _application_initialized:
        logging.warning("Application not yet initialized for this process. Attempting deferred initialization.")
        try:
            await application.initialize()
            setup_handlers(application) # 确保 handlers 也被设置
            # setup_commands 和 set_webhook 不在这里重复调用，因为它们只需要一次
            _application_initialized = True
            logging.info("Application successfully initialized in webhook handler.")
        except Exception as e:
            logging.error(f"Deferred initialization failed: {e}", exc_info=True)
            return 'ok' # 初始化失败，返回 ok 避免 Telegram 重试

    try:
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        logging.info(f"Finished processing update for user {user_id}.")

    except Exception as e:
        logging.error(f"Error processing Telegram update: {e}", exc_info=True)
        return 'ok'
    
    return 'ok'


@app.route('/webhook_status', methods=['GET'])
async def webhook_status():
    """获取 Webhook 状态"""
    logging.info(f"Received /webhook_status request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    try:
        # 确保在获取 webhook info 之前 application 已经初始化
        if not _application_initialized:
             logging.warning("Application not initialized for webhook status check. Attempting deferred initialization.")
             await application.initialize()
             _application_initialized = True

        info = await application.bot.get_webhook_info()
        statuses = {
            'webhook_url': info.url,
            'has_custom_certificate': info.has_custom_certificate,
            'pending_update_count': info.pending_update_count,
            'last_error_date': info.last_error_date,
            'last_error_message': info.last_error_message,
            'max_connections': info.max_connections,
            'allowed_updates': info.allowed_updates,
            'app_initialized': _application_initialized # 添加初始化状态
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

# --- 主函数入口 ---

async def initialize_and_start_webhook_app():
    """初始化 Telegram Application 并启动 Flask 服务器。"""
    global _application_initialized
    logging.info("Starting application in Webhook mode...")
    
    try:
        # 1. 初始化 application
        await application.initialize()
        _application_initialized = True # 标记为已初始化
        logging.info("Telegram Application initialized.")

        # 2. 设置处理器
        setup_handlers(application)
        
        # 3. 设置命令
        await setup_commands(application)

        # 4. 设置 Webhook
        await set_webhook(application)

        logging.info(f"Starting Flask app with Hypercorn on port {PORT} for webhook mode.")
        from hypercorn.config import Config
        from hypercorn.asyncio import serve as hypercorn_serve
        
        config = Config()
        config.bind = [f"0.0.0.0:{PORT}"]
        
        await hypercorn_serve(app, config)
        logging.info("Hypercorn server stopped.")
    except Exception as e:
        logging.critical(f"Fatal error during webhook app startup: {e}", exc_info=True)
        exit(1)


def start_polling_app():
    """以 Long Polling 模式启动 Bot。"""
    logging.info("Starting application in Long Polling mode...")
    
    # Long Polling 模式不需要显式调用 initialize，run_polling 内部会处理
    setup_handlers(application)
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_commands(application))

    logging.info("Running in long polling mode.")
    application.run_polling(poll_interval=2)
    logging.info("Bot stopped long polling.")


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

    if USE_WEBHOOK:
        asyncio.run(initialize_and_start_webhook_app())
    else:
        start_polling_app()
    
    logging.info("Application finished.")