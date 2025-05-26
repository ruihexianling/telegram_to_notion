import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from telegram import Update
from bot_setup import setup_bot
from config import *
import json
from datetime import datetime

# === 设置 Webhook ===
async def set_webhook(application):
    webhook_url = f"{RENDER_WEBHOOK_URL.rstrip('/')}/{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    logging.info(f"Webhook URL 设置为: {webhook_url}")

# === 处理 来自tg bot的Webhook 请求 ===
async def telegram_webhook(request: Request, application):
    try:
        logging.info(f"Received update: {request.url.path}, IP: {request.client.host}, User-Agent: {request.headers.get('user-agent')}")
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "processed"})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": str(e)})

# === Webhook 状态检查 ===
async def webhook_status():
    status = {"status": "active", "timestamp": datetime.now()}
    return JSONResponse(json.dumps(status, default=str))