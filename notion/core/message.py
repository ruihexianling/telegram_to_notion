"""消息模型模块"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
import pytz
import os
import tempfile
import re
from telegram import Bot

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

@dataclass
class Message:
    """消息基类"""
    content: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    external_url: Optional[str] = None
    content_type: Optional[str] = None
    media_group_id: Optional[str] = None
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    # 新增属性
    source: Optional[str] = None  # 来源
    tags: Optional[List[str]] = None  # 标签
    is_pinned: bool = False  # 是否置顶
    source_url: Optional[str] = None  # 源链接
    created_time: Optional[datetime] = None  # 创建时间
    file_count: int = 0  # 文件数量
    link_count: int = 0  # 链接数量

    def __post_init__(self):
        """初始化后处理"""
        # 初始化标签列表
        if self.tags is None:
            self.tags = []
        
        # 计算链接数量
        if self.content:
            self._count_links()
        
        # 如果有外部链接，增加链接计数
        if self.external_url:
            self.link_count += 1

    def _count_links(self) -> None:
        """计算文本中的链接数量"""
        if not self.content:
            return
            
        # URL正则表达式模式
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        
        # 查找所有URL
        urls = re.findall(url_pattern, self.content)
        self.link_count = len(urls)
        
        logger.debug(
            f"Counted links in content - message_id: {self.message_id} - "
            f"link_count: {self.link_count}"
        )

    @classmethod
    async def from_telegram_message(cls, message: Any, bot: Optional[Bot] = None) -> 'Message':
        """从 Telegram 消息创建消息对象"""
        logger.debug(
            f"Creating message from Telegram message - message_id: {message.message_id} - "
            f"has_text: {bool(message.text)} - has_caption: {bool(message.caption)} - "
            f"has_media: {bool(message.document or message.photo or message.video or message.audio or message.voice)}"
        )
        
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now_beijing = datetime.now(beijing_tz)
        
        # 创建消息对象
        msg = cls(
            content=message.text or message.caption,
            message_id=message.message_id,
            user_id=message.from_user.id if message.from_user else None,
            media_group_id=message.media_group_id,
            timestamp=now_beijing,
            created_time=now_beijing,
            source="Telegram",  # 设置来源为 Telegram
            source_url=f"https://t.me/c/{message.chat.id}/{message.message_id}" if message.chat.id else None,  # 设置源链接
            tags=[],  # 初始化标签列表
            file_count=0,  # 初始化文件计数
            link_count=0  # 初始化链接计数
        )

        # 处理文件
        if message.document:
            file = message.document
            msg.file_name = file.file_name
            msg.content_type = file.mime_type
            msg.file_count = 1
            logger.debug(
                f"Processing document message - message_id: {message.message_id} - "
                f"content_type: {file.mime_type}"
            )
        elif message.photo:
            file = message.photo[-1]  # 获取最大尺寸的照片
            msg.file_name = f"photo_{message.message_id}.jpg"
            msg.content_type = "image/jpeg"
            msg.file_count = 1
            logger.debug(
                f"Processing photo message - message_id: {message.message_id} - "
                f"photo_count: {len(message.photo)}"
            )
        elif message.video:
            file = message.video
            msg.file_name = file.file_name or f"video_{message.message_id}.mp4"
            msg.content_type = file.mime_type or "video/mp4"
            msg.file_count = 1
            logger.debug(
                f"Processing video message - message_id: {message.message_id} - "
                f"content_type: {msg.content_type}"
            )
        elif message.audio:
            file = message.audio
            msg.file_name = file.file_name or f"audio_{message.message_id}.mp3"
            msg.content_type = file.mime_type or "audio/mpeg"
            msg.file_count = 1
            logger.debug(
                f"Processing audio message - message_id: {message.message_id} - "
                f"content_type: {msg.content_type}"
            )
        elif message.voice:
            file = message.voice
            msg.file_name = f"voice_{message.message_id}.ogg"
            msg.content_type = "audio/ogg"
            msg.file_count = 1
            logger.debug(
                f"Processing voice message - message_id: {message.message_id}"
            )
        else:
            return msg

        # 下载文件到临时目录
        if hasattr(file, 'file_id') and bot:
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, msg.file_name)
            try:
                logger.debug(
                    f"Downloading file from Telegram - message_id: {message.message_id} - "
                    f"content_type: {msg.content_type}"
                )
                # 获取文件对象
                file_obj = await bot.get_file(file.file_id)
                # 下载文件
                await file_obj.download_to_drive(file_path)
                msg.file_path = file_path
                logger.debug(
                    f"File downloaded successfully - message_id: {message.message_id} - "
                    f"content_type: {msg.content_type}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to download file from Telegram - message_id: {message.message_id} - "
                    f"error_type: {type(e).__name__} - content_type: {msg.content_type}",
                    exc_info=True
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise

        return msg

    @property
    def title(self) -> str:
        """获取消息标题"""
        if self.timestamp:
            return f"Telegram消息 {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        return "Telegram消息"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        logger.debug(
            f"Converting message to dictionary - message_id: {self.message_id} - "
            f"has_content: {bool(self.content)} - has_file: {bool(self.file_path)}"
        )
        return {
            'content': self.content,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'content_type': self.content_type,
            'media_group_id': self.media_group_id,
            'message_id': self.message_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'source': self.source,
            'tags': self.tags,
            'is_pinned': self.is_pinned,
            'source_url': self.source_url,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'file_count': self.file_count,
            'link_count': self.link_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建消息对象"""
        logger.debug(
            f"Creating message from dictionary - message_id: {data.get('message_id')} - "
            f"has_content: {bool(data.get('content'))} - has_file: {bool(data.get('file_path'))}"
        )
        if data.get('timestamp'):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if data.get('created_time'):
            data['created_time'] = datetime.fromisoformat(data['created_time'])
        return cls(**data) 