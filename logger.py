"""日志工具模块"""
import logging
import sys
from typing import Optional

def setup_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别，默认为 INFO
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 设置日志级别
    if level is None:
        level = logging.DEBUG
    logger.setLevel(level)
    
    # 如果已经有处理器，不重复添加
    if logger.handlers:
        return logger
        
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    # 创建格式化器
    formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    
    return logger

    
class CustomFormatter(logging.Formatter):
    def format(self, record):
        log_message = super().format(record)
        
        username = getattr(record, 'username', None)
        user_id = getattr(record, 'user_id', None)
        text_content = getattr(record, 'text_content', None)
        
        if username:
            log_message += f" - Username: {username}"
        if user_id:
            log_message += f" - UserID: {user_id}"
        if text_content:
            log_message += f" - Text: {text_content}"
            
        return log_message

    

# 创建默认日志记录器
logger = setup_logger(__name__)