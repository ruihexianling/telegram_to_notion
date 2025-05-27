"""API 处理器模块"""
import tempfile
from typing import Optional
from fastapi import APIRouter, Request, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from config import *
from .client import NotionClient
from ..core.message import Message
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
from ..utils.file_utils import save_upload_file_temporarily, cleanup_temp_dir
from common_utils import verify_signature
from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

@router.post("/upload_as_page")
async def upload_as_page(
    request: Request,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = Form(None)
):
    """上传内容作为新页面"""
    logger.debug(
        f"Received upload_as_page request - title_length: {len(title)} - "
        f"has_content: {content is not None} - has_file: {file is not None}"
    )
    return await api_upload(request, title, content, file, append_only=False)

@router.post("/upload_as_block")
async def upload_as_block(
    request: Request,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = Form(None)
):
    """上传内容作为块"""
    logger.debug(
        f"Received upload_as_block request - title_length: {len(title)} - "
        f"has_content: {content is not None} - has_file: {file is not None}"
    )
    return await api_upload(request, title, content, file, append_only=True)

async def api_upload(
    request: Request,
    title: str,
    content: Optional[str] = None,
    file: Optional[UploadFile] = None,
    append_only: bool = False
):
    """API 上传处理"""
    # 验证签名
    signature = request.headers.get('X-Signature')
    if not verify_signature(signature, request):
        logger.warning(
            f"Invalid API signature - signature_length: {len(signature) if signature else 0} - "
            f"client_ip: {request.client.host}"
        )
        raise HTTPException(status_code=401, detail="Invalid signature")

    logger.info(
        f"Processing API upload request - title_length: {len(title)} - "
        f"has_content: {content is not None} - has_file: {file is not None} - "
        f"append_only: {append_only} - client_ip: {request.client.host}"
    )

    if not content and not file:
        logger.warning(
            f"Invalid API upload request: missing content and file - "
            f"client_ip: {request.client.host}"
        )
        raise HTTPException(status_code=400, detail="Either 'content' or 'file' must be provided")

    temp_dir = None
    try:
        # 创建消息对象
        message = Message(content=content)

        # 处理文件上传
        if file:
            logger.debug(
                f"Processing file upload - filename: {file.filename} - "
                f"content_type: {file.content_type} - client_ip: {request.client.host}"
            )
            temp_dir = tempfile.mkdtemp()
            file_path, file_name, content_type = await save_upload_file_temporarily(file, temp_dir=temp_dir)
            message.file_path = file_path
            message.file_name = file_name
            message.content_type = content_type
            logger.debug(
                f"File saved temporarily - content_type: {content_type} - "
                f"client_ip: {request.client.host}"
            )

        # 创建 Notion 客户端和上传器
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': PAGE_ID
        })
        
        async with NotionClient(config) as client:
            uploader = NotionUploader(client)
            
            # 上传消息
            page_id = await uploader.upload_message(message, append_only=append_only)
            
            logger.info(
                f"API upload completed successfully - page_id: {page_id[:8]}... - "
                f"append_only: {append_only} - client_ip: {request.client.host}"
            )
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Content/File uploaded successfully",
                    "page_url": f"https://www.notion.so/{page_id.replace('-', '')}"
                }
            )

    except Exception as e:
        logger.error(
            f"API upload failed - error_type: {type(e).__name__} - "
            f"client_ip: {request.client.host}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to upload content/file: {e}")
    finally:
        # 清理临时目录
        if temp_dir:
            logger.debug(
                f"Cleaning up temporary directory - client_ip: {request.client.host}"
            )
            cleanup_temp_dir(temp_dir) 