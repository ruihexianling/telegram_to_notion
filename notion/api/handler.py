"""Notion API 处理器"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from starlette.responses import JSONResponse

from common_utils import verify_signature
from ..api.client import NotionClient
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
from ..routes import get_route

from logger import setup_logger
from config import *
# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

@router.post(get_route("api_upload_page"))
async def upload_as_page(
    request: Request,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    files: list[UploadFile] = File(None)
):
    """上传内容为页面"""
    try:
        # 验证签名
        signature = request.headers.get("X-Signature")
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")
            
        # 获取请求体
        body = await request.body()
        
        # 验证签名
        if not verify_signature(body, signature, API_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")
            
        # 创建 Notion 客户端
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': PAGE_ID
        })
        
        async with NotionClient(config) as client:
            # 创建上传器
            uploader = NotionUploader(client)
            
            # 上传内容
            page_id = await uploader.upload_as_page(
                title=title,
                content=content,
                files=files
            )
            
            logger.info(
                f"Content uploaded as page - page_id: {page_id} - title: {title}"
            )
            
            return JSONResponse({
                "status": "success",
                "page_id": page_id
            })
            
    except Exception as e:
        logger.exception(f"Error uploading content as page - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(get_route("api_upload_block"))
async def upload_as_block(
    request: Request,
    content: str = Form(...),
    files: list[UploadFile] = File(None)
):
    """上传内容为块"""
    try:
        # 验证签名
        signature = request.headers.get("x-notion-signature")
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")
            
        # 获取请求体
        body = await request.body()
        
        # 验证签名
        if not verify_signature(body, signature, NOTION_API_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")
            
        # 创建 Notion 客户端
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': NOTION_PAGE_ID
        })
        
        async with NotionClient(config) as client:
            # 创建上传器
            uploader = NotionUploader(client)
            
            # 上传内容
            block_id = await uploader.upload_as_block(
                content=content,
                files=files
            )
            
            logger.info(
                f"Content uploaded as block - block_id: {block_id}"
            )
            
            return JSONResponse({
                "status": "success",
                "block_id": block_id
            })
            
    except Exception as e:
        logger.exception(f"Error uploading content as block - error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 