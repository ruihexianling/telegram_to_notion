"""Notion 配置管理模块"""
import logging
from typing import Dict, Any
import re
from ..api.exceptions import NotionConfigError
from logger import setup_logger

logger = setup_logger(__name__)

class NotionConfig:
    """Notion 配置管理类"""
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._validate_config()
        logger.info(
            f"NotionConfig initialized - version: {self.notion_version} - "
            f"page_id: {self.parent_page_id[:8]}..."
        )

    def _format_page_id(self, page_id: str) -> str:
        """格式化页面 ID，添加连字符
        
        Args:
            page_id: 原始页面 ID
            
        Returns:
            str: 格式化后的页面 ID
        """
        # 如果已经包含连字符，直接返回
        if '-' in page_id:
            logger.debug(f"Page ID already contains hyphens: {page_id}")
            return page_id
            
        # 移除所有连字符
        page_id = page_id.replace('-', '')
        
        # 检查长度
        if len(page_id) != 32:
            raise NotionConfigError(f"无效的页面 ID 长度: {len(page_id)}")
            
        # 添加连字符
        formatted_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
        logger.debug(f"Formatted page ID - original: {page_id} - formatted: {formatted_id}")
        return formatted_id

    def _validate_config(self) -> None:
        """验证配置是否完整"""
        required_keys = ['NOTION_KEY', 'NOTION_VERSION', 'PAGE_ID']
        missing_keys = [key for key in required_keys if key not in self._config or not self._config[key]]
        if missing_keys:
            raise NotionConfigError(f"缺少必要的 Notion 配置项: {', '.join(missing_keys)}")

        # 验证 NOTION_KEY 格式
        notion_key = self._config['NOTION_KEY']
        if not notion_key.startswith('ntn_'):
            raise NotionConfigError("Notion API Key 必须以 'ntn_' 开头")

        # 验证并格式化 PAGE_ID
        page_id = self._config['PAGE_ID']
        try:
            self._config['PAGE_ID'] = self._format_page_id(page_id)
            logger.info(f"Page ID validated and formatted: {self._config['PAGE_ID']}")
        except NotionConfigError as e:
            raise NotionConfigError(f"无效的 PAGE_ID 格式: {page_id} - {str(e)}")

        # 验证 NOTION_VERSION 格式
        version = self._config['NOTION_VERSION']
        version_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(version_pattern, version):
            raise NotionConfigError(
                f"无效的 NOTION_VERSION 格式: {version}。"
                "版本号应该是类似 '2022-06-28' 的格式"
            )

        logger.debug(
            f"Notion configuration validated - "
            f"version: {version} - "
            f"page_id: {self._config['PAGE_ID']} - "
            f"key_prefix: {notion_key[:7]}..."
        )

    @property
    def notion_key(self) -> str:
        """获取 Notion API Key"""
        return self._config['NOTION_KEY']

    @property
    def notion_version(self) -> str:
        """获取 Notion API 版本"""
        return self._config['NOTION_VERSION']

    @property
    def parent_page_id(self) -> str:
        """获取父页面 ID"""
        return self._config['PAGE_ID']

    @property
    def headers(self) -> Dict[str, str]:
        """获取 API 请求头"""
        headers = {
            "Authorization": f"Bearer {self.notion_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json"
        }
        logger.debug(f"Generated API headers - version: {self.notion_version}")
        return headers

    @property
    def multipart_headers(self) -> Dict[str, str]:
        """获取多部分请求头"""
        headers = {
            "Authorization": f"Bearer {self.notion_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "multipart/form-data"
        }
        logger.debug(f"Generated multipart headers - version: {self.notion_version}")
        return headers 