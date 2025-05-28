"""Notion API 处理器"""
import datetime
import pytz
from typing import Optional, List, Union
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Header
from starlette.responses import JSONResponse
import json
import re

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

def is_url_list(content: str) -> bool:
    """检查内容是否为URL列表"""
    if not content:
        return False
    # 分割内容为逗号
    urls = content.strip().split(',')
    # 检查每个URL是否为有效的URL
    url_pattern = re.compile(r'^https?://\S+$')
    return all(url_pattern.match(url.strip()) for url in urls)

def get_error_category(error: Exception) -> str:
    """获取错误类别
    
    Args:
        error: 异常对象
        
    Returns:
        str: 错误类别描述
    """
    if isinstance(error, HTTPException):
        return "请求错误"
    elif "ClientResponseError" in str(type(error)):
        return "Notion API 错误"
    elif "ConnectionError" in str(type(error)):
        return "网络连接错误"
    elif "TimeoutError" in str(type(error)):
        return "请求超时"
    elif "FileNotFoundError" in str(type(error)):
        return "文件不存在"
    elif "PermissionError" in str(type(error)):
        return "权限错误"
    else:
        return "服务器内部错误"

async def api_upload(
    request: Request,
    page_id: Optional[str] = None,
    content: Optional[str] = None,
    files: Optional[List[UploadFile]] = None,
    urls: Optional[str] = None,
    x_signature: Optional[str] = None,
    append_only: bool = False
) -> dict:
    """统一的 API 上传方法
    
    Args:
        request: FastAPI 请求对象
        page_id: 目标页面ID
        content: 内容
        files: 上传的文件列表
        urls: URL列表字符串（逗号分隔）
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
                beijing_tz = pytz.timezone('Asia/Shanghai')
                now_beijing = datetime.datetime.now(beijing_tz)
                title = content[:15] if content else "from_api_" + now_beijing.strftime("%Y-%m-%d %H:%M:%S")
                new_page_id = await client.create_page(title)
                client.parent_page_id = new_page_id
                logger.info(
                    f"Created new Notion page - parent_page_id: {page_id} - "
                    f"new_page_id: {new_page_id} - title: {title}"
                )
            
            # 处理文件上传
            if urls:
                # 处理URL列表（逗号分隔）
                url_list = [url.strip() for url in urls.split(',') if url.strip()]
                for url in url_list:
                    message = Message(
                        content=content,
                        file_path=None,
                        file_name=None,
                        content_type=None,
                        external_url=url
                    )
                    await uploader.upload_message(message, append_only=True, external_url=url)
            elif files:
                # 处理文件列表
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
        # 记录详细错误日志
        logger.exception(f"Error uploading content - error: {e}")
        # 返回简化的错误信息
        error_category = get_error_category(e)
        raise HTTPException(status_code=500, detail=error_category)

@router.post(get_route("upload_via_api"))
async def upload_via_api(
    request: Request,
    page_id: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    urls: Optional[str] = Form(None),
    append_only: bool = Form(True),
    x_signature: str = Header(None, alias="X-Signature")
):
    """上传内容为页面
    
    Args:
        page_id: 父页面ID
        content: 页面内容
        files: 上传的文件列表
        urls: URL列表字符串（逗号分隔）
        x_signature: API 签名，在请求头中通过 X-Signature 传递
    """
    return await api_upload(
        request=request,
        page_id=page_id,
        content=content,
        files=files,
        urls=urls,
        x_signature=x_signature,
        append_only=append_only
    )