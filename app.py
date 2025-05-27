"""主应用模块"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from telegram.ext import Application

from config import *
from notion.bot.setup import setup_bot
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
# app.include_router(webhook_router, prefix="/api")
app.include_router(api_router, prefix="/api")

# API 路由
@app.get("/")
async def root():
    """根路由"""
    return PlainTextResponse("Notion Bot API Service")

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    try:
        logger.info("Starting application")
        # 设置机器人
        application = setup_bot()
        
        # 启动机器人
        logger.debug("Initializing bot application")
        await application.initialize()
        logger.debug("Starting bot application")
        await application.start()
        logger.debug("Starting bot polling")
        await application.updater.start_polling()
        
        logger.info("Bot started successfully")
        
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