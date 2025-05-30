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
            f"database_id: {self.parent_page_id}"
        )

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

        # 验证 DATABASE_ID 格式
        page_id = self._config['PAGE_ID']
        if not page_id:
            raise NotionConfigError("PAGE_ID 不能为空")

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
            f"database_id: {page_id} - "
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
        """获取数据库 ID"""
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