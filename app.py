"""主应用模块"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from telegram.ext import Application

from config import *
from notion.bot.setup import setup_bot, setup_commands, setup_webhook, remove_webhook
from notion.webhook.handler import router as webhook_router
from notion.api.handler import router as api_router
from notion.bot.handler import router as bot_router, set_application
from notion.routes import get_route

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
app.include_router(webhook_router)
app.include_router(api_router)
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
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy"
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

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    try:
        logger.info("Starting application")
        # 设置机器人
        application = setup_bot()
        
        # 设置全局 Application 实例
        set_application(application)
        
        # 设置 webhook
        notion_telegram_webhook = f"NOTION_TELEGRAM_BOT_WEBHOOK_URL+{get_route('notion_telegram_webhook')}"
        logger.info(f"Setting webhook URL: {notion_telegram_webhook}")
        
        # 初始化机器人
        logger.debug("Initializing bot application")
        await application.initialize()
        
        # 设置 webhook
        await setup_webhook(application, notion_telegram_webhook)
        
        # 设置命令
        application = await setup_commands(application)
        
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