"""上传服务模块"""
import os
import asyncio
from typing import Optional, Dict, Any
import mimetypes
import pytz
from datetime import datetime

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
            'text/plain', 'text/csv', 'text/html'
        }
        logger.debug(
            f"NotionUploader initialized - parent_page_id: {client.parent_page_id} - "
            f"supported_mime_types: {len(self.supported_mime_types)}"
        )

    async def upload_message(self, message: Message, append_only: bool = False, external_url: Optional[str] = None) -> str:
        """上传消息到 Notion
        
        Args:
            message: 消息对象
            append_only: 是否为追加模式
            external_url: 外部文件URL（如果提供，将使用external_url模式）
        """
        try:
            logger.info(
                f"Starting message upload to Notion - append_only: {append_only} - "
                f"has_file: {bool(message.file_path)} - has_content: {bool(message.content)} - "
                f"external_url: {external_url[:10] + '...' if external_url else None}"
            )
            
            # 获取当前时间
            beijing_tz = pytz.timezone('Asia/Shanghai')
            now_beijing = datetime.now(beijing_tz)
            
            # 创建页面或使用现有页面
            if not append_only:
                # 构建页面属性
                properties = {
                    '来源': message.source,
                    '标签': message.tags,
                    '是否置顶': message.is_pinned,
                    '源链接': message.source_url,
                    '创建时间': message.created_time,
                    '更新时间': now_beijing,
                    '文件数量': message.file_count or 0,
                    '链接数量': message.link_count or 0
                }
                
                # 验证父页面 ID
                parent_page_id = self.client.parent_page_id
                logger.debug(f"Using parent page ID: {parent_page_id}")
                
                # 创建新页面
                page_id = await self.client.create_page(
                    message.title,
                    properties=properties,
                    parent_page_id=parent_page_id
                )
                logger.info(f"Created new Notion page - page_id: {page_id[:8]}...")
            else:
                # 在 append_only 模式下，使用 client 的 parent_page_id
                page_id = self.client.parent_page_id
                if not page_id:
                    logger.error("Missing parent_page_id in append_only mode")
                    raise ValueError("在 append_only 模式下，必须设置 parent_page_id")
                logger.info(f"Using existing Notion page - page_id: {page_id[:8]}...")
                
                # 获取当前页面的属性
                page = await self.client.get_page(page_id)
                current_properties = page.get('properties', {})
                
                # 更新文件数量和链接数量，确保有默认值
                current_file_count = current_properties.get('文件数量', {}).get('number', 0) or 0
                current_link_count = current_properties.get('链接数量', {}).get('number', 0) or 0
                
                # 确保 message 的属性也有默认值
                message_file_count = message.file_count or 0
                message_link_count = message.link_count or 0
                
                # 构建更新的属性
                properties = {
                    '文件数量': current_file_count + message_file_count,
                    '链接数量': current_link_count + message_link_count,
                    '更新时间': now_beijing
                }
                
                # 更新页面属性
                await self.client.update_page(page_id, properties)
                logger.info(
                    f"Updated page properties - page_id: {page_id[:8]}... - "
                    f"new_file_count: {properties['文件数量']} - "
                    f"new_link_count: {properties['链接数量']}"
                )

            # 处理文本内容
            if message.content:
                await self.client.append_text(page_id, message.content)
                logger.debug(f"Appended text content to Notion page - page_id: {page_id[:8]}...")

            # 处理文件上传
            if message.file_path or external_url:
                await self._handle_file_upload(page_id, message, external_url)

            return page_id
        except Exception as e:
            logger.error(
                f"Failed to upload message to Notion - error_type: {type(e).__name__} - "
                f"append_only: {append_only}",
                exc_info=True
            )
            raise

    async def _handle_file_upload(self, page_id: str, message: Message, external_url: Optional[str] = None) -> None:
        """处理文件上传
        
        Args:
            page_id: 页面ID
            message: 消息对象
            external_url: 外部文件URL（如果提供，将使用external_url模式）
        """
        if external_url:
            # 使用 external_url 模式
            file_name = message.file_name or external_url.split('/')[-1]
            content_type = message.content_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            
            logger.info(
                f"Processing external URL upload - url: {external_url[:10]}... - "
                f"content_type: {content_type}"
            )
        else:
            # 使用普通上传模式
            if not os.path.exists(message.file_path):
                logger.error("File not found - file_path: ***")  # 脱敏文件路径
                raise FileNotFoundError(f"File not found at {message.file_path}")

            # 获取文件信息
            file_name, file_extension, content_type = get_file_info(message.file_path)
            file_name = message.file_name or file_name
            content_type = message.content_type or content_type

            logger.info(
                f"Processing file upload - file_extension: {file_extension} - "
                f"content_type: {content_type} - page_id: {page_id[:8]}..."
            )

            # 特殊处理 Markdown 文件
            if file_extension.lower() == 'md' or content_type == 'text/markdown':
                logger.info(f"Converting Markdown file to text content - file_name: {file_name}")
                try:
                    with open(message.file_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()
                    # 添加 Markdown 内容作为文本
                    await self.client.append_text(page_id, markdown_content)
                    logger.info(f"Successfully converted and appended Markdown content - file_name: {file_name}")
                    return
                except Exception as e:
                    logger.error(f"Failed to convert Markdown file - error_type: {type(e).__name__}", exc_info=True)
                    raise NotionFileUploadError(f"Markdown 文件处理失败: {str(e)}")

            # 检查文件类型是否支持
            if content_type not in self.supported_mime_types:
                logger.warning(
                    f"Unsupported file type - content_type: {content_type} - "
                    f"file_extension: {file_extension}"
                )
                raise NotionFileUploadError(f"Notion 不支持此类型的文件: {file_name}")

            # 获取文件大小
            file_size = os.path.getsize(message.file_path)
            if file_size == 0:
                logger.error(f"Empty file detected - file_name: {file_name}")
                raise NotionFileUploadError(f"文件为空，无法上传: {file_name}")

            logger.info(
                f"File size information - file_size_bytes: {file_size} - "
                f"file_size_mb: {round(file_size / (1024 * 1024), 2)} - "
                f"content_type: {content_type}"
            )

        try:
            # 创建文件上传对象
            file_upload_id, upload_url, number_of_parts, mode = await self.client.create_file_upload(
                file_name,
                content_type,
                file_size if not external_url else None,
                external_url
            )

            logger.info(
                f"File upload object created - upload_mode: {mode} - "
                f"number_of_parts: {number_of_parts} - content_type: {content_type}"
            )

            if not external_url:
                # 上传文件
                if mode == "multi_part":
                    await self._upload_multi_part_file(
                        message.file_path,
                        upload_url,
                        content_type,
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
                        content_type
                    )
                    logger.info(f"Single-part file upload completed - content_type: {content_type}")

            # 添加文件块到页面
            await self.client.append_file_block(
                page_id,
                file_upload_id,
                file_name,
                content_type
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