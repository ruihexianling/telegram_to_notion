"""Notion API 异常类定义"""

class NotionAPIError(Exception):
    """Notion API 错误基类"""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)

class NotionConfigError(NotionAPIError):
    """Notion 配置错误"""
    pass

class NotionFileUploadError(NotionAPIError):
    """Notion 文件上传错误"""
    pass

class NotionPageError(NotionAPIError):
    """Notion 页面操作错误"""
    pass 