import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# Telegram Bot的API令牌
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Notion API的版本和密钥
NOTION_VERSION = os.getenv('NOTION_VERSION', '2022-06-28')
NOTION_KEY = os.getenv('NOTION_KEY')
DATABASE_ID = os.getenv('DATABASE_ID')  # 数据库 ID
# PAGE_ID = os.getenv('DATABASE_ID')  # 暂时兼容
API_PAGE_ID = os.getenv('API_PAGE_ID') # 因为database模式不允许在数据库下直接创建块，因此配置一个接口专用的默认页面

# Webhook配置
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
PORT = int(os.getenv('PORT', 8443))
NOTION_TELEGRAM_BOT_WEBHOOK_URL = os.getenv('NOTION_TELEGRAM_BOT_WEBHOOK_URL')
NOTION_TELEGRAM_BOT_WEBHOOK_PATH = os.getenv('NOTION_TELEGRAM_BOT_WEBHOOK_PATH')
RAILWAY_WEBHOOK_PATH = os.getenv('RAILWAY_WEBHOOK_PATH', '/api/railway_webhook')  # Railway webhook 路径

# 授权用户列表
ADMIN_USERS_STR = os.environ.get("ADMIN_USERS", "")
ADMIN_USERS = list(map(int, ADMIN_USERS_STR.split(","))) if ADMIN_USERS_STR else []

AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = list(map(int, AUTHORIZED_USERS_STR.split(","))) if AUTHORIZED_USERS_STR else []

# 部署URL
DEPLOY_URL = os.getenv('DEPLOY_URL')

# 接口密钥，可设定为任意字符串
API_SECRET = os.getenv('API_SECRET')

# Railway webhook 密钥
RAILWAY_WEBHOOK_SECRET = os.getenv('RAILWAY_WEBHOOK_SECRET')

# 环境
ENV = os.getenv('ENV', 'prod')
# 调试模式
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# 日志配置
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.getenv('LOG_DIR', 'logs'))
PATH_OF_LOGS = os.getenv('PATH_OF_LOGS', 'logs')