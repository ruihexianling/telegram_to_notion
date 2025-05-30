"""Telegram Bot 工具函数模块"""
import traceback
import os
import psutil
import platform
from datetime import datetime
import pytz
import requests

from telegram.ext import Application
from config import ADMIN_USERS, DEPLOY_URL
from logger import setup_logger

logger = setup_logger(__name__)

# === 管理员消息相关函数 ===
async def send_message_to_admins(application: Application, text: str):
    """发送消息给所有管理员用户"""
    logger.debug(f"Sending message to admin users: {text}")
    for admin_id in ADMIN_USERS:
        try:
            await application.bot.send_message(chat_id=admin_id, text=text)
            logger.info(f"Message '{text}' sent to admin: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send message '{text}' to admin {admin_id}: {e}")
    logger.info("Messages sent to all admins")

async def after_bot_start(application: Application):
    """机器人上线后，给所有管理员发送消息"""
    await send_message_to_admins(application, "🤖 机器人已上线！")

async def before_bot_stop(application: Application):
    """机器人下线前，给所有管理员发送消息"""
    # render蓝绿机制，不适用
    # await send_message_to_admins(application, "🤖 机器人已下线！")
    pass

# === Webhook 相关函数 ===
async def setup_webhook(application: Application, webhook_url: str) -> None:
    """设置 webhook
    
    Args:
        application: Telegram 应用实例
        webhook_url: webhook URL
    """
    try:
        logger.info(f"Setting up webhook - url: {webhook_url}")
        
        # 设置 webhook
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=[
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "inline_query",
                "chosen_inline_result",
                "callback_query",
                "shipping_query",
                "pre_checkout_query",
                "poll",
                "poll_answer",
                "my_chat_member",
                "chat_member",
                "chat_join_request"
            ],
            drop_pending_updates=False,  # 丢弃待处理的更新
            max_connections=100,  # 最大连接数
            ip_address=None  # 自动检测IP地址
        )
        
        # 获取 webhook 信息
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook info - url: {webhook_info.url} - has_custom_certificate: {webhook_info.has_custom_certificate} - pending_update_count: {webhook_info.pending_update_count}")
        
    except Exception as e:
        logger.exception(f"Failed to setup webhook - error: {e}")
        raise

async def remove_webhook(application: Application) -> None:
    """移除 webhook
    
    Args:
        application: Telegram 应用实例
    """
    try:
        logger.info("Removing webhook")
        await application.bot.delete_webhook()
        logger.info("Webhook removed successfully")
    except Exception as e:
        logger.exception(f"Failed to remove webhook - error: {e}")
        raise

# === 系统信息相关函数 ===
def format_datetime(dt: datetime) -> str:
    """将时间格式化为北京时间字符串
    
    Args:
        dt: 要格式化的时间对象
        
    Returns:
        str: 格式化后的北京时间字符串
    """
    if dt is None:
        return '无'
    beijing_tz = pytz.timezone('Asia/Shanghai')
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    beijing_time = dt.astimezone(beijing_tz)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

async def get_system_info() -> str:
    """获取系统信息"""
    try:
        logger.info("Getting system info...")
        # 获取北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(beijing_tz)
        
        # 系统信息
        system_info = f"🖥 系统信息:\n"
        system_info += f"• 系统: {platform.system()} {platform.release()}\n"
        system_info += f"• 架构: {platform.machine()}\n"
        system_info += f"• Python: {platform.python_version()}\n"
        
        # CPU 信息
        cpu_info = f"\n💻 CPU 信息:\n"
        cpu_info += f"• 物理核心数: {psutil.cpu_count(logical=False)}\n"
        cpu_info += f"• 逻辑核心数: {psutil.cpu_count()}\n"
        cpu_info += f"• CPU 使用率: {psutil.cpu_percent()}%\n"
        
        # 内存信息
        memory = psutil.virtual_memory()
        memory_info = f"\n🧠 内存信息:\n"
        memory_info += f"• 总内存: {memory.total / (1024**3):.2f} GB\n"
        memory_info += f"• 已用内存: {memory.used / (1024**3):.2f} GB\n"
        memory_info += f"• 内存使用率: {memory.percent}%\n"
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_info = f"\n💾 磁盘信息:\n"
        disk_info += f"• 总空间: {disk.total / (1024**3):.2f} GB\n"
        disk_info += f"• 已用空间: {disk.used / (1024**3):.2f} GB\n"
        disk_info += f"• 磁盘使用率: {disk.percent}%\n"
        
        # 进程信息
        process = psutil.Process(os.getpid())
        process_info = f"\n⚙️ 进程信息:\n"
        process_info += f"• PID: {process.pid}\n"
        process_info += f"• 进程内存: {process.memory_info().rss / (1024**2):.2f} MB\n"
        process_info += f"• CPU 使用率: {process.cpu_percent()}%\n"
        process_info += f"• 运行时间: {format_datetime(datetime.fromtimestamp(process.create_time()))}\n"
        
        # 网络信息
        net_info = f"\n🌐 网络信息:\n"
        net_io = psutil.net_io_counters()
        net_info += f"• 发送: {net_io.bytes_sent / (1024**2):.2f} MB\n"
        net_info += f"• 接收: {net_io.bytes_recv / (1024**2):.2f} MB\n"
        
        # 系统负载
        load1, load5, load15 = psutil.getloadavg()
        load_info = f"\n📊 系统负载:\n"
        load_info += f"• 1分钟: {load1:.2f}\n"
        load_info += f"• 5分钟: {load5:.2f}\n"
        load_info += f"• 15分钟: {load15:.2f}\n"
        
        return system_info + cpu_info + memory_info + disk_info + process_info + net_info + load_info
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        return f"获取系统信息失败: {str(e)}"

# === 部署相关函数 ===
async def trigger_deploy() -> tuple[bool, str]:
    """触发重新部署
    
    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    try:
        # 构建请求数据
        url = DEPLOY_URL
        response = requests.get(url)
        
        if response.status_code == 200:
            return True, "✅ 部署请求已发送，请等待实例重新部署..."
        else:
            return False, f"❌ 部署请求失败: {response.status_code}"
    except Exception as e:
        return False, f"❌ 部署请求出错: {e}\n{traceback.format_exc()}" 