"""路由配置模块"""
from typing import Dict

# API 路由前缀
API_PREFIX = "/api"

# Webhook 路由
WEBHOOK_PATH = "webhook"
TELEGRAM_WEBHOOK_PATH = "telegram/webhook"

# 健康检查路由
HEALTH_CHECK_PATH = "healthz"

# 根路由
ROOT_PATH = "/"

# 路由映射
ROUTES: Dict[str, str] = {
    # API 路由
    "api_webhook": f"{API_PREFIX}/{WEBHOOK_PATH}",

    # telegram webhook 路由
    "api_telegram_webhook": f"/{TELEGRAM_WEBHOOK_PATH}",
    
    # 健康检查路由
    "health_check": f"/{HEALTH_CHECK_PATH}",
    
    # 根路由
    "root": ROOT_PATH,
    
    # API 上传页面路由
    "api_upload_page": f"{API_PREFIX}/upload_page",
    "api_upload_block": f"{API_PREFIX}/upload_block",
}

def get_route(route_name: str) -> str:
    """获取路由路径
    
    Args:
        route_name: 路由名称
        
    Returns:
        str: 路由路径
    """
    if route_name not in ROUTES:
        raise ValueError(f"Unknown route name: {route_name}")
    return ROUTES[route_name]