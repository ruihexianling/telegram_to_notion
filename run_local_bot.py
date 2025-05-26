import logging
from config import *
from bot_setup import setup_bot

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)



if __name__ == "__main__":
    # Get bot token from environment variables
    bot_token = TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("BOT_TOKEN environment variable not set.")
    else:
        # Build the application
        application = setup_bot(bot_token)

        # Run the bot in polling mode
        logger.info("Starting bot in polling mode...")
        # Use run_polling for blocking polling execution
        application.run_polling(poll_interval=2.0)