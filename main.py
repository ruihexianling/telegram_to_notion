import asyncio
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand, Update # 导入 Update 类
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from werkzeug.middleware.proxy_fix import ProxyFix

from config import * # 确保 config.py 存在且配置正确
from notion_bot_utils import handle_any_message # 确保这个文件存在且函数正确

# 配置日志记录
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG) # 提高 telegram 库的日志级别以便调试

# Notion 配置
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

# 初始化 Flask 应用
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1) # 处理 X-Forwarded-For 头，当在代理后运行时有用

# 全局的 Application 实例，所有处理器都将注册到这个实例上
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

def setup_handlers(app_instance: Application):
    """设置 Telegram 应用并添加处理器。"""
    logging.info("Setting up Telegram handlers...")

    # 添加命令处理器
    app_instance.add_handler(CommandHandler("start", start_command))
    app_instance.add_handler(CommandHandler("help", help_command))
    logging.info("Command handlers added.")

    # 使用偏函数将 NOTION_CONFIG 传递给 handle_any_message
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
    update_data = request.get_json() # 获取原始的 JSON 字典数据

    if not update_data:
        logging.warning("Received empty webhook update.")
        return 'ok' # Telegram 有时会发送空请求，直接返回 'ok'

    # 安全地获取 user_id 进行授权检查
    # 对于所有类型的 update，message 不一定存在，但 from_user 信息通常在 'message', 'edited_message', 'callback_query' 等字段中
    user_id = None
    if 'message' in update_data:
        user_id = update_data['message'].get('from', {}).get('id')
    elif 'callback_query' in update_data:
        user_id = update_data['callback_query'].get('from', {}).get('id')
    # 可以根据需要添加其他 update 类型

    if user_id is None:
        logging.warning(f"Could not extract user_id from update: {update_data.keys()}")
        # 对于无法识别的用户，依然返回 'ok'，但进行日志记录
        return 'ok'

    if not is_authorized(user_id):
        logging.warning(f"Unauthorized access attempt by user {user_id} with update: {update_data}")
        # 对于未经授权的访问，直接返回 HTTP 403 即可
        return jsonify({"error": "Unauthorized"}), 403 # 不再尝试 reply_text

    logging.debug(f"Received webhook update data: {update_data}")

    try:
        # 将字典转换为 telegram.Update 对象，需要传入全局的 application.bot
        update = Update.de_json(update_data, application.bot)
        # 使用转换后的 Update 对象进行处理
        await application.process_update(update)
        logging.info(f"Finished processing update for user {user_id}.")

    except Exception as e:
        logging.error(f"Error processing Telegram update: {e}", exc_info=True)
        # 返回一个错误响应给 Telegram，以便它知道处理失败了
        return jsonify({"error": "Failed to process update"}), 500
    
    return 'ok' # 成功接收并开始处理，即使处理失败也返回 'ok' 给 Telegram，防止重试过多


@app.route('/webhook_status', methods=['GET'])
async def webhook_status():
    """获取 Webhook 状态"""
    logging.info(f"Received /webhook_status request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")

    # 可以添加身份验证，例如一个简单的共享密钥
    # auth_header = request.headers.get('Authorization')
    # if not auth_header or auth_header != f"Bearer {WEBHOOK_SECRET}": # WEBHOOK_SECRET 需在 config.py 中定义
    #     logging.warning("Unauthorized attempt to access /webhook_status")
    #     return jsonify({"error": "Unauthorized"}), 401

    try:
        info = await application.bot.get_webhook_info() # 确保使用 await
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
    # 确保 AUTHORIZED_USERS 在 config.py 中被定义为一个包含用户ID的列表
    if user_id in AUTHORIZED_USERS:
        return True
    return False

# --- 主函数入口 ---

async def main():
    """运行 Telegram bot 应用的主函数。"""
    try:
        logging.info("Application starting...")

        # 设置 Telegram 应用并添加处理器 (使用全局 application 实例)
        setup_handlers(application)
        
        # 设置命令菜单 (使用全局 application 实例)
        await setup_commands(application)

        if USE_WEBHOOK:
            logging.info("USE_WEBHOOK is true. Preparing for webhook mode.")
            # 初始化 application 以便在 webhook 模式下接收更新
            await application.initialize()
            
            # 设置 Telegram Bot 的 webhook URL
            await set_webhook(application)

            logging.info(f"Starting Flask app with Hypercorn on port {PORT} for webhook mode.")
            # 在 main 函数的事件循环中直接启动 Hypercorn 服务器
            # 需要导入 hypercorn
            from hypercorn.config import Config
            from hypercorn.asyncio import serve as hypercorn_serve
            
            config = Config()
            config.bind = [f"0.0.0.0:{PORT}"]
            # Hypercorn 会在当前事件循环中运行并接管进程，持续处理 HTTP 请求
            await hypercorn_serve(app, config) 
            
        else:
            logging.info("USE_WEBHOOK is false or not set. Running in long polling mode.")
            # Long polling 模式不需要 Flask 应用，直接运行 bot
            await application.run_polling(poll_interval=2) # await run_polling
            logging.info("Bot stopped long polling.")

    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)

    logging.info("Application finished.")


if __name__ == "__main__":
    # 确保 config.py 中定义的变量可用
    # 例如：TELEGRAM_BOT_TOKEN, RENDER_WEBHOOK_URL, WEBHOOK_PATH, PORT, USE_WEBHOOK, AUTHORIZED_USERS
    # 如果这些变量没有定义，程序会在这里报错
    try:
        # 在这里进行一次简单的检查，确保关键配置变量存在
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