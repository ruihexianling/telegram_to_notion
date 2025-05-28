# import logging
from config import *

# Configure logging
from notion.bot.setup import setup_bot, setup_commands
from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

logger.info("Application started.")

if __name__ == "__main__":
    # Get bot token from environment variables
    bot_token = TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Please set it to run the bot.")
        exit(1) # Exit if token is not set
    else:
        logger.debug("TELEGRAM_BOT_TOKEN is set.")
        # Build the application
        application = setup_bot()

        # Run the bot in polling mode
        logger.info("Starting bot in polling mode...")
        setup_commands(application)
        # Use run_polling for blocking polling execution
        application.run_polling(poll_interval=5.0)

        # Stop the bot
        logger.info("Bot is shutting down.")
        application.shutdown()
        logger.info("Application shut down successfully.")