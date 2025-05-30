"""Notion API 处理器"""
import datetime
import pytz
from typing import Optional, List, Union, Dict, Any, Tuple
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Header, status
import re

from .auth import require_api_key
from .response import api_response
from ..api.client import NotionClient
from ..core.message import Message
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
from ..routes import get_route
from ..utils.file_utils import save_upload_file_temporarily, cleanup_temp_file
from ..api.exceptions import NotionFileUploadError

from logger import setup_logger
from config import *

# 配置日志
logger = setup_logger(__name__)

# 创建路由
router = APIRouter()

# 常量定义
BEIJING_TIMEZONE = 'Asia/Shanghai'
URL_PATTERN = re.compile(r'^https?://\S+$')
CONTENT_PREVIEW_LENGTH = 10
TITLE_LENGTH = 15
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
TIMESTAMP_MILLISECONDS = 3

# 错误类别映射
ERROR_CATEGORIES = {
    HTTPException: "请求错误",
    NotionFileUploadError: "文件上传错误",
    "ClientResponseError": "Notion API 错误",
    "ConnectionError": "网络连接错误",
    "TimeoutError": "请求超时",
    "FileNotFoundError": "文件不存在",
    "PermissionError": "权限错误"
}

# HTTP 状态码映射
HTTP_STATUS_CODES = {
    HTTPException: lambda e: e.status_code,
    NotionFileUploadError: lambda _: status.HTTP_400_BAD_REQUEST,
    "ClientResponseError": lambda _: status.HTTP_502_BAD_GATEWAY,
    "ConnectionError": lambda _: status.HTTP_503_SERVICE_UNAVAILABLE,
    "TimeoutError": lambda _: status.HTTP_504_GATEWAY_TIMEOUT,
    "FileNotFoundError": lambda _: status.HTTP_404_NOT_FOUND,
    "PermissionError": lambda _: status.HTTP_403_FORBIDDEN
}

def is_url_list(content: str) -> bool:
    """检查内容是否为URL列表
    
    Args:
        content: 要检查的内容
        
    Returns:
        bool: 是否为URL列表
    """
    if not content:
        return False
    urls = content.strip().split(',')
    return all(URL_PATTERN.match(url.strip()) for url in urls)

def get_error_category(error: Exception) -> str:
    """获取错误类别
    
    Args:
        error: 异常对象
        
    Returns:
        str: 错误类别描述
    """
    error_type = type(error).__name__
    for error_class, category in ERROR_CATEGORIES.items():
        if isinstance(error, error_class) or error_class in error_type:
            return category
    return "服务器内部错误"

def get_http_status_code(error: Exception) -> int:
    """获取HTTP状态码
    
    Args:
        error: 异常对象
        
    Returns:
        int: HTTP状态码
    """
    error_type = type(error).__name__
    for error_class, status_code_func in HTTP_STATUS_CODES.items():
        if isinstance(error, error_class) or error_class in error_type:
            return status_code_func(error)
    return status.HTTP_500_INTERNAL_SERVER_ERROR

def get_beijing_time() -> datetime.datetime:
    """获取北京时区的当前时间
    
    Returns:
        datetime.datetime: 北京时区的当前时间
    """
    beijing_tz = pytz.timezone(BEIJING_TIMEZONE)
    return datetime.datetime.now(beijing_tz)

def format_timestamp(dt: datetime.datetime) -> str:
    """格式化时间戳
    
    Args:
        dt: 日期时间对象
        
    Returns:
        str: 格式化后的时间戳
    """
    return dt.strftime(TIMESTAMP_FORMAT)[:-TIMESTAMP_MILLISECONDS]

def create_message(
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    file_name: Optional[str] = None,
    content_type: Optional[str] = None,
    external_url: Optional[str] = None,
    source: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_pinned: bool = False,
    source_url: Optional[str] = None,
    created_time: Optional[datetime.datetime] = None
) -> Message:
    """创建消息对象
    
    Args:
        content: 消息内容
        file_path: 文件路径
        file_name: 文件名
        content_type: 文件类型
        external_url: 外部URL
        source: 来源
        tags: 标签列表
        is_pinned: 是否置顶
        source_url: 源链接
        created_time: 创建时间
        
    Returns:
        Message: 消息对象
    """
    return Message(
        content=content,
        file_path=file_path,
        file_name=file_name,
        content_type=content_type,
        external_url=external_url,
        source=source or 'API',
        tags=tags or [],
        is_pinned=is_pinned,
        source_url=source_url,
        created_time=created_time
    )

