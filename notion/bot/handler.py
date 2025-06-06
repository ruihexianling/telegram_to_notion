"""Telegram Bot 消息处理器"""
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, Application
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import JSONResponse
import json
from datetime import datetime
import pytz

from ..api.client import NotionClient
from ..core.buffer import MessageBuffer
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
import config
from ..routes import get_route
from .application import get_application
from .tools import send_message_to_admins, format_datetime

from common_utils import is_auth_user

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 创建全局配置
notion_config = NotionConfig({
    'NOTION_KEY': config.NOTION_KEY,
    'NOTION_VERSION': config.NOTION_VERSION,
    'PAGE_ID': config.DATABASE_ID
})

# 创建全局消息缓冲区实例
message_buffer = MessageBuffer()

# 创建路由
router = APIRouter()

# === 消息处理函数 ===
async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理所有消息"""
    message = update.message
    if not message:
        logger.warning("Received an update without a message object")
        return
    
    logger.info(
        f"Received a message - username: {update.effective_user.username} - "
        f"user_id: {update.effective_user.id}"
    )

    if not is_auth_user(update.effective_user.id):
        await message.reply_text("您没有权限使用此功能, 请联系管理员")
        logger.warning(
            f"Unauthorized user attempted to use the bot - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id} - text_content: {message.text}"
        )
        return

    try:
        logger.info(
            f"Creating Notion client and uploader - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id}"
        )
        async with NotionClient(notion_config) as client:
            uploader = NotionUploader(client)
            
            logger.info(
                f"Adding message to buffer - username: {update.effective_user.username} - "
                f"user_id: {update.effective_user.id}"
            )
            # 将消息添加到缓冲区
            page_url = await message_buffer.add_message(
                update.effective_user.id,
                message,
                uploader,
                context.bot
            )
            
            # 如果是第一条消息，发送页面URL
            if page_url:
                logger.info(
                    f"First message saved to Notion, sending page URL - username: {update.effective_user.username} - "
                    f"user_id: {update.effective_user.id} - page_url: {page_url}"
                )
                bot_message = await message.reply_text(f"您的消息已保存到Notion页面：{page_url}\n 30秒内继续发送的消息将自动追加到该页面")
                message_buffer.buffers[update.effective_user.id]['first_reply_sent'] = True
                message_buffer.buffers[update.effective_user.id]['first_bot_message'] = bot_message
                
    except Exception as e:
        error_msg = f"处理消息时发生错误: {str(e)}"
        logger.exception(
            f"{error_msg} - username: {update.effective_user.username} - "
            f"user_id: {update.effective_user.id} - text_content: {message.text}"
        )
        await message.reply_text(f"❌ {error_msg}")

# === Webhook 处理函数 ===
@router.post(get_route("notion_telegram_webhook"))
async def telegram_webhook(request: Request):
    """处理 Telegram webhook 请求"""
    try:
        application = get_application()
        if not application:
            raise HTTPException(status_code=500, detail="Application not initialized")
            
        # 解析更新
        update = Update.de_json(await request.json(), application.bot)
        
        # 处理更新
        await application.process_update(update)
        
        logger.info(
            f"Processed Telegram update - update_id: {update.update_id}"
        )
        
        return JSONResponse({"status": "success"})
        
    except Exception as e:
        logger.exception(f"Error processing Telegram update - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(get_route("railway_webhook"))
async def railway_webhook(request: Request):
    """处理 Railway webhook 请求"""
    try:
        # 获取请求体
        body = await request.body()
        body_str = body.decode('utf-8')
        
        # 解析请求体
        data = json.loads(body_str)
        
        # 打印完整的 data 信息
        logger.info(f"Received Railway webhook data: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # 获取应用实例
        application = get_application()
        if not application:
            raise HTTPException(status_code=500, detail="Application not initialized")
            
        # 转换时间戳为北京时间
        timestamp = data.get('timestamp')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                beijing_time = format_datetime(dt)
            except Exception as e:
                logger.error(f"Failed to parse timestamp: {e}")
                beijing_time = timestamp
        else:
            beijing_time = 'Unknown'
            
        # 构建通知消息
        message = (
            f"🚨 Railway {data.get('type', 'Unknown')} 通知\n\n"
            f"📦 项目信息:\n"
            f"• 名称: {data.get('project', {}).get('name', 'Unknown')}\n"
            f"• 描述: {data.get('project', {}).get('description', 'Unknown')}\n\n"
            f"🌍 环境信息:\n"
            f"• 名称: {data.get('environment', {}).get('name', 'Unknown')}\n\n"
            f"📝 事件详情:\n"
            f"• 类型: {data.get('type', 'Unknown')}\n"
            f"• 状态: {data.get('status', 'Unknown')}\n"
        )

        # 根据不同类型添加特定信息
        if data.get('type') == 'DEPLOY':
            deployment = data.get('deployment', {})
            meta = deployment.get('meta', {})
            service = data.get('service', {})
            
            # 添加部署信息
            if deployment.get('creator'):
                message += f"• 操作者: {deployment['creator'].get('name', 'Unknown')}\n"
            
            # 添加服务信息
            if service:
                message += f"• 服务: {service.get('name', 'Unknown')}\n"
            
            # 添加部署元数据
            if meta:
                message += f"\n🔧 部署配置:\n"
                if meta.get('repo'):
                    message += f"• 仓库: {meta['repo']}\n"
                if meta.get('branch'):
                    message += f"• 分支: {meta['branch']}\n"
                if meta.get('commitMessage'):
                    message += f"• 提交信息: {meta['commitMessage']}\n"
                if meta.get('commitHash'):
                    message += f"• 提交哈希: {meta['commitHash'][:8]}\n"
                if meta.get('cronSchedule'):
                    message += f"• 定时任务: {meta['cronSchedule']}\n"
                if meta.get('startCommand'):
                    message += f"• 启动命令: {meta['startCommand']}\n"
                    
        elif data.get('type') == 'BUILD':
            message += f"• 构建状态: {data.get('status', 'Unknown')}\n"
        elif data.get('type') == 'SERVICE':
            message += f"• 服务状态: {data.get('status', 'Unknown')}\n"
        elif data.get('type') == 'DOMAIN':
            message += f"• 域名状态: {data.get('status', 'Unknown')}\n"
            
        # 添加时间信息
        message += f"\n⏰ 时间: {beijing_time}\n"
        
        # 如果有错误信息，添加到消息中
        if data.get('error'):
            message += f"\n❌ 错误信息:\n{data['error']}"
            
        # 发送通知给管理员
        await send_message_to_admins(application, message)
        
        logger.info(f"Processed Railway webhook - type: {data.get('type')}")
        return JSONResponse({"status": "success"})
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in Railway webhook request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.exception(f"Error processing Railway webhook - error: {e}")
        raise HTTPException(status_code=500, detail=str(e))