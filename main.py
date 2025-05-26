import logging
import shutil
import tempfile
from typing import Optional

import uvicorn

from fastapi import FastAPI, Request, status, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Update

from config import *
from notion_bot_utils import upload_as_block, save_upload_file_temporarily
from bot_setup import setup_bot

# === 配置日志 ===
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('telegram').setLevel(logging.DEBUG)

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

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

# === 设置 Webhook ===
async def set_webhook():
    webhook_url = f"{RENDER_WEBHOOK_URL.rstrip('/')}/{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    logging.info(f"Webhook URL 设置为: {webhook_url}")

# === API 路由 ===
@app.get("/")
async def root():
    return PlainTextResponse("Hello, World!")

@app.get("/healthz")
async def healthz(request: Request):
    logging.info(f"Received Health check: {request.client.host} {request.method} {request.url.path}")
    return JSONResponse({"status": "ok"})

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "processed"})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": str(e)})

@app.get("/webhook_status")
async def webhook_status():
    
    info = await application.bot.get_webhook_info()
    return JSONResponse({
        "webhook_url": info.url,
        "pending_updates_count": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message,
        "max_connections": info.max_connections,
        "allowed_updates": info.allowed_updates
    })

# === Notion 上传 API ===
class UploadPayload(BaseModel):
    title: str
    content: Optional[str] = None
    file: Optional[UploadFile] = File(None)

@app.post("/api/upload_as_block")
async def api_upload(
    title: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = Form(None)
):
    logging.info(f"Received API upload request: title='{title}', content_provided={content is not None}, file_provided={file is not None}")

    if not content and not file:
        logging.warning("API upload request failed: Neither content nor file provided.")
        raise HTTPException(status_code=400, detail="Either 'content' or 'file' must be provided")

    temp_dir = None
    file_path = None
    file_name = None
    content_type = None

    try:
        if file:
            # Use the new helper function to save the file temporarily
            temp_dir = tempfile.mkdtemp()
            file_path, file_name, content_type = await save_upload_file_temporarily(file, temp_dir=temp_dir)
            logging.info(f"File saved temporarily: {file_path}")

        # Call the unified upload_as_block function
        await upload_as_block(
            title=title,
            content=content, # Pass content even if file is present, upload_as_block handles it
            file_path=file_path,
            file_name=file_name,
            content_type=content_type
        )

        logging.info("API upload successful.")
        return JSONResponse(status_code=200, content={"message": "Content/File uploaded successfully"})

    except Exception as e:
        logging.error(f"API upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload content/file: {e}")
    finally:
        # Clean up the temporary directory and its contents if it was created
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_e:
                logging.error(f"Error cleaning up temporary directory {temp_dir}: {cleanup_e}", exc_info=True)

@app.on_event("startup")
async def startup_event():
    await application.initialize()

    if USE_WEBHOOK:
        await set_webhook()
        logging.info("✅ Webhook mode enabled.")

        
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False, forwarded_allow_ips="*")
