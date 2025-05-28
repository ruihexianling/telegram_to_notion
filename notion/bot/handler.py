"""Telegram Bot 消息处理器"""
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, Application
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import JSONResponse

from ..api.client import NotionClient
from ..core.buffer import MessageBuffer
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
import config
from ..routes import get_route

from common_utils import is_user_authorized

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 创建全局配置
notion_config = NotionConfig({
    'NOTION_KEY': config.NOTION_KEY,
    'NOTION_VERSION': config.NOTION_VERSION,
    'PAGE_ID': config.PAGE_ID
})

# 创建全局消息缓冲区实例
message_buffer = MessageBuffer()

# 创建路由
router = APIRouter()

# 全局 Application 实例
_application: Optional[Application] = None

def set_application(application: Application):
    """设置全局 Application 实例"""
    global _application
    _application = application

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理所有消息"""
    message = update.message
    if not message:
        logger.warning("Received an update without a message object")
        return
    
    logger.info(
        f"Received a message - username: {update.effective_user.username} - "
        f"user_id: {update.effective_user.id}"
    )

    if not is_user_authorized(update.effective_user.id):
        await message.reply_text("您没有权限使用此功能")
        logger.warning(
            f"Unauthorized user attempted to use the bot - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id} - text_content: {message.text}"
        )
        return

    try:
        logger.debug(
            f"Creating Notion client and uploader - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id}"
        )
        async with NotionClient(notion_config) as client:
            uploader = NotionUploader(client)
            
            logger.debug(
                f"Adding message to buffer - username: {update.effective_user.username} - "
                f"user_id: {update.effective_user.id}"
            )
            # 将消息添加到缓冲区
            page_url = await message_buffer.add_message(
                update.effective_user.id,
                message,
                uploader,
                context.bot
            )
            
            # 如果是第一条消息，发送页面URL
            if page_url:
                logger.info(
                    f"First message saved to Notion, sending page URL - username: {update.effective_user.username} - "
                    f"user_id: {update.effective_user.id} - page_url: {page_url}"
                )
                await message.reply_text(f"您的消息已保存到Notion页面：{page_url}")
                message_buffer.buffers[update.effective_user.id]['first_reply_sent'] = True
                
    except Exception as e:
        error_msg = f"处理消息时发生错误: {str(e)}"
        logger.exception(
            f"{error_msg} - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id} - text_content: {message.text}"
        )
        await message.reply_text(f"❌ {error_msg}")

@router.post(get_route("api_telegram_webhook"))
async def telegram_webhook(request: Request):
    """处理 Telegram webhook 请求"""
    try:
        if not _application:
            raise HTTPException(status_code=500, detail="Application not initialized")
            
        # 解析更新
        update = Update.de_json(await request.json(), _application.bot)
        
        # 处理更新
        await _application.process_update(update)
        
        logger.info(
            f"Processed Telegram update - update_id: {update.update_id}"
        )
        
        return JSONResponse({"status": "success"})
        
    except Exception as e:
        logger.exception(f"Error processing Telegram update - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))