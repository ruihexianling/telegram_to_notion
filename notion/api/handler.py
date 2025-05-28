"""Notion API 处理器"""
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Header
from starlette.responses import JSONResponse
import json

from common_utils import verify_signature
from ..api.client import NotionClient
from ..core.message import Message
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
from ..routes import get_route
from ..utils.file_utils import save_upload_file_temporarily, cleanup_temp_file

from logger import setup_logger
from config import *
# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

async def api_upload(
    request: Request,
    page_id: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    files: Optional[List[UploadFile]] = None,
    x_signature: Optional[str] = None,
    append_only: bool = False
) -> dict:
    """统一的 API 上传方法
    
    Args:
        request: FastAPI 请求对象
        page_id: 目标页面ID
        content: 内容
        files: 上传的文件列表
        x_signature: API 签名
        append_only: 是否为追加模式
        
    Returns:
        dict: 包含上传结果的字典
    """
    try:
        # 验证签名
        if not x_signature:
            raise HTTPException(status_code=400, detail="Missing signature")
            
        # 验证签名
        if not verify_signature(x_signature, request):
            raise HTTPException(status_code=401, detail="Invalid signature")
            
        if not page_id:
            # 如果没有提供 page_id，使用默认的
            page_id = PAGE_ID
            
        # 创建 Notion 客户端
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': page_id
        })
        
        async with NotionClient(config) as client:
            # 创建上传器
            uploader = NotionUploader(client)
            
            if append_only:
                # 追加模式：使用现有页面
                client.parent_page_id = page_id
            else:
                # 非追加模式：创建新页面
                title = content[:15]
                new_page_id = await client.create_page(title)
                client.parent_page_id = new_page_id
                logger.info(
                    f"Created new Notion page - parent_page_id: {page_id} - "
                    f"new_page_id: {new_page_id} - title: {title}"
                )
            
            # 处理文件上传
            if files:
                for file in files:
                    # 保存文件到临时目录
                    file_path, file_name, content_type = await save_upload_file_temporarily(file)
                    try:
                        # 创建消息对象
                        message = Message(
                            content=content,
                            file_path=file_path,
                            file_name=file_name,
                            content_type=content_type
                        )
                        
                        # 上传消息
                        await uploader.upload_message(message, append_only=True)
                    finally:
                        # 清理临时文件
                        if file_path:
                            cleanup_temp_file(file_path)
            else:
                # 没有文件，只处理文本内容
                message = Message(
                    content=content,
                    file_path=None,
                    file_name=None,
                    content_type=None
                )
                
                # 上传消息
                await uploader.upload_message(message, append_only=True)
            
            # 返回新页面ID
            return {
                "status": "success",
                "page_id": client.parent_page_id,
                "page_url": f"https://www.notion.so/{client.parent_page_id.replace('-', '')}"
            }
                
    except Exception as e:
        logger.exception(f"Error uploading content - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(get_route("api_upload_page"))
async def upload_as_page(
    request: Request,
    page_id: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    files: list[UploadFile] = File(None),
    x_signature: str = Header(None, alias="X-Signature")
):
    """上传内容为页面
    
    Args:
        page_id: 父页面ID
        content: 页面内容
        files: 上传的文件列表
        x_signature: API 签名，在请求头中通过 X-Signature 传递
    """
    return await api_upload(
        request=request,
        page_id=page_id,
        content=content,
        files=files,
        x_signature=x_signature,
        append_only=False
    )

@router.post(get_route("api_upload_block"))
async def upload_as_block(
    request: Request,
    page_id: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    files: list[UploadFile] = File(None),
    x_signature: str = Header(None, alias="X-Signature")
):
    """上传内容为块
    
    Args:
        page_id: 目标页面ID
        content: 块内容
        files: 上传的文件列表
        x_signature: API 签名，在请求头中通过 X-Signature 传递
    """
    return await api_upload(
        request=request,
        page_id=page_id,
        content=content,
        files=files,
        x_signature=x_signature,
        append_only=True
    )
        