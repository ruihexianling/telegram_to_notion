"""主应用模块"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from telegram.ext import Application
from telegram import Bot

from config import *
from notion.bot.setup import setup_bot, setup_commands, setup_webhook, remove_webhook
from notion.webhook.handler import router as webhook_router
from notion.api.handler import router as api_router

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 初始化 FastAPI 应用
app = FastAPI(
    title="Notion Bot API",
    description="Telegram 消息转发到 Notion 的 API 服务",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加路由
app.include_router(webhook_router, prefix="/api")
app.include_router(api_router, prefix="/api")

# API 路由
@app.get("/")
async def root():
    """根路由"""
    return PlainTextResponse("Notion Bot API Service")

@app.get("/healthz")
@app.head("/healthz")
async def health_check():
    """健康检查路由，用于 UptimeRobot 监控"""
    try:
        # 获取当前应用实例
        application = Application.get_current()
        
        # 检查 webhook 状态
        webhook_info = await application.bot.get_webhook_info()
        
        # 返回健康状态
        return JSONResponse({
            "status": "healthy",
            "webhook": {
                "has_custom_certificate": webhook_info.has_custom_certificate,
                "pending_update_count": webhook_info.pending_update_count,
                "last_error_date": webhook_info.last_error_date,
                "last_error_message": webhook_info.last_error_message,
                "max_connections": webhook_info.max_connections,
                "ip_address": webhook_info.ip_address
            }
        })
    except Exception as e:
        logger.error(f"Health check failed - error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    """处理 Telegram webhook 请求"""
    try:
        update = await request.json()
        logger.debug(f"Received webhook update - update_id: {update.get('update_id')}")
        
        # 获取当前应用实例
        application = Application.get_current()
        # 处理更新
        await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.exception(f"Error processing webhook update - error: {e}")
        raise

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    try:
        logger.info("Starting application")
        # 设置机器人
        application = setup_bot()
        
        # 设置 webhook
        webhook_url = f"https://{WEBHOOK_URL}/{WEBHOOK_PATH}"
        logger.info(f"Setting webhook URL: {webhook_url}")
        
        # 初始化机器人
        logger.debug("Initializing bot application")
        await application.initialize()
        
        # 设置 webhook
        await setup_webhook(application, webhook_url)
        
        # 设置命令
        setup_commands(application)
        
        logger.info("Bot started successfully with webhook")
        
    except Exception as e:
        logger.exception("Failed to start bot")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的事件处理"""
    try:
        logger.info("Shutting down application")
        # 停止机器人
        application = Application.get_current()
        
        # 移除 webhook
        await remove_webhook(application)
        
        logger.debug("Stopping bot application")
        await application.stop()
        logger.debug("Shutting down bot application")
        await application.shutdown()
        
        logger.info("Bot stopped successfully")
        
    except Exception as e:
        logger.exception("Error stopping bot")
        raise

if __name__ == "__main__":
    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        reload=True
    )