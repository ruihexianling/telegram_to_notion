# import logging
from config import *

# Configure logging
from notion.bot.setup import setup_bot, setup_commands
from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)



if __name__ == "__main__":
    # Get bot token from environment variables
    bot_token = TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("BOT_TOKEN environment variable not set.")
    else:
        # Build the application
        application = setup_bot()

        # Run the bot in polling mode
        logger.info("Starting bot in polling mode...")
        setup_commands(application)
        # Use run_polling for blocking polling execution
        application.run_polling(poll_interval=2.0)
        
        # Stop the bot
        application.shutdown()