"""日志工具模块"""
import logging
import sys
import os
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pytz
from config import DEBUG, LOG_DIR

def setup_logger(name: str, level: Optional[int] = None, log_third_party: bool = False) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别，默认为 INFO
        log_third_party: 是否记录第三方库的日志，默认为 False
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 设置日志级别
    if level is None:
        level = logging.DEBUG if DEBUG else logging.INFO
        log_third_party = True if DEBUG else False
    logger.setLevel(level)
    
    # 如果已经有处理器，不重复添加
    if logger.handlers:
        return logger
        
    # 防止日志消息传递给根记录器，避免重复输出
    logger.propagate = False

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    # 创建格式化器
    formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    
    # 创建日志目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # 创建文件处理器
    log_file = os.path.join(LOG_DIR, f"{name}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 如果需要记录第三方库的日志，则为第三方库设置单独的处理器和级别
    if log_third_party:
        third_party_logger = logging.getLogger('')  # 获取根记录器
        third_party_logger_level = logging.INFO if DEBUG else logging.WARNING
        third_party_logger.setLevel(third_party_logger_level)  # 设置第三方库的日志级别
        if not third_party_logger.handlers:
            third_party_handler = logging.StreamHandler(sys.stdout)
            third_party_formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            third_party_handler.setFormatter(third_party_formatter)
            third_party_logger.addHandler(third_party_handler)
            
            # 为第三方库也添加文件处理器
            third_party_file_handler = logging.FileHandler(
                os.path.join(LOG_DIR, 'third_party.log'),
                encoding='utf-8'
            )
            third_party_file_handler.setFormatter(third_party_formatter)
            third_party_logger.addHandler(third_party_file_handler)

    return logger

class CustomFormatter(logging.Formatter):
    """自定义日志格式化器，支持北京时间"""
    
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
    
    def formatTime(self, record, datefmt=None):
        """重写时间格式化方法，转换为北京时间"""
        ct = datetime.fromtimestamp(record.created)
        if ct.tzinfo is None:
            ct = pytz.UTC.localize(ct)
        beijing_time = ct.astimezone(self.beijing_tz)
        if datefmt:
            return beijing_time.strftime(datefmt)
        return beijing_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
    
    def format(self, record):
        log_message = super().format(record)
        
        # 只保留基本的用户信息
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

def get_recent_logs(hours: int = 24, limit: int = 100) -> List[Dict]:
    """获取最近的日志记录
    
    Args:
        hours: 获取多少小时内的日志，默认24小时
        limit: 最多返回多少条日志，默认100条
        
    Returns:
        List[Dict]: 日志记录列表，每条记录包含时间、级别、模块、消息等信息
    """
    logs = []
    beijing_tz = pytz.timezone('Asia/Shanghai')
    start_time = datetime.now(beijing_tz) - timedelta(hours=hours)
    
    # 遍历日志目录下的所有日志文件
    for filename in os.listdir(LOG_DIR):
        if not filename.endswith('.log'):
            continue
            
        file_path = os.path.join(LOG_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        # 解析日志行
                        parts = line.strip().split(' - ')
                        if len(parts) < 4:
                            continue
                            
                        timestamp_str = parts[0]
                        module = parts[1]
                        level = parts[2]
                        message = ' - '.join(parts[3:])
                        
                        # 解析时间戳（已经是北京时间）
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        timestamp = beijing_tz.localize(timestamp)
                        
                        # 只保留指定时间范围内的日志
                        if timestamp >= start_time:
                            logs.append([
                                timestamp.isoformat(),
                                module,
                                level,
                                message
                            ])
                    except Exception as e:
                        continue
        except Exception as e:
            continue
    
    # 按时间戳排序并限制数量
    logs.sort(key=lambda x: x[0], reverse=True)
    return logs[:limit]

# 创建默认日志记录器
logger = setup_logger(__name__)