"""Telegram Bot 消息处理器"""
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from ..api.client import NotionClient
from ..core.buffer import MessageBuffer
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
import config


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

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理所有消息"""
    message = update.message
    if not message:
        logger.warning("Received an update without a message object")
        return
    
    logger.info(
        "Received a message",
        extra={
            'username': update.effective_user.username,
            'user_id': update.effective_user.id,
            'text_content': message.text
        }
    )

    if not is_user_authorized(update.effective_user.id):
        await message.reply_text("您没有权限使用此功能")
        logger.warning(
            "Unauthorized user attempted to use the bot",
            extra={
                'username': update.effective_user.username,
                'user_id': update.effective_user.id,
                'text_content': message.text
            }
        )
        return


    try:
        # 创建 Notion 客户端和上传器
        # config = NotionConfig(notion_config)  # 使用传入的配置
        logger.debug(
            "Notion client and uploader created",
            extra={
                'username': update.effective_user.username,
                'user_id': update.effective_user.id,
                'text_content': message.text
            }
        )
        async with NotionClient(notion_config) as client:
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
        logger.exception(error_msg)
        await message.reply_text(f"❌ {error_msg}")