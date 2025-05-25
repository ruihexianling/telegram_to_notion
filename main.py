import asyncio
import os
import logging
from functools import partial

from flask import Flask, jsonify, request
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from werkzeug.middleware.proxy_fix import ProxyFix

# Assuming config.py exists and contains these:
# TELEGRAM_BOT_TOKEN
# NOTION_KEY
# NOTION_VERSION
# PAGE_ID
# RENDER_WEBHOOK_URL
# WEBHOOK_PATH
# PORT
# USE_WEBHOOK
# AUTHORIZED_USERS
from config import *

# Make sure notion_bot_utils is correctly imported and handle_any_message is defined there
from notion_bot_utils import handle_any_message

# Configure logging
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.WARNING) # Suppress noisy httpx logs
logging.getLogger('httpcore').setLevel(logging.WARNING) # Suppress noisy httpcore logs


# Notion Configuration
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

# Initialize Flask application
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# Global Application instance
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

def setup_handlers(app_instance: Application):
    """Set up Telegram application and add handlers."""
    logging.info("Setting up Telegram handlers...")
    app_instance.add_handler(CommandHandler("start", start_command))
    app_instance.add_handler(CommandHandler("help", help_command))
    logging.info("Command handlers added.")

    bound_handle_any_message = partial(handle_any_message, notion_config=NOTION_CONFIG)
    app_instance.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, bound_handle_any_message))
    logging.info("Message handler added.")


async def setup_commands(app_instance: Application):
    """Set up the bot's command menu."""
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
    """Handle /start command"""
    logging.info(f"Received /start command from user: {update.message.from_user.id}")
    await update.message.reply_text('Welcome to the bot!')
    logging.info(f"Replied to /start command for user: {update.message.from_user.id}")


async def help_command(update: Update, context):
    """Handle /help command"""
    logging.info(f"Received /help command from user: {update.message.from_user.id}")
    await update.message.reply_text('Here is how you can use the bot...')
    logging.info(f"Replied to /help command for user: {update.message.from_user.id}")


async def set_webhook(app_instance: Application):
    """Set the Telegram bot's Webhook URL."""
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

# --- Flask Routes ---

@app.route('/')
def index():
    """Root route for health checks or simple access"""
    logging.info(f"Received root request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return 'Hello, World!'

@app.route('/healthz', methods=['GET'])
def health():
    """Health check route"""
    logging.info(f"Received health check request: {request.remote_addr} {request.method} {request.path} {request.user_agent}")
    return jsonify({
        "status": "ok"
    }), 200

@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
async def save_to_notion_webhook():
    """Process Telegram Webhook updates"""
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
        # If no user_id, it might be a channel post or other update type not requiring authorization
        # Decide if you want to allow all or strictly only authorized updates here
        # For now, we'll return 'ok' as it's not a critical failure for the webhook itself
        return 'ok'

    if not is_authorized(user_id):
        logging.warning(f"Unauthorized access attempt by user {user_id} with update: {update_data}")
        # Consider whether to return 403 or 'ok'. 'ok' is safer for Telegram to avoid retries.
        return 'ok' # Return 'ok' to Telegram even if unauthorized

    logging.debug(f"Received webhook update data: {update_data}")

    try:
        # Check if application is initialized before processing updates
        # This check is what the runtime error points to.
        # It *should* be initialized globally once on startup,
        # but this might catch race conditions or unexpected state.
        # However, the proper fix is to ensure it's initialized during app startup.
        # application._check_initialized() # This is an internal method, avoid direct call.
        
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        logging.info(f"Finished processing update for user {user_id}.")

    except Exception as e:
        logging.error(f"Error processing Telegram update: {e}", exc_info=True)
        # Return 'ok' to Telegram to prevent repeated attempts for a failed update
        return 'ok' 
    
    return 'ok'


@app.route('/webhook_status', methods=['GET'])
async def webhook_status():
    """Get Webhook status"""
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
    """Check if the user is in the authorized list"""
    # AUTHORIZED_USERS should be a tuple or set for efficient lookup
    if user_id in AUTHORIZED_USERS:
        return True
    return False

# --- Main entry point ---

async def initialize_and_start_webhook_app():
    """Initializes the Telegram Application and starts the Flask server."""
    logging.info("Starting application in Webhook mode...")
    
    # 1. Initialize the application FIRST
    await application.initialize()
    logging.info("Telegram Application initialized.")

    # 2. Set up handlers
    setup_handlers(application)
    
    # 3. Set up commands
    await setup_commands(application)

    # 4. Set webhook
    await set_webhook(application)

    logging.info(f"Starting Flask app with Hypercorn on port {PORT} for webhook mode.")
    from hypercorn.config import Config
    from hypercorn.asyncio import serve as hypercorn_serve
    
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    
    # Hypercorn requires a running asyncio loop to serve.
    # The current `asyncio.run()` will manage this.
    await hypercorn_serve(app, config)
    logging.info("Hypercorn server stopped.")

def start_polling_app():
    """Starts the bot in long polling mode."""
    logging.info("Starting application in Long Polling mode...")
    
    # For long polling, initialize is often implicitly handled or less strict,
    # but it's good practice to call it explicitly.
    # application.initialize() is not typically called directly before run_polling
    # because run_polling handles its own setup.
    
    setup_handlers(application)
    
    # Run setup_commands in the current event loop context before run_polling
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
        # Use asyncio.run to kick off the async webhook setup and server start
        asyncio.run(initialize_and_start_webhook_app())
    else:
        # For long polling, call the synchronous function
        start_polling_app()
    
    logging.info("Application finished.")