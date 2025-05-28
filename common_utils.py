from urllib.request import Request
from functools import wraps
from fastapi import HTTPException

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
    async def wrapper(*args, **kwargs):
        # 检查是否是 Telegram 机器人命令
        update = next((arg for arg in args if isinstance(arg, Update)), None)
        if update:
            user_id = update.effective_user.id
            if not is_admin(user_id):
                await update.message.reply_text(
                    "⚠️ 抱歉，此命令仅限管理员使用。\n"
                    "如果您需要管理员权限，请联系系统管理员。"
                )
                logger.warning(f"非管理员用户尝试访问管理员接口{func.__name__} - user_id: {user_id} - 用户名: {update.effective_user.username}")
                return
            return await func(*args, **kwargs)
            
        # API 接口权限验证
        request = next((arg for arg in args if isinstance(arg, Request)), None)
        if not request:
            raise HTTPException(status_code=400, detail="无法获取请求对象")
            
        user_id = request.state.user_id if hasattr(request.state, 'user_id') else None
        if not user_id:
            raise HTTPException(status_code=401, detail="未获取到用户ID")
            
        if not is_admin(user_id):
            logger.warning(f"非管理员用户尝试访问管理员接口{func.__name__} - user_id: {user_id} - 用户名: {request.effective_user.username}")
            raise HTTPException(status_code=403, detail="需要管理员权限")
            
        return await func(*args, **kwargs)
    return wrapper

# 装饰器：授权用户可执行
def auth_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 检查是否是 Telegram 机器人命令
        update = next((arg for arg in args if isinstance(arg, Update)), None)
        if update:
            user_id = update.effective_user.id
            if not is_auth_user(user_id):
                await update.message.reply_text(
                    "⚠️ 抱歉，您没有使用此功能的权限。\n"
                    "如果您需要使用此功能，请联系系统管理员获取授权。"
                )
                logger.warning(f"未授权用户尝试访问接口{func.__name__} - user_id: {user_id} - 用户名: {update.effective_user.username}")
                return
            return await func(*args, **kwargs)
            
        # API 接口权限验证
        request = next((arg for arg in args if isinstance(arg, Request)), None)
        if not request:
            raise HTTPException(status_code=400, detail="无法获取请求对象")
            
        user_id = request.state.user_id if hasattr(request.state, 'user_id') else None
        if not user_id:
            raise HTTPException(status_code=401, detail="未获取到用户ID")
            
        if not is_auth_user(user_id):
            logger.warning(f"未授权用户尝试访问接口{func.__name__} - user_id: {user_id} - 用户名: {update.effective_user.username}")
            raise HTTPException(status_code=403, detail="需要授权用户权限")
            
        return await func(*args, **kwargs)
    return wrapper
    