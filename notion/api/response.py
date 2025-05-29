"""API响应格式模块"""
from typing import Any, Dict, Optional, Union
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

# 错误码定义
class ErrorCode:
    SUCCESS = 0
    INVALID_API_KEY = 1001
    INVALID_PARAMS = 1002
    VALIDATION_ERROR = 1003  # 新增：参数验证错误
    NOT_FOUND = 1004  # 新增：资源未找到
    NOTION_API_ERROR = 2001
    FILE_UPLOAD_ERROR = 2002
    NETWORK_ERROR = 3001
    TIMEOUT_ERROR = 3002
    FILE_NOT_FOUND = 4001
    PERMISSION_ERROR = 4002
    INTERNAL_ERROR = 5001

# 错误码描述
ERROR_MESSAGES = {
    ErrorCode.SUCCESS: "成功",
    ErrorCode.INVALID_API_KEY: "无效的API密钥",
    ErrorCode.INVALID_PARAMS: "无效的参数",
    ErrorCode.VALIDATION_ERROR: "参数验证错误",  # 新增：参数验证错误描述
    ErrorCode.NOT_FOUND: "请求的资源不存在",  # 新增：资源未找到描述
    ErrorCode.NOTION_API_ERROR: "Notion API错误",
    ErrorCode.FILE_UPLOAD_ERROR: "文件上传错误",
    ErrorCode.NETWORK_ERROR: "网络连接错误",
    ErrorCode.TIMEOUT_ERROR: "请求超时",
    ErrorCode.FILE_NOT_FOUND: "文件不存在",
    ErrorCode.PERMISSION_ERROR: "权限错误",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误"
}

def get_error_code(error: Exception) -> int:
    """根据异常类型获取对应的错误码
    
    Args:
        error: 异常对象
        
    Returns:
        int: 错误码
    """
    if isinstance(error, (HTTPException, StarletteHTTPException)):
        if error.status_code == 401:
            return ErrorCode.INVALID_API_KEY
        elif error.status_code == 400:
            return ErrorCode.INVALID_PARAMS
        elif error.status_code == 404:
            return ErrorCode.NOT_FOUND
        else:
            return ErrorCode.INTERNAL_ERROR
    elif isinstance(error, (RequestValidationError, ValidationError)):
        return ErrorCode.VALIDATION_ERROR
    elif "ClientResponseError" in str(type(error)):
        return ErrorCode.NOTION_API_ERROR
    elif "ConnectionError" in str(type(error)):
        return ErrorCode.NETWORK_ERROR
    elif "TimeoutError" in str(type(error)):
        return ErrorCode.TIMEOUT_ERROR
    elif "FileNotFoundError" in str(type(error)):
        return ErrorCode.FILE_NOT_FOUND
    elif "PermissionError" in str(type(error)):
        return ErrorCode.PERMISSION_ERROR
    else:
        return ErrorCode.INTERNAL_ERROR

def get_validation_error_message(error: Union[RequestValidationError, ValidationError]) -> str:
    """获取验证错误的详细消息
    
    Args:
        error: 验证错误对象
        
    Returns:
        str: 错误消息
    """
    if isinstance(error, RequestValidationError):
        errors = error.errors()
    else:
        errors = error.errors()
    
    if not errors:
        return ERROR_MESSAGES[ErrorCode.VALIDATION_ERROR]
    
    # 获取第一个错误信息
    error_info = errors[0]
    error_type = error_info.get("type", "")
    error_loc = " -> ".join(str(x) for x in error_info.get("loc", []))
    error_msg = error_info.get("msg", "")
    
    return f"参数验证错误: {error_loc} - {error_msg}"

def success_response(data: Any = None, message: str = "成功") -> Dict:
    """生成成功响应
    
    Args:
        data: 响应数据
        message: 响应消息
        
    Returns:
        Dict: 响应字典
    """
    return {
        "code": ErrorCode.SUCCESS,
        "message": message,
        "data": data
    }

def error_response(error: Exception) -> Dict:
    """生成错误响应
    
    Args:
        error: 异常对象
        
    Returns:
        Dict: 响应字典
    """
    code = get_error_code(error)
    
    # 特殊处理验证错误
    if isinstance(error, (RequestValidationError, ValidationError)):
        message = get_validation_error_message(error)
    else:
        message = ERROR_MESSAGES.get(code, str(error))
    
    return {
        "code": code,
        "message": message,
        "data": None
    }

def api_response(data: Any = None, error: Optional[Exception] = None) -> JSONResponse:
    """生成API响应
    
    Args:
        data: 响应数据
        error: 异常对象
        
    Returns:
        JSONResponse: FastAPI响应对象
    """
    if error:
        response_data = error_response(error)
        status_code = 500
        if isinstance(error, (HTTPException, StarletteHTTPException)):
            status_code = error.status_code
        elif isinstance(error, (RequestValidationError, ValidationError)):
            status_code = 400
    else:
        response_data = success_response(data)
        status_code = 200
        
    return JSONResponse(
        content=response_data,
        status_code=status_code
    ) 