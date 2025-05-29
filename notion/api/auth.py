"""API认证模块"""
from functools import wraps
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from config import API_SECRET
from logger import setup_logger

logger = setup_logger(__name__)

def require_api_key():
    """API密钥验证装饰器
    
    验证请求头中的 X-API-Key 是否与配置的 API_SECRET 匹配
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for kwarg in kwargs.values():
                    if isinstance(kwarg, Request):
                        request = kwarg
                        break
            
            if not request:
                raise HTTPException(status_code=500, detail="Request object not found")
            
            # 获取请求头中的API密钥
            api_key = request.headers.get('X-API-Key')
            
            # 验证API密钥
            if not api_key or api_key != API_SECRET:
                logger.warning(f"Invalid API key attempt from IP: {request.client.host}")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid API key"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator 