import asyncio
import os
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from werkzeug.middleware.proxy_fix import ProxyFix

from config import *

# 配置日志记录
from notion_bot_utils import handle_any_message

# logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG)

NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # 处理X-Forwarded-For

def setup_handlers(application):
    """设置 Telegram 应用并添加处理器。"""
    logging.info("Application starting...")

    # 添加处理器
    logging.info("Adding command and message handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # 使用偏函数将 NOTION_CONFIG 传递给 handle_any_message
    bound_handle_any_message = partial(handle_any_message, notion_config=NOTION_CONFIG)

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, bound_handle_any_message))
    logging.info("Handlers added.")


async def setup_commands(application):
    """设置机器人的命令菜单。"""
    commands = [
        BotCommand('start', 'Start the bot'),
        BotCommand('help', 'Get help'),
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Commands set.")

async def start_command(update, context):
    """处理 /start 命令"""
    logging.info(f"*** Entering start_command for user: {update.message.from_user.id} ***")
    await update.message.reply_text('Welcome to the bot!')
    logging.info(f"*** Replied to /start command for user: {update.message.from_user.id} ***")

async def help_command(update, context):
    """处理 /help 命令"""
    await update.message.reply_text('Here is how you can use the bot...')

async def set_webhook(application):
    """设置 Telegram 机器人的 Webhook URL。"""
    webhook_url = f"{RENDER_WEBHOOK_URL.rstrip('/')}/{WEBHOOK_PATH}"
    if webhook_url:
        try:
            await application.bot.set_webhook(webhook_url)
            logging.info(f"Webhook URL 设置为: {webhook_url}")
        except Exception as e:
            logging.error(f"设置 Webhook URL 时发生错误: {e}")
    else:
        logging.warning("WEBHOOK_URL 环境变量未设置。")


@app.route('/')
def index():
    """根路由，用于健康检查"""
    logging.info(f"收到根路由请求: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return 'Hello, World!'

@app.route('/healthz', methods=['GET'])
def health():
    # 打印请求信息
    logging.info(f"收到健康检查请求: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return jsonify({
        "status": "ok"
    }), 200


@app.route('/webhook_status', methods=['GET'])
async def webhook_status():
    """获取 Webhook 状态"""
    logging.info(f"收到/webhook_status请求: {request.remote_addr} {request.method} {request.path} {request.user_agent}")

    # 添加身份验证检查
    auth_header = request.headers.get('Authorization')

    # if not auth_header or auth_header != f"Bearer {WEBHOOK_SECRET}":
    #     logging.warning("未授权的访问尝试")
    #     return jsonify({"error": "Unauthorized"}), 401

    statuses = {}
    info = application.bot.get_webhook_info()
    statuses['webhook_url'] = info.url
    statuses['pending_updates_count'] = info.pending_update_count
    statuses['last_error_date'] = info.last_error_date
    statuses['last_error_message'] = info.last_error_message
    statuses['max_connections'] = info.max_connections
    statuses['allowed_updates'] = info.allowed_updates
    logging.info(f"Webhook status: {statuses}")
    return jsonify(statuses)

def run_long_polling(app):
    logging.info("Starting bot in long polling mode...")
    logging.info("Bot started in long polling mode. Press Ctrl-C to stop.")
    # 运行 bot 直到用户按下 Ctrl-C
    app.run_polling(poll_interval=2)


def run_webhook(flask_app, webhook_url, port):
    if not webhook_url:
        logging.error("WEBHOOK_URL not found in environment variables. Webhook mode requires WEBHOOK_URL.")
        exit(1)

    logging.info(f"Starting Flask app for webhook on port {port}...")
    # 在生产环境中使用 Gunicorn 或 uWSGI
    flask_app.run(host='0.0.0.0', port=port)

def is_authorized(user_id):
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
        _application_initialized = True
        logging.info("Telegram Application initialized.")

        # 2. 设置处理器
        setup_handlers(application)
        
        # 设置命令菜单
        await setup_commands(application)

        # 4. 设置 Webhook
        await set_webhook(application)

        logging.info(f"Starting Hypercorn with combined Flask and Telegram webhook handler on port {PORT}.")
        from hypercorn.config import Config
        from hypercorn.asyncio import serve as hypercorn_serve
        
        config = Config()
        config.bind = [f"0.0.0.0:{PORT}"]
        
        # 将 Flask 应用和 Telegram Webhook Handler 组合起来
        # 我们需要一个简单的 ASGI app 来分发请求。
        async def combined_asgi_app(scope, receive, send, sync_spawn, call_soon):
            if scope['type'] == 'http':
                # 判断路径是否是 Telegram Webhook 路径
                if scope['path'] == f'/{WEBHOOK_PATH}':
                    logging.debug(f"Routing to Telegram Webhook Handler for path: {scope['path']}")
                    # 如果是 Telegram Webhook 路径，交给 application 处理
                    return await application(scope, receive, send)
                else:
                    logging.debug(f"Routing to Flask app for path: {scope['path']}")
                    # 其他路径交给 Flask app 处理
                    from hypercorn.app_wrappers import WSGIWrapper
                    await WSGIWrapper(app, max_body_size=1048576)(scope, receive, send, sync_spawn, call_soon)
            else:
                logging.warning(f"Unhandled ASGI scope type: {scope['type']}")
                # 对于其他 ASGI scope 类型，可以尝试默认行为或返回错误
                # 这里为了简单，我们让 Hypercorn 默认处理（通常会失败或忽略）
                # 实际生产中可能需要更严谨的 ASGI 路由
                await send({'type': 'http.response.start', 'status': 404, 'headers': []})
                await send({'type': 'http.response.body', 'body': b'Not Found'})

        # 启动 Hypercorn，并传入我们组合的 ASGI 应用
        await hypercorn_serve(combined_asgi_app, config)
        logging.info("Hypercorn server stopped.")

    except Exception as e:
        logging.critical(f"Fatal error during webhook app startup: {e}", exc_info=True)
        exit(1)


def start_polling_app():
    """以 Long Polling 模式启动 Bot。"""
    logging.info("Starting application in Long Polling mode...")
    
    setup_handlers(application)
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_commands(application))

    logging.info("Running in long polling mode.")
    application.run_polling(poll_interval=2)
    logging.info("Bot stopped long polling.")


if __name__ == "__main__":
    try:
        # 确保所有必要的配置变量都已定义
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
        # 当 USE_WEBHOOK 为 True 时，运行异步的 webhook 启动函数
        asyncio.run(initialize_and_start_webhook_app())
    else:
        # 当 USE_WEBHOOK 为 False 时，运行同步的 long polling 启动函数
        start_polling_app()
    
    logging.info("Application finished.")

if __name__ == "__main__":
    asyncio.run(main())