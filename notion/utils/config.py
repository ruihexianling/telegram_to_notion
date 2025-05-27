"""Notion 配置管理模块"""
import logging
from typing import Dict, Any
from ..api.exceptions import NotionConfigError

class NotionConfig:
    """Notion 配置管理类"""
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置是否完整"""
        required_keys = ['NOTION_KEY', 'NOTION_VERSION', 'PAGE_ID']
        missing_keys = [key for key in required_keys if key not in self._config or not self._config[key]]
        if missing_keys:
            raise NotionConfigError(f"缺少必要的 Notion 配置项: {', '.join(missing_keys)}")

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
        return {
            "Authorization": f"Bearer {self.notion_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json"
        }

    @property
    def multipart_headers(self) -> Dict[str, str]:
        """获取多部分请求头"""
        return {
            "Authorization": f"Bearer {self.notion_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "multipart/form-data"
        } 