"""消息模型模块"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
import pytz
import os
import tempfile
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
    content_type: Optional[str] = None
    media_group_id: Optional[str] = None
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: Optional[datetime] = None

    @classmethod
    async def from_telegram_message(cls, message: Any, bot: Optional[Bot] = None) -> 'Message':
        """从 Telegram 消息创建消息对象"""
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now_beijing = datetime.now(beijing_tz)
        
        # 创建消息对象
        msg = cls(
            content=message.text or message.caption,
            message_id=message.message_id,
            user_id=message.from_user.id if message.from_user else None,
            media_group_id=message.media_group_id,
            timestamp=now_beijing
        )

        # 处理文件
        if message.document:
            file = message.document
            msg.file_name = file.file_name
            msg.content_type = file.mime_type
        elif message.photo:
            file = message.photo[-1]  # 获取最大尺寸的照片
            msg.file_name = f"photo_{message.message_id}.jpg"
            msg.content_type = "image/jpeg"
        elif message.video:
            file = message.video
            msg.file_name = file.file_name or f"video_{message.message_id}.mp4"
            msg.content_type = file.mime_type or "video/mp4"
        elif message.audio:
            file = message.audio
            msg.file_name = file.file_name or f"audio_{message.message_id}.mp3"
            msg.content_type = file.mime_type or "audio/mpeg"
        elif message.voice:
            file = message.voice
            msg.file_name = f"voice_{message.message_id}.ogg"
            msg.content_type = "audio/ogg"
        else:
            return msg

        # 下载文件到临时目录
        if hasattr(file, 'file_id') and bot:
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, msg.file_name)
            try:
                # 获取文件对象
                file_obj = await bot.get_file(file.file_id)
                # 下载文件
                await file_obj.download_to_drive(file_path)
                msg.file_path = file_path
            except Exception as e:
                logger.error(f"Error downloading file: {e}", exc_info=True)
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
        return {
            'content': self.content,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'content_type': self.content_type,
            'media_group_id': self.media_group_id,
            'message_id': self.message_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建消息对象"""
        if data.get('timestamp'):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data) 