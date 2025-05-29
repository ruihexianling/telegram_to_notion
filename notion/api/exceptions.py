"""Notion API 异常类定义"""

class NotionAPIError(Exception):
    """Notion API 错误基类"""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)

class NotionConfigError(NotionAPIError):
    """Notion 配置错误"""
    pass

class NotionFileUploadError(NotionAPIError):
    """Notion 文件上传错误"""
    pass

class NotionPageError(NotionAPIError):
    """Notion 页面操作错误"""
    pass

"""Notion API 异常处理模块"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .response import api_response, ErrorCode

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数验证异常"""
    return api_response(error=exc)

async def validation_error_handler(request: Request, exc: ValidationError):
    """处理Pydantic验证异常"""
    return api_response(error=exc)

async def http_exception_handler(request: Request, exc: HTTPException):
    """处理HTTP异常"""
    return api_response(error=exc)

async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理Starlette HTTP异常（包括404）"""
    return api_response(error=exc)

def setup_exception_handlers(app):
    """设置全局异常处理器
    
    Args:
        app: FastAPI应用实例
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler) 