"""主应用模块"""
from urllib import request

import uvicorn
import asyncio
import signal
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from telegram.ext import Application
import os
import sys
import atexit
import psutil
import socket
from typing import Optional
import logging
from datetime import datetime

from config import *
from notion.bot.setup import setup_bot, setup_commands, setup_webhook, remove_webhook, after_bot_start, before_bot_stop, send_message_to_admins
from notion.webhook.handler import router as webhook_router
from notion.api.handler import router as api_router
from notion.api.logs import router as logs_router
from notion.bot.handler import router as bot_router
from notion.bot.application import set_application, get_application
from notion.routes import get_route
from notion.api.exceptions import setup_exception_handlers
from config import DEBUG, PORT, ENV

# 配置日志
logger = logging.getLogger(__name__)

# 初始化 FastAPI 应用
app = FastAPI(
    title="Notion Bot API",
    description="Telegram 消息转发到 Notion 的 API 服务",
    version="1.0.0",
    debug=DEBUG,
    # 生产环境下，将这些路由设为 None
    docs_url=None if ENV == "prod" else "/docs",
    redoc_url=None if ENV == "prod" else "/redoc",
    openapi_url=None if ENV == "prod" else "/openapi.json",
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
async def health_check(request: Request):
    """健康检查路由，用于 UptimeRobot 监控"""
    try:
        client_host = getattr(request.client, 'host', 'unknown')
        user_agent = request.headers.get('user-agent', 'unknown')
        x_forwarded_for = request.headers.get('x-forwarded-for', 'unknown')
        logger.info(f"Performing health check, from: {client_host}, user-agent: {user_agent}, x-forwarded-for: {x_forwarded_for}")
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
        # 记录应用关闭时的系统信息
        logger.info("Application is shutting down...")
        logger.info("Current process info:")
        log_system_info()
        
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
            # 确保 application 实例在停止前是运行状态
            if application.running:
                await application.stop()
                try:
                    if ENV == 'dev':
                        # 移除 webhook
                        await remove_webhook(application)
                except Exception as e:
                    logger.error(f"Failed to remove webhook: {e}")
                logger.debug("Shutting down bot application")
                await application.shutdown()
        except Exception as e:
            logger.error(f"Failed to shutdown application: {e}")
        
        logger.info("Application shut down successfully")
        
    except Exception as e:
        logger.exception("Error during shutdown")
        # 不要抛出异常，确保清理工作完成

def log_system_info():
    """记录系统资源信息"""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=1)
        
        logger.info(f"System Info - PID: {os.getpid()}")
        logger.info(f"Memory Usage - RSS: {memory_info.rss / 1024 / 1024:.2f} MB, VMS: {memory_info.vms / 1024 / 1024:.2f} MB")
        logger.info(f"CPU Usage: {cpu_percent}%")
        
        # 记录系统负载
        load1, load5, load15 = psutil.getloadavg()
        logger.info(f"System Load - 1min: {load1:.2f}, 5min: {load5:.2f}, 15min: {load15:.2f}")
        
        # 记录系统内存
        system_memory = psutil.virtual_memory()
        logger.info(f"System Memory - Total: {system_memory.total / 1024 / 1024:.2f} MB, Available: {system_memory.available / 1024 / 1024:.2f} MB")
        
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")

def handle_exit(signum, frame):
    """处理退出信号"""
    import signal as _signal
    try:
        signal_name = _signal.Signals(signum).name
    except Exception:
        signal_name = str(signum)
    
    # 获取发送信号的进程信息
    try:
        parent = psutil.Process(os.getpid()).parent()
        if parent:
            parent_info = f" (来自父进程 {parent.pid} - {parent.name()})"
        else:
            parent_info = " (无父进程)"
    except Exception:
        parent_info = " (无法获取父进程信息)"
    
    # 获取当前进程信息
    try:
        process = psutil.Process(os.getpid())
        process_info = f"\n进程信息:\n"
        process_info += f"• PID: {process.pid}\n"
        process_info += f"• 进程名: {process.name()}\n"
        process_info += f"• 命令行: {' '.join(process.cmdline())}\n"
        process_info += f"• 内存使用: {process.memory_info().rss / (1024**2):.2f} MB\n"
        process_info += f"• CPU 使用率: {process.cpu_percent()}%\n"
        process_info += f"• 运行时间: {datetime.fromtimestamp(process.create_time()).strftime('%Y-%m-%d %H:%M:%S')}\n"
    except Exception as e:
        process_info = f"\n无法获取进程信息: {e}"
    
    # 获取系统负载
    try:
        load1, load5, load15 = psutil.getloadavg()
        load_info = f"\n系统负载:\n"
        load_info += f"• 1分钟: {load1:.2f}\n"
        load_info += f"• 5分钟: {load5:.2f}\n"
        load_info += f"• 15分钟: {load15:.2f}\n"
    except Exception as e:
        load_info = f"\n无法获取系统负载: {e}"
    
    logger.info(
        f"收到信号 {signal_name} ({signum}){parent_info}\n"
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        f"{process_info}"
        f"{load_info}"
    )
    
    # 这里不需要做任何事情，因为 uvicorn 会处理关闭事件

if __name__ == "__main__":
    # 记录启动时的系统信息
    logger.info("Starting application with system info:")
    log_system_info()
    
    # 注册信号处理器
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, handle_exit)
    if hasattr(signal, 'SIGQUIT'):
        signal.signal(signal.SIGQUIT, handle_exit)
    
    # 注册退出处理
    atexit.register(lambda: logger.info("Application exited through atexit"))
    
    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,  # 禁用热重载
        workers=1,  # 使用单个工作进程
        log_level="info" if not DEBUG else "debug",
        proxy_headers=True,  # 启用代理头
        forwarded_allow_ips="*"  # 允许所有代理IP
    )