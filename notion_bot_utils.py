"""Notion Bot 工具模块"""
import logging
import tempfile
from typing import Optional
from fastapi import UploadFile, HTTPException, Form
from httpcore import Request
from starlette.responses import JSONResponse
from telegram import Update
from telegram.ext import ContextTypes

from common_utils import verify_signature
from config import *
from bot_setup import is_user_authorized
from notion import (
    NotionConfig,
    NotionClient,
    NotionUploader,
    MessageBuffer,
    Message,
    save_upload_file_temporarily,
    cleanup_temp_dir
)

# 配置日志
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('httpcore.http11').setLevel(logging.ERROR)

# 创建全局配置
notion_config = NotionConfig({
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
})

# 创建全局消息缓冲区实例
message_buffer = MessageBuffer()

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE, notion_config: dict) -> None:
    """处理所有消息"""
    message = update.message
    if not message:
        logging.warning("Received an update without a message object.")
        return

    if not is_user_authorized(update.effective_user.id):
        await message.reply_text("您没有权限使用此功能。")
        logging.warning(f"Unauthorized user attempted to use the bot: {update.effective_user.username}, {update.effective_user.id}, Message: {message.text}")
        return

    try:
        # 创建 Notion 客户端和上传器
        config = NotionConfig(notion_config)  # 将字典转换为 NotionConfig 对象
        async with NotionClient(config) as client:
            uploader = NotionUploader(client)
            
            # 将消息添加到缓冲区
            page_url = await message_buffer.add_message(
                update.effective_user.id,
                message,
                uploader,
                context.bot
            )
            
            # 如果是第一条消息，发送页面URL
            if page_url:
                await message.reply_text(f"您的消息已保存到Notion页面：{page_url}")
                message_buffer.buffers[update.effective_user.id]['first_reply_sent'] = True
                
    except Exception as e:
        error_msg = f"处理消息时发生错误: {str(e)}"
        logging.exception(error_msg)
        await message.reply_text(f"❌ {error_msg}")

async def api_upload(request: Request, title: str = Form(...), content: Optional[str] = Form(None), file: Optional[UploadFile] = Form(None), append_only: bool = False):
    """API 上传处理"""
    # 验证签名
    signature = request.headers.get('X-Signature')
    if not verify_signature(signature, request):
        logging.debug(f"Invalid signature: {signature}")
        raise HTTPException(status_code=401, detail="Invalid signature")

    logging.info(f"Received API upload request: title='{title}', content_provided={content is not None}, file_provided={file is not None}")

    if not content and not file:
        logging.warning("API upload request failed: Neither content nor file provided.")
        raise HTTPException(status_code=400, detail="Either 'content' or 'file' must be provided")

    temp_dir = None
    try:
        # 创建消息对象
        message = Message(content=content)

        # 处理文件上传
        if file:
            temp_dir = tempfile.mkdtemp()
            file_path, file_name, content_type = await save_upload_file_temporarily(file, temp_dir=temp_dir)
            message.file_path = file_path
            message.file_name = file_name
            message.content_type = content_type

        # 创建 Notion 客户端和上传器
        async with NotionClient(notion_config) as client:
            uploader = NotionUploader(client)
            
            # 上传消息
            page_id = await uploader.upload_message(message, append_only=append_only)
            
            logging.info("API upload successful.")
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Content/File uploaded successfully",
                    "page_url": f"https://www.notion.so/{page_id.replace('-', '')}"
                }
            )

    except Exception as e:
        logging.error(f"API upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload content/file: {e}")
    finally:
        # 清理临时目录
        if temp_dir:
            cleanup_temp_dir(temp_dir)