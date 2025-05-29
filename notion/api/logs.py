"""日志API路由模块"""
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import JSONResponse

from logger import get_recent_logs, setup_logger
from ..routes import get_route
from .auth import require_api_key

# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

@router.get(get_route("notion_telegram_logs"))
@require_api_key()
async def get_logs(
    hours: int = 24,
    limit: int = 100,
    request: Request = None
) -> JSONResponse:
    """获取近期日志
    
    Args:
        hours: 获取多少小时内的日志，默认24小时
        limit: 最多返回多少条日志，默认100条
        request: FastAPI请求对象，用于获取客户端IP等信息
    
    Returns:
        JSONResponse: 包含日志内容的响应
    """
    try:
        # 获取客户端IP
        client_ip = request.client.host if request and request.client else "unknown"
        
        # 记录访问日志
        logger.info(f"Log access request from IP: {client_ip}")
        
        # 获取日志
        logs = get_recent_logs(hours=hours, limit=limit)
        
        return JSONResponse({
            "status": "success",
            "data": {
                "logs": logs,
                "total": len(logs),
                "hours": hours,
                "limit": limit,
                "timestamp": datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.exception(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 