"""主应用模块"""
import uvicorn
import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from telegram.ext import Application

from config import *
from notion.bot.setup import setup_bot, setup_commands, setup_webhook, remove_webhook, after_bot_start, before_bot_stop
from notion.webhook.handler import router as webhook_router
from notion.api.handler import router as api_router
from notion.api.logs import router as logs_router
from notion.bot.handler import router as bot_router
from notion.bot.application import set_application, get_application
from notion.routes import get_route
from notion.api.exceptions import setup_exception_handlers

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 初始化 FastAPI 应用
app = FastAPI(
    title="Notion Bot API",
    description="Telegram 消息转发到 Notion 的 API 服务",
    version="1.0.0",
    # 根据DEBUG环境变量决定是否启用文档
    docs_url="/docs" if os.getenv("DEBUG", "").lower() in ("true", "1", "yes") else None,
    redoc_url="/redoc" if os.getenv("DEBUG", "").lower() in ("true", "1", "yes") else None,
    openapi_url="/openapi.json" if os.getenv("DEBUG", "").lower() in ("true", "1", "yes") else None
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置全局异常处理器
setup_exception_handlers(app)

# 添加路由
app.include_router(webhook_router)
app.include_router(api_router)
app.include_router(logs_router)
app.include_router(bot_router)

# API 路由
@app.get(get_route("root"))
async def root():
    """根路由"""
    return PlainTextResponse("Notion Bot API Service")

@app.get(get_route("health_check"))
@app.head(get_route("health_check"))
async def health_check():
    """健康检查路由，用于 UptimeRobot 监控"""
    try:
        logger.info("Performing health check")
        application = get_application()
        if not application:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "unhealthy",
                    "error": "Application not initialized"
                }
            )
        
        # 检查 webhook 状态
        webhook_info = await application.bot.get_webhook_info()
        if not webhook_info.url:
            logger.warning("Webhook URL is empty, attempting to reset")
            await setup_webhook(application, NOTION_TELEGRAM_BOT_WEBHOOK_URL + get_route('notion_telegram_webhook'))
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "webhook_info": len(webhook_info.url) > 0
            }
        )
    except Exception as e:
        logger.error(f"Health check failed - error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )

async def setup_webhook_with_retry(application: Application, webhook_url: str, max_retries: int = 3):
    """带重试机制的 webhook 设置"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Setting up webhook (attempt {attempt + 1}/{max_retries})")
            await setup_webhook(application, webhook_url)
            return True
        except Exception as e:
            logger.error(f"Failed to setup webhook (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)  # 等待5秒后重试
            else:
                raise

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    try:
        logger.info("Starting application")
        # 设置机器人
        application = setup_bot()
        
        # 设置全局 Application 实例
        set_application(application)
        
        # 初始化机器人
        logger.debug("Initializing bot application")
        await application.initialize()
        
        # 设置 webhook（带重试机制）
        notion_telegram_webhook = NOTION_TELEGRAM_BOT_WEBHOOK_URL + get_route('notion_telegram_webhook')
        logger.info(f"Setting webhook URL: {notion_telegram_webhook}")
        await setup_webhook_with_retry(application, notion_telegram_webhook)
        
        # 设置命令
        application = await setup_commands(application)

        # Send startup message to admin users
        await after_bot_start(application)
        
        logger.info("Bot started successfully with webhook")

        # 输出所有注册路由
        logger.info("Registered routes:")
        for route in app.routes:
            logger.info(f"  {route.path} - {route.methods}")
    except Exception as e:
        logger.exception("Failed to start bot")
        # 不要直接抛出异常，而是记录错误并继续运行
        # 这样即使 bot 启动失败，API 服务仍然可以运行
        logger.error("Bot initialization failed, but API service will continue running")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的事件处理"""
    try:
        logger.info("Shutting down application")
        # 停止机器人
        application = get_application()
        if not application:
            logger.warning("No application instance found during shutdown")
            return
    
        logger.debug("Stopping bot application")
        try:
            # send shutdown message to admin users
            await before_bot_stop(application)
        except Exception as e:
            logger.error(f"Failed to send shutdown message: {e}")

        try:
            # 移除 webhook
            await remove_webhook(application)
        except Exception as e:
            logger.error(f"Failed to remove webhook: {e}")

        try:
            # 确保 application 实例在停止前是运行状态
            if application.running:
                await application.stop()
                logger.debug("Shutting down bot application")
                await application.shutdown()
        except Exception as e:
            logger.error(f"Failed to shutdown application: {e}")
        
        logger.info("Application shut down successfully")
        
    except Exception as e:
        logger.exception("Error during shutdown")
        # 不要抛出异常，确保清理工作完成

if __name__ == "__main__":
    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        reload=DEBUG,  # 只在调试模式下启用热重载
        workers=1,  # 使用单个工作进程
        log_level="info" if not DEBUG else "debug"
    )