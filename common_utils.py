
from urllib.request import Request
from config import API_SECRET, AUTHORIZED_USERS

def verify_signature(signature: str,request: Request) -> bool:
    # 具体校验逻辑待实现
    return signature == API_SECRET

def is_user_authorized(user_id: int) -> bool:
    """检查用户是否有权限使用机器人"""
    return user_id in AUTHORIZED_USERS
