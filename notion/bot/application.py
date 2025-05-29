"""全局Application实例管理模块"""
from typing import Optional
from telegram.ext import Application

# 全局 Application 实例
_application: Optional[Application] = None

def get_application() -> Application:
    """获取全局 Application 实例"""
    if _application is None:
        raise RuntimeError("Application not set.")
    return _application

def set_application(application: Application):
    """设置全局 Application 实例"""
    global _application
    _application = application 