def create_page_properties(
    source: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_pinned: bool = False,
    source_url: Optional[str] = None,
    created_time: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """创建页面属性
    
    Args:
        source: 来源
        tags: 标签列表
        is_pinned: 是否置顶
        source_url: 源链接
        created_time: 创建时间
        
    Returns:
        Dict[str, Any]: 页面属性字典
    """
    return {
        '来源': source if source is not None else 'API',
        '标签': tags or [],
        '是否置顶': is_pinned,
        '源链接': source_url,
        '创建时间': created_time,
        '文件数量': 0,  # 初始化为0，让 Message 对象来计算实际数量
        '链接数量': 0   # 初始化为0，让 Message 对象来计算实际数量
    }

async def handle_url_upload(
    uploader: NotionUploader,
    url: str,
    source: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_pinned: bool = False,
    source_url: Optional[str] = None,
    created_time: Optional[datetime.datetime] = None
) -> None:
    """处理URL上传
    
    Args:
        uploader: Notion上传器
        url: 要上传的URL
        source: 来源
        tags: 标签列表
        is_pinned: 是否置顶
        source_url: 源链接
        created_time: 创建时间
        
    Raises:
        HTTPException: URL上传失败
    """
    try:
        message = create_message(
            external_url=url,
            source=source,
            tags=tags,
            is_pinned=is_pinned,
            source_url=source_url,
            created_time=created_time
        )
        await uploader.upload_message(message, append_only=True, external_url=url)
    except Exception as e:
        logger.error(f"URL上传失败: {url}, 错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL上传失败: {url}, 错误: {str(e)}"
        )

async def handle_file_upload(
    uploader: NotionUploader,
    file: UploadFile,
    source: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_pinned: bool = False,
    source_url: Optional[str] = None,
    created_time: Optional[datetime.datetime] = None
) -> None:
    """处理文件上传
    
    Args:
        uploader: Notion上传器
        file: 要上传的文件
        source: 来源
        tags: 标签列表
        is_pinned: 是否置顶
        source_url: 源链接
        created_time: 创建时间
        
    Raises:
        HTTPException: 文件上传失败
    """
    file_path = None
    try:
        file_path, file_name, content_type = await save_upload_file_temporarily(file)
        message = create_message(
            file_path=file_path,
            file_name=file_name,
            content_type=content_type,
            source=source,
            tags=tags,
            is_pinned=is_pinned,
            source_url=source_url,
            created_time=created_time
        )
        await uploader.upload_message(message, append_only=True)
    except Exception as e:
        logger.error(f"文件上传失败: {file.filename}, 错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件上传失败: {file.filename}, 错误: {str(e)}"
        )
    finally:
        if file_path:
            cleanup_temp_file(file_path)

async def api_upload(
    request: Request,
    page_id: Optional[str] = None,
    content: Optional[str] = None,
    files: Optional[List[UploadFile]] = None,
    urls: Optional[str] = None,
    x_signature: Optional[str] = None,
    append_only: bool = False,
    source: Optional[str] = None,
    tags: Optional[str] = None,
    is_pinned: bool = False,
    source_url: Optional[str] = None
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
        source: 来源
        tags: 标签列表（逗号分隔）
        is_pinned: 是否置顶
        source_url: 源链接
        
    Returns:
        dict: API响应
        
    Raises:
        HTTPException: 上传失败
    """
    try:
        # 获取北京时区的当前时间
        now_beijing = get_beijing_time()
        
        # 安全地获取内容预览
        content_preview = content[:CONTENT_PREVIEW_LENGTH] if content else "None"
        # 安全地获取文件数量
        files_count = len(files) if files else 0
        # 安全地获取URL数量
        urls_count = len(urls.split(',')) if urls else 0
        
        logger.info(
            f"Received upload request - page_id: {page_id} - "
            f"content: {content_preview} - files: {files_count} - "
            f"urls: {urls_count} - append_only: {append_only} - "
            f"source: {source} - tags: {tags} - is_pinned: {is_pinned}"
        )
         
        if not page_id:
            # 如果没有提供 page_id，使用默认主页面PAGE_ID
            page_id = DATABASE_ID
            
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
                # 追加模式：使用默认接口通用页面 append_only = true
                client.parent_page_id = API_PAGE_ID
            else:
                # 非追加模式：创建新页面 append_only = false
                title = content[:TITLE_LENGTH] if content else "from_api"
                
                # 构建页面属性
                properties = create_page_properties(
                    source=source,
                    tags=tags.split(',') if tags else None,
                    is_pinned=is_pinned,
                    source_url=source_url,
                    created_time=now_beijing
                )
                
                new_page_id = await client.create_page(title, properties=properties)
                client.parent_page_id = new_page_id
                logger.info(
                    f"Created new Notion page - parent_page_id: {page_id} - "
                    f"new_page_id: {new_page_id} - title: {title}"
                )

            # 先处理文本内容
            # 每个消息前添加时间戳
            beijing_time = format_timestamp(now_beijing)
            content = f"[{beijing_time}]\n{content}" if content else f"[{beijing_time}]"
            message = create_message(
                content=content,
                source=source,
                tags=tags.split(',') if tags else None,
                is_pinned=is_pinned,
                source_url=source_url,
                created_time=now_beijing
            )
            # 上传文本消息
            await uploader.upload_message(message, append_only=True)
            
            # 处理文件上传
            if urls:
                # 处理URL列表（逗号分隔）
                url_list = [url.strip() for url in urls.split(',') if url.strip()]
                for url in url_list:
                    await handle_url_upload(
                        uploader=uploader,
                        url=url,
                        source=source,
                        tags=tags.split(',') if tags else None,
                        is_pinned=is_pinned,
                        source_url=source_url,
                        created_time=now_beijing
                    )
            elif files:
                # 处理文件列表
                for file in files:
                    await handle_file_upload(
                        uploader=uploader,
                        file=file,
                        source=source,
                        tags=tags.split(',') if tags else None,
                        is_pinned=is_pinned,
                        source_url=source_url,
                        created_time=now_beijing
                    )
            
            # 返回新页面ID
            data = {
                "page_id": client.parent_page_id,
                "page_url": f"https://www.notion.so/{client.parent_page_id.replace('-', '')}"
            }
            return api_response(data=data)
                
    except HTTPException as e:
        # 记录详细错误日志
        logger.exception(f"HTTP错误: {e.detail}")
        raise e
    except Exception as e:
        # 记录详细错误日志
        error_category = get_error_category(e)
        error_message = str(e)
        logger.exception(f"{error_category}: {error_message}")
        raise HTTPException(
            status_code=get_http_status_code(e),
            detail=f"{error_category}: {error_message}"
        )

@router.post(get_route("upload_via_api"))
@require_api_key()
async def upload_via_api(
    request: Request,
    page_id: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    urls: Optional[str] = Form(None),
    append_only: bool = Form(True),
    source: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    is_pinned: bool = Form(False),
    source_url: Optional[str] = Form(None),
    x_signature: str = Header(None, alias="X-Signature")
) -> dict:
    """上传内容为页面
    
    Args:
        request: FastAPI 请求对象
        page_id: 父页面ID
        content: 页面内容
        files: 上传的文件列表
        urls: URL列表字符串（逗号分隔）
        append_only: 是否为追加模式
        source: 来源
        tags: 标签列表（逗号分隔）
        is_pinned: 是否置顶
        source_url: 源链接
        x_signature: API 签名，在请求头中通过 X-Signature 传递
        
    Returns:
        dict: API响应
        
    Raises:
        HTTPException: 上传失败
    """
    return await api_upload(
        request=request,
        page_id=page_id,
        content=content,
        files=files,
        urls=urls,
        x_signature=x_signature,
        append_only=append_only,
        source=source,
        tags=tags,
        is_pinned=is_pinned,
        source_url=source_url
    )