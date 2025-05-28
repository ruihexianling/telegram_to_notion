"""Notion Webhook 处理器"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import JSONResponse

from ..api.client import NotionClient
from ..core.uploader import NotionUploader
from ..utils.config import NotionConfig
from ..routes import get_route

from logger import setup_logger
# 配置日志
logger = setup_logger(__name__)

# 创建路由

router = APIRouter()
