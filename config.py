import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

NOTION_KEY = os.getenv('NOTION_KEY', 'your_notion_key_here')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'your_telegram_token_here')
NOTION_VERSION = '2022-06-28'  # 使用当前支持的API版本
PAGE_ID= os.getenv('PAGE_ID', 'your_page_id_here')  # 修正从PAGE_ID环境变量读取
