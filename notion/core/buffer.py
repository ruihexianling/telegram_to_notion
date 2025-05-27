"""消息缓冲服务模块"""
import logging
import asyncio
from typing import Dict, Optional
from collections import defaultdict
from telegram import Message as TelegramMessage, Bot
from ..core.message import Message
from .uploader import NotionUploader

class MessageBuffer:
    """消息缓冲区管理器"""
    def __init__(self, buffer_timeout: int = 30):
        self.buffer_timeout = buffer_timeout
        self.buffers: Dict[int, Dict] = defaultdict(lambda: {
            'page_id': None,
            'task': None,
            'first_reply_sent': False,
            'media_group_id': None,
            'media_group_messages': {},
            'last_message': None,
            'uploader': None,
            'has_error': False
        })
        self.lock = asyncio.Lock()

    async def add_message(
        self,
        user_id: int,
        message: TelegramMessage,
        uploader: NotionUploader,
        bot: Optional[Bot] = None
    ) -> Optional[str]:
        """添加消息到缓冲区"""
        async with self.lock:
            buffer = self.buffers[user_id]
            buffer['uploader'] = uploader

            # 如果是第一条消息，创建新页面
            if not buffer['page_id']:
                notion_message = await Message.from_telegram_message(message, bot)
                try:
                    page_id = await uploader.upload_message(notion_message)
                    buffer['page_id'] = page_id
                    buffer['task'] = asyncio.create_task(self._process_buffer(user_id))
                    return f"https://www.notion.so/{page_id.replace('-', '')}"
                except Exception as e:
                    logging.error(f"Error creating page or processing first message: {e}", exc_info=True)
                    buffer['has_error'] = True
                    raise

            # 处理媒体组消息
            if message.media_group_id:
                if buffer['media_group_id'] != message.media_group_id:
                    buffer['media_group_id'] = message.media_group_id
                    buffer['media_group_messages'] = {message.message_id: message}
                else:
                    buffer['media_group_messages'][message.message_id] = message

            # 处理当前消息
            notion_message = await Message.from_telegram_message(message, bot)
            try:
                # 确保使用正确的页面ID
                if buffer['page_id']:
                    # 创建新的上传器实例，使用正确的页面ID
                    new_uploader = NotionUploader(uploader.client)
                    new_uploader.client.parent_page_id = buffer['page_id']
                    await new_uploader.upload_message(notion_message, append_only=True)
                else:
                    await uploader.upload_message(notion_message, append_only=True)
                buffer['has_error'] = False
            except Exception as e:
                logging.error(f"Error processing message: {e}", exc_info=True)
                buffer['has_error'] = True
                raise

            # 更新最后一条消息
            buffer['last_message'] = message

            # 重置缓冲区任务
            if buffer['task']:
                buffer['task'].cancel()
            buffer['task'] = asyncio.create_task(self._process_buffer(user_id))

            return None

    async def _process_buffer(self, user_id: int) -> None:
        """处理缓冲区超时"""
        try:
            await asyncio.sleep(self.buffer_timeout)
            
            async with self.lock:
                buffer = self.buffers[user_id]
                
                # 发送完结通知
                if buffer['page_id'] and buffer['last_message']:
                    try:
                        error_msg = "（部分文件上传失败）" if buffer.get('has_error', False) else ""
                        await buffer['last_message'].reply_text(
                            f"所有消息已处理完成{error_msg}，请查看Notion页面：https://www.notion.so/{buffer['page_id'].replace('-', '')}"
                        )
                    except Exception as e:
                        logging.error(f"Error sending completion message: {e}", exc_info=True)
                
                # 清理缓冲区
                del self.buffers[user_id]
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error in buffer processing: {e}", exc_info=True)
            async with self.lock:
                if user_id in self.buffers:
                    del self.buffers[user_id] 