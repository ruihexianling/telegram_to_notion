import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# Telegram Bot的API令牌
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Notion API的版本和密钥
NOTION_VERSION = '2022-06-28'  # 使用当前支持的API版本
NOTION_KEY = os.getenv('NOTION_KEY')
PAGE_ID= os.getenv('PAGE_ID')  # 替换为你的Notion页面ID

# Webhook配置
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
PORT = int(os.getenv('PORT', 8443))
NOTION_TELEGRAM_BOT_WEBHOOK_URL = os.getenv('NOTION_TELEGRAM_BOT_WEBHOOK_URL')
NOTION_TELEGRAM_BOT_WEBHOOK_PATH = os.getenv('NOTION_TELEGRAM_BOT_WEBHOOK_PATH')

# 授权用户列表
ADMIN_USERS_STR = os.environ.get("ADMIN_USERS", "")
ADMIN_USERS = list(map(int, ADMIN_USERS_STR.split(","))) if ADMIN_USERS_STR else []


AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = list(map(int, AUTHORIZED_USERS_STR.split(","))) if AUTHORIZED_USERS_STR else []

# 
DEPLOY_URL = os.getenv('DEPLOY_URL')

# 接口密钥，可设定为任意字符串
API_SECRET = os.getenv('API_SECRET')

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'