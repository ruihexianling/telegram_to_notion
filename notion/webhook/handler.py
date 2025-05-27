"""Notion Webhook 处理器"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import JSONResponse

from ..api.client import NotionClient
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig


from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

# @router.post("/webhook")
async def handle_webhook(request: Request):
    """处理 Notion webhook 请求"""
    try:
        # 验证签名
        signature = request.headers.get("x-notion-signature")
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")
            
        # 获取请求体
        body = await request.body()
        
        # 验证签名
        if not verify_signature(body, signature, NOTION_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")
            
        # 解析请求体
        data = await request.json()
        
        # 处理 webhook 事件
        event_type = data.get("type")
        if event_type == "page_updated":
            await handle_page_update(data)
        elif event_type == "page_created":
            await handle_page_created(data)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
            
        return JSONResponse({"status": "success"})
        
    except Exception as e:
        logger.exception(f"Error handling webhook - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def handle_page_update(data: dict):
    """处理页面更新事件"""
    try:
        page_id = data.get("page_id")
        if not page_id:
            logger.warning("Missing page_id in webhook data")
            return
            
        # 创建 Notion 客户端
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': page_id
        })
        
        async with NotionClient(config) as client:
            # 获取页面内容
            page = await client.get_page(page_id)
            title = page.get('properties', {}).get('title', [{}])[0].get('text', {}).get('content', '')
            logger.info(
                f"Page updated - page_id: {page_id} - title: {title}"
            )
            
    except Exception as e:
        logger.exception(f"Error handling page update - page_id: {data.get('page_id')} - error: {e}")
        raise

async def handle_page_created(data: dict):
    """处理页面创建事件"""
    try:
        page_id = data.get("page_id")
        if not page_id:
            logger.warning("Missing page_id in webhook data")
            return
            
        # 创建 Notion 客户端
        config = NotionConfig({
            'NOTION_KEY': NOTION_KEY,
            'NOTION_VERSION': NOTION_VERSION,
            'PAGE_ID': page_id
        })
        
        async with NotionClient(config) as client:
            # 获取页面内容
            page = await client.get_page(page_id)
            title = page.get('properties', {}).get('title', [{}])[0].get('text', {}).get('content', '')
            logger.info(
                f"Page created - page_id: {page_id} - title: {title}"
            )
            
    except Exception as e:
        logger.exception(f"Error handling page creation - page_id: {data.get('page_id')} - error: {e}")
        raise