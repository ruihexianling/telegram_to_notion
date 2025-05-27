import logging
from config import *

# Configure logging
from notion.bot.setup import setup_bot, setup_commands
from notion.utils.logger import setup_logger

logging.getLogger("httpx").setLevel(logging.WARNING)

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
        # Use run_polling for blocking polling execution
        application.run_polling(poll_interval=2.0)
        setup_commands(application)

        # Stop the bot
        application.shutdown()


if __name__ == "__main__":
    main()