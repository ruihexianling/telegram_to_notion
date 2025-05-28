"""Notion API 客户端"""
import logger
import aiohttp
from typing import Dict, Optional, Any, Tuple
from .exceptions import NotionAPIError, NotionFileUploadError, NotionPageError
from ..utils.config import NotionConfig
from logger import setup_logger
import asyncio

logger = setup_logger(__name__)

class NotionClient:
    """Notion API 客户端类"""
    def __init__(self, config: NotionConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._parent_page_id: Optional[str] = None

    @property
    def parent_page_id(self) -> str:
        """获取父页面 ID"""
        return self._parent_page_id or self.config.parent_page_id

    @parent_page_id.setter
    def parent_page_id(self, value: str):
        """设置父页面 ID"""
        self._parent_page_id = value

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        url: str,
        method: str = 'POST',
        payload: Optional[Dict] = None,
        data: Optional[aiohttp.FormData] = None,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        if not self._session:
            self._session = aiohttp.ClientSession()

        if data:
            headers = {
                "Authorization": f"Bearer {self.config.notion_key}",
                "Notion-Version": self.config.notion_version
            }
        else:
            headers = self.config.headers
            if content_type:
                headers["Content-Type"] = content_type

        logger.debug(
            f"Making Notion API request - method: {method} - "
            f"endpoint: {url.split('/')[-1]} - "
            f"has_payload: {bool(payload)} - has_data: {bool(data)}"
        )

        try:
            if method == 'POST':
                async with self._session.post(url, json=payload, headers=headers, data=data) as response:
                    return await self._handle_response(response, url)
            elif method == 'PATCH':
                async with self._session.patch(url, json=payload, headers=headers) as response:
                    return await self._handle_response(response, url)
            elif method == 'GET':
                async with self._session.get(url, headers=headers) as response:
                    return await self._handle_response(response, url)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")
        except aiohttp.ClientError as e:
            logger.error(
                f"Notion API request failed - method: {method} - "
                f"endpoint: {url.split('/')[-1]} - error_type: {type(e).__name__}",
                exc_info=True
            )
            raise NotionAPIError(f"Notion API 请求失败: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error in Notion API request - method: {method} - "
                f"endpoint: {url.split('/')[-1]} - error_type: {type(e).__name__}",
                exc_info=True
            )
            raise NotionAPIError(f"Notion API 请求发生意外错误: {str(e)}")

    async def _handle_response(self, response: aiohttp.ClientResponse, url: str) -> Dict[str, Any]:
        """处理 API 响应"""
        try:
            response.raise_for_status()
            return await response.json()
        except aiohttp.ClientResponseError as e:
            response_body = await response.text()
            logger.error(
                f"Notion API response error - status_code: {e.status} - "
                f"endpoint: {url.split('/')[-1]} - "
                f"error_type: {'file_upload' if 'file_uploads' in url else 'page_operation'}"
            )
            if 'file_uploads' in url:
                raise NotionFileUploadError(
                    f"Notion 文件上传失败: {e.message}",
                    status_code=e.status,
                    response_body=response_body
                )
            else:
                raise NotionPageError(
                    f"Notion 页面操作失败: {e.message}",
                    status_code=e.status,
                    response_body=response_body
                )

    async def create_page(self, title: str, content_text: Optional[str] = None) -> str:
        """创建 Notion 页面"""
        logger.debug(
            f"Creating Notion page - has_content: {bool(content_text)} - "
            f"title_length: {len(title)}"
        )
        
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {
                "type": "page_id",
                "page_id": self.parent_page_id
            },
            "properties": {
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            },
            "children": []
        }

        if content_text:
            payload["children"].append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": content_text
                            }
                        }
                    ]
                }
            })

        response = await self._make_request(url, method='POST', payload=payload)
        logger.info(f"Notion page created successfully - page_id: {response['id'][:8]}...")
        return response['id']

    async def append_text(self, page_id: str, content_text: str) -> None:
        """添加文本块到页面"""
        logger.debug(
            f"Appending text to Notion page - page_id: {page_id[:8]}... - "
            f"content_length: {len(content_text)}"
        )
        
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        payload = {
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": content_text
                                }
                            }
                        ]
                    }
                }
            ]
        }
        await self._make_request(url, method='PATCH', payload=payload)
        logger.debug(f"Text appended successfully - page_id: {page_id[:8]}...")

    async def create_file_upload(
        self,
        file_name: str,
        content_type: str,
        file_size: Optional[int] = None
    ) -> Tuple[str, str, Optional[int], Optional[str]]:
        """创建文件上传对象"""
        logger.debug(
            f"Creating file upload object - content_type: {content_type} - "
            f"file_size_mb: {round(file_size / (1024 * 1024), 2) if file_size else None}"
        )
        
        url = "https://api.notion.com/v1/file_uploads"
        
        mode = "single_part"
        number_of_parts = None
        payload = {"filename": file_name, "content_type": content_type, "mode": mode}
        
        if file_size and file_size > 20 * 1024 * 1024:  # 20MB
            mode = "multi_part"
            part_size = 10 * 1024 * 1024  # 10MB
            number_of_parts = (file_size + part_size - 1) // part_size
            payload = {
                "mode": mode,
                "number_of_parts": number_of_parts,
                "filename": file_name,
                "content_type": content_type
            }
            logger.debug(
                f"Using multi-part upload mode - number_of_parts: {number_of_parts} - "
                f"part_size_mb: {round(part_size / (1024 * 1024), 2)}"
            )
        
        response = await self._make_request(url, method='POST', payload=payload)
        logger.info(
            f"File upload object created - upload_id: {response['id'][:8]}... - "
            f"mode: {mode} - number_of_parts: {number_of_parts}"
        )
        return response['id'], response['upload_url'], number_of_parts, mode

    async def upload_file_part(
        self,
        file_path: str,
        upload_url: str,
        content_type: str,
        part_number: int,
        start_byte: int,
        end_byte: int
    ) -> None:
        """上传文件的一部分"""
        logger.debug(
            f"Uploading file part - part_number: {part_number} - "
            f"content_type: {content_type} - part_size: {end_byte - start_byte}"
        )
        
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            part_data = f.read(end_byte - start_byte)
            
            data = aiohttp.FormData()
            data.add_field('file', part_data, content_type=content_type)
            data.add_field('part_number', str(part_number))
            
            try:
                await self._make_request(upload_url, method='POST', data=data)
                logger.debug(
                    f"File part uploaded successfully - part_number: {part_number} - "
                    f"content_type: {content_type}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to upload file part - part_number: {part_number} - "
                    f"error_type: {type(e).__name__}",
                    exc_info=True
                )
                raise NotionFileUploadError(f"文件分片上传失败: {str(e)}") from e

    async def complete_multi_part_upload(self, file_upload_id: str) -> None:
        """完成多部分文件上传"""
        logger.debug(f"Completing multi-part upload - upload_id: {file_upload_id[:8]}...")
        
        url = f"https://api.notion.com/v1/file_uploads/{file_upload_id}/complete"
        await self._make_request(url, method='POST')
        
        logger.info(f"Multi-part upload completed - upload_id: {file_upload_id[:8]}...")

    async def append_file_block(
        self,
        page_id: str,
        file_upload_id: str,
        file_name: str,
        file_mime_type: str
    ) -> None:
        """添加文件块到页面"""
        logger.debug(
            f"Appending file block to page - page_id: {page_id[:8]}... - "
            f"upload_id: {file_upload_id[:8]}... - mime_type: {file_mime_type}"
        )
        
        # 等待文件上传完成
        await self.wait_for_file_upload(file_upload_id)
        
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        
        block_type = "file"
        for type_name, mime_types in {
            'image': {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'},
            'video': {'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'},
            'audio': {'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/ogg', 'audio/webm'},
            'pdf': {'application/pdf'}
        }.items():
            if file_mime_type in mime_types:
                block_type = type_name
                break
        
        payload = {
            "children": [
                {
                    "object": "block",
                    "type": block_type,
                    block_type: {
                        "type": "file_upload",
                        "file_upload": {
                            "id": file_upload_id
                        },
                        "caption": [
                            {
                                "type": "text",
                                "text": {
                                    "content": file_name
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        await self._make_request(url, method='PATCH', payload=payload)
        logger.info(
            f"File block appended successfully - page_id: {page_id[:8]}... - "
            f"block_type: {block_type} - mime_type: {file_mime_type}"
        )

    async def get_file_upload_status(self, file_upload_id: str) -> Dict[str, Any]:
        """获取文件上传状态
        
        Args:
            file_upload_id: 文件上传ID
            
        Returns:
            Dict: 包含文件上传状态的响应
        """
        url = f"https://api.notion.com/v1/file_uploads/{file_upload_id}"
        logger.debug(f"Getting file upload status - upload_id: {file_upload_id[:8]}...")
        
        response = await self._make_request(url, method='GET')
        logger.debug(
            f"File upload status - upload_id: {file_upload_id[:8]}... - "
            f"status: {response.get('status')}"
        )
        return response

    async def wait_for_file_upload(
        self,
        file_upload_id: str,
        max_retries: int = 6,
        initial_delay: float = 5.0
    ) -> Dict[str, Any]:
        """等待文件上传完成
        
        Args:
            file_upload_id: 文件上传ID
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间（秒）
            
        Returns:
            Dict: 包含文件上传状态的响应
            
        Raises:
            NotionFileUploadError: 如果文件上传失败或超时
        """
        logger.debug(
            f"Waiting for file upload - upload_id: {file_upload_id[:8]}... - "
            f"max_retries: {max_retries} - initial_delay: {initial_delay}"
        )
        
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                response = await self.get_file_upload_status(file_upload_id)
                status = response.get('status')
                
                if status == 'uploaded':
                    logger.info(f"File upload completed - upload_id: {file_upload_id[:8]}...")
                    return response
                elif status == 'failed':
                    error = response.get('file_import_result', {}).get('error', {})
                    logger.error(
                        f"File upload failed - upload_id: {file_upload_id[:8]}... - "
                        f"error: {error}"
                    )
                    raise NotionFileUploadError(
                        f"文件上传失败: {error.get('message', '未知错误')}"
                    )
                
                logger.debug(
                    f"File upload still pending - upload_id: {file_upload_id[:8]}... - "
                    f"attempt: {attempt + 1}/{max_retries} - delay: {delay}"
                )
                
                await asyncio.sleep(delay)
                delay *= 2  # 指数退避
                
            except Exception as e:
                logger.error(
                    f"Error checking file upload status - upload_id: {file_upload_id[:8]}... - "
                    f"attempt: {attempt + 1}/{max_retries} - error_type: {type(e).__name__}",
                    exc_info=True
                )
                if attempt == max_retries - 1:
                    raise NotionFileUploadError(f"等待文件上传超时: {str(e)}")
                await asyncio.sleep(delay)
                delay *= 2
        
        raise NotionFileUploadError("等待文件上传超时") 