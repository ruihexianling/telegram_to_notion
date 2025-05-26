import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from requests import request

from config import *
from notion_bot_utils import api_upload
from bot_setup import setup_bot
from webhook_handlers import set_webhook
import webhook_handlers

# === 配置日志 ===
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.INFO)

# === 初始化 FastAPI app ===
app = FastAPI()

# === 允许跨域（根据需要配置） ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

application = setup_bot(TELEGRAM_BOT_TOKEN)

# === Notion 上传 API ===
# class UploadPayload(BaseModel):
#     title: str
#     content: Optional[str] = None
#     file: Optional[UploadFile] = File(None)

# === API 路由 ===
@app.get("/")
async def root():
    return PlainTextResponse("Hello, World!")

@app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
async def healthz(request: Request):
    logging.info(f"Received Health check: {request.url.path}, IP: {request.client.host}, User-Agent: {request.headers.get('user-agent')}")
    return JSONResponse({"status": "ok"})

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    return await webhook_handlers.telegram_webhook(request, application)

@app.get("/webhook_status")
async def webhook_status():
    return await webhook_handlers.webhook_status()

@app.post("/api/upload_as_page")
async def api_upload_as_page(request: Request, title: str = Form(...), content: Optional[str] = Form(None), file: Optional[UploadFile] = Form(None)):
    return await api_upload(request, title, content, file, append_only=False)

@app.post("/api/upload_as_block")
async def api_upload_as_block(request: Request, title: str = Form(...), content: Optional[str] = Form(None), file: Optional[UploadFile] = Form(None)):
    return await api_upload(request, title, content, file, append_only=True)

@app.on_event("startup")
async def startup_event():
    await application.initialize()

    if USE_WEBHOOK:
        await set_webhook(application)
        logging.info("✅ Webhook mode enabled.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False, forwarded_allow_ips="*")