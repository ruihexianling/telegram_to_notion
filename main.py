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

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # 处理X-Forwarded-For

def load_and_validate_config():
    """加载并验证必要的配置。"""
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        exit(1)

    notion_config = {
        'NOTION_KEY': NOTION_KEY,
        'NOTION_VERSION': NOTION_VERSION,
        'PAGE_ID': PAGE_ID
    }

    # 检查 Notion 配置
    if not notion_config.get('NOTION_KEY') or not notion_config.get('PAGE_ID'):
        logging.error("Notion configuration (NOTION_KEY or NOTION_PAGE_ID) not found in environment variables.")
        exit(1)

    return notion_config


def setup_application(notion_config):
    """设置 Telegram 应用并添加处理器。"""
    logging.info("Application starting...")
    # 创建 Application 并传入你的 bot token。
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 添加处理器
    logging.info("Adding command and message handlers...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    bound_handle_any_message = partial(handle_any_message, notion_config=notion_config)

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, bound_handle_any_message))
    logging.info("Handlers added.")

    application.post_init = post_init

    return application


def start(update, context):
    """处理 /start 命令"""
    update.message.reply_text('Welcome to the bot!')

def help_command(update, context):
    """处理 /help 命令"""
    update.message.reply_text('Here is how you can use the bot...')

async def set_webhook(application):
    """设置 Telegram 机器人的 Webhook URL。"""
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        try:
            await application.bot.set_webhook(webhook_url)
            logging.info(f"Webhook URL 设置为: {webhook_url}")
        except Exception as e:
            logging.error(f"设置 Webhook URL 时发生错误: {e}")
    else:
        logging.warning("WEBHOOK_URL 环境变量未设置。")


async def post_init(app: Application):
    """设置命令列表和 Webhook (新增或修改)"""
    # 设置命令列表
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
    ])
    logging.info("Telegram commands set.")

    # 设置 Webhook (仅在 Webhook 模式下)
    if USE_WEBHOOK and WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logging.info(f"Webhook set to {WEBHOOK_URL}")
        except Exception as e:
            logging.error(f"Failed to set webhook: {e}")


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

@app.route('/save2notion', methods=['POST'])
async def save_to_notion_webhook():
    update = request.get_json()
    if update:
        logging.debug(f"Received webhook update: {update}")
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()  # 替换为你的实际 token
        await application.process_update(update)
    return 'ok'


def run_long_polling(app):
    logging.info("Starting bot in long polling mode...")
    logging.info("Bot started in long polling mode. Press Ctrl-C to stop.")
    # 运行 bot 直到用户按下 Ctrl-C
    app.run_polling(poll_interval=3)


def run_webhook(flask_app, webhook_url, port):
    if not webhook_url:
        logging.error("WEBHOOK_URL not found in environment variables. Webhook mode requires WEBHOOK_URL.")
        exit(1)

    logging.info(f"Starting Flask app for webhook on port {port}...")
    # 在生产环境中使用 Gunicorn 或 uWSGI
    flask_app.run(host='0.0.0.0', port=port)


def main():
    """运行 Telegram bot 应用的主函数。"""
    try:
        notion_config = load_and_validate_config()
        application = setup_application(notion_config)

        if USE_WEBHOOK:
            logging.info("USE_WEBHOOK is true. Running in webhook mode.")
            run_webhook(application, WEBHOOK_URL, PORT)
        else:
            logging.info("USE_WEBHOOK is false or not set. Running in long polling mode.")
            run_long_polling(application)

    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)

    logging.info("Application finished.")


if __name__ == '__main__':
    main()