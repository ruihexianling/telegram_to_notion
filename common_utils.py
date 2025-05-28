from urllib.request import Request
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext

from config import ADMIN_USERS, AUTHORIZED_USERS, API_SECRET
# 配置日志
from logger import setup_logger

logger = setup_logger(__name__)

def verify_signature(signature: str,request: Request) -> bool:
    # 具体校验逻辑待实现
    return signature == API_SECRET

def is_admin(user_id: int) -> bool:
    """检查用户是否为管理员"""
    return user_id in ADMIN_USERS

def is_auth_user(user_id: int) -> bool:
    """检查用户是否为授权用户（包括管理员）"""
    return user_id in AUTHORIZED_USERS or is_admin(user_id)

# 装饰器：仅管理员可执行
def admin_required(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            update.message.reply_text("❌ 你没有权限执行此命令。")
            logger.warning(f"Non admin user attempted to access - username: {user.username} - user_id: {user.id}")
            return
        return func(update, context, *args, **kwargs)
    return wrapped

# 装饰器：授权用户可执行
def auth_required(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_auth_user(user_id):
            update.message.reply_text("❌ 你没有权限执行此命令。")
            logger.warning(f"Unauthorized user attempted to access - username: {user.username} - user_id: {user.id}")
            return
        return func(update, context, *args, **kwargs)
    return wrapped 
