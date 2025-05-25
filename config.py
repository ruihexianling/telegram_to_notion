import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'your_telegram_token_here')

NOTION_VERSION = '2022-06-28'  # 使用当前支持的API版本
NOTION_KEY = os.getenv('NOTION_KEY', 'your_notion_key_here')
PAGE_ID= os.getenv('PAGE_ID', 'your_page_id_here')  # 修正从PAGE_ID环境变量读取

USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
PORT = int(os.getenv('PORT', 8443))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'your_webhook_url_here')

AUTHORIZED_USERS = os.getenv('AUTHORIZED_USERS', '').split(',')