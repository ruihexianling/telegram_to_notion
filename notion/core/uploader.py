"""上传服务模块"""
import os
import asyncio
from typing import Optional, Dict, Any

import aiohttp

from ..api.client import NotionClient
from ..api.exceptions import NotionFileUploadError
from ..core.message import Message
from ..utils.file_utils import get_file_info, cleanup_temp_file
from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

class NotionUploader:
    """Notion 上传服务类"""
    def __init__(self, client: NotionClient):
        self.client = client
        self.supported_mime_types = {
            # 图片
            'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
            # 视频
            'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm',
            # 音频
            'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/ogg', 'audio/webm',
            # 文档
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            # 文本
            'text/plain', 'text/csv', 'text/markdown', 'text/html'
        }

    async def upload_message(self, message: Message, append_only: bool = False) -> str:
        """上传消息到 Notion"""
        try:
            logger.debug(
                f"Starting message upload to Notion - append_only: {append_only} - "
                f"has_file: {bool(message.file_path)} - has_content: {bool(message.content)}"
            )
            
            # 创建页面或使用现有页面
            if not append_only:
                page_id = await self.client.create_page(message.title)
                logger.info(f"Created new Notion page - page_id: {page_id[:8]}...")
            else:
                # 在 append_only 模式下，使用 client 的 parent_page_id
                page_id = self.client.parent_page_id
                if not page_id:
                    logger.error("Missing parent_page_id in append_only mode")
                    raise ValueError("在 append_only 模式下，必须设置 parent_page_id")
                logger.debug(f"Using existing Notion page - page_id: {page_id[:8]}...")

            # 处理文件上传
            if message.file_path:
                await self._handle_file_upload(page_id, message)

            # 处理文本内容
            if message.content:
                await self.client.append_text(page_id, message.content)
                logger.debug(f"Appended text content to Notion page - page_id: {page_id[:8]}...")

            return page_id
        except Exception as e:
            logger.error(
                f"Failed to upload message to Notion - error_type: {type(e).__name__} - "
                f"append_only: {append_only}",
                exc_info=True
            )
            raise

    async def _handle_file_upload(self, page_id: str, message: Message) -> None:
        """处理文件上传"""
        if not os.path.exists(message.file_path):
            logger.error("File not found - file_path: ***")  # 脱敏文件路径
            raise FileNotFoundError(f"File not found at {message.file_path}")

        # 获取文件信息
        file_name, file_extension, content_type = get_file_info(message.file_path)
        effective_file_name = message.file_name or file_name
        effective_content_type = message.content_type or content_type

        logger.debug(
            f"Processing file upload - file_extension: {file_extension} - "
            f"content_type: {content_type} - page_id: {page_id[:8]}..."
        )

        # 检查文件类型是否支持
        if effective_content_type not in self.supported_mime_types:
            logger.warning(
                f"Unsupported file type - content_type: {content_type} - "
                f"file_extension: {file_extension}"
            )
            raise NotionFileUploadError(f"Notion 不支持此类型的文件: {effective_file_name}")

        # 获取文件大小
        file_size = os.path.getsize(message.file_path)
        logger.info(
            f"File size information - file_size_bytes: {file_size} - "
            f"file_size_mb: {round(file_size / (1024 * 1024), 2)} - "
            f"content_type: {content_type}"
        )

        try:
            # 创建文件上传对象
            file_upload_id, upload_url, number_of_parts, mode = await self.client.create_file_upload(
                effective_file_name,
                effective_content_type,
                file_size
            )

            logger.debug(
                f"File upload object created - upload_mode: {mode} - "
                f"number_of_parts: {number_of_parts} - content_type: {content_type}"
            )

            # 上传文件
            if mode == "multi_part":
                await self._upload_multi_part_file(
                    message.file_path,
                    upload_url,
                    effective_content_type,
                    number_of_parts
                )
                await self.client.complete_multi_part_upload(file_upload_id)
                logger.info(
                    f"Multi-part file upload completed - number_of_parts: {number_of_parts} - "
                    f"content_type: {content_type}"
                )
            else:
                await self._upload_single_part_file(
                    message.file_path,
                    upload_url,
                    effective_content_type
                )
                logger.info(f"Single-part file upload completed - content_type: {content_type}")

            # 添加文件块到页面
            await self.client.append_file_block(
                page_id,
                file_upload_id,
                effective_file_name,
                effective_content_type
            )
            logger.info(
                f"File block appended to page - page_id: {page_id[:8]}... - "
                f"content_type: {content_type}"
            )

        except Exception as e:
            logger.error(
                f"File upload failed - error_type: {type(e).__name__} - "
                f"content_type: {content_type}",
                exc_info=True
            )
            raise NotionFileUploadError(f"文件上传失败: {str(e)}")

    async def _upload_single_part_file(
        self,
        file_path: str,
        upload_url: str,
        content_type: str
    ) -> None:
        """上传单部分文件"""
        logger.debug(f"Starting single-part file upload - content_type: {content_type}")
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=os.path.basename(file_path), content_type=content_type)
            await self.client._make_request(upload_url, method='POST', data=data)
        logger.debug(f"Single-part file upload completed - content_type: {content_type}")

    async def _upload_multi_part_file(
        self,
        file_path: str,
        upload_url: str,
        content_type: str,
        number_of_parts: int
    ) -> None:
        """上传多部分文件"""
        logger.debug(
            f"Starting multi-part file upload - number_of_parts: {number_of_parts} - "
            f"content_type: {content_type}"
        )
        
        file_size = os.path.getsize(file_path)
        part_size = (file_size + number_of_parts - 1) // number_of_parts

        tasks = []
        for part_number in range(1, number_of_parts + 1):
            start_byte = (part_number - 1) * part_size
            end_byte = min(part_number * part_size, file_size)
            
            task = self.client.upload_file_part(
                file_path,
                upload_url,
                content_type,
                part_number,
                start_byte,
                end_byte
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        logger.debug(
            f"Multi-part file upload completed - number_of_parts: {number_of_parts} - "
            f"content_type: {content_type}"
        ) 