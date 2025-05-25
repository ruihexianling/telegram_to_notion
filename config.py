import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

NOTION_VERSION = '2022-06-28'  # 使用当前支持的API版本
NOTION_KEY = os.getenv('NOTION_KEY')
PAGE_ID= os.getenv('PAGE_ID')  # 修正从PAGE_ID环境变量读取

USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
PORT = int(os.getenv('PORT', 8443))
RENDER_WEBHOOK_URL = os.getenv('RENDER_WEBHOOK_URL')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH')

AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = list(map(int, AUTHORIZED_USERS_STR.split(","))) if AUTHORIZED_USERS_STR else []
