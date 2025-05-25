import asyncio
import os
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand
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
    await update.message.reply_text('Welcome to the bot!')

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

application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
async def save_to_notion_webhook():
    logging.info(f"Received webhook request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    update = request.get_json()
    if update:
        user_id = update.get('message', {}).get('from', {}).get('id')
        if not is_authorized(user_id):
            logging.warning(f"Unauthorized access attempt by user {user_id}")
            update.message.reply_text('Unauthorized access, Please contact the administrator')
            return jsonify({"error": "Unauthorized"}), 403
        logging.debug(f"Received webhook update: {update}")
        await application.process_update(update)
    return 'ok'


@app.route('/webhook_status')
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
    statuses[TELEGRAM_BOT_TOKEN[:8]] = {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message,
        "max_connections": info.max_connections,
        "allows_anonymous": info.allows_anonymous,
        "ip_address": info.ip_address
    }
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

async def main():
    """运行 Telegram bot 应用的主函数。"""
    try:
        logging.info("Starting application...")
        global application
        application = (
                Application.builder()
                .token(TELEGRAM_BOT_TOKEN)
                .build()
            )

        # 设置 Telegram 应用并添加处理器
        setup_handlers(application)
        
        # 设置命令菜单
        await setup_commands(application)


        if USE_WEBHOOK:
            # Initialize the application for webhook mode
            await application.initialize()
            
            await set_webhook(application)
            logging.info("USE_WEBHOOK is true. Running in webhook mode.")
            run_webhook(app, RENDER_WEBHOOK_URL, PORT)
        else:
            logging.info("USE_WEBHOOK is false or not set. Running in long polling mode.")
            run_long_polling(application)

    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)

    logging.info("Application finished.")


if __name__ == "__main__":
    asyncio.run(main())