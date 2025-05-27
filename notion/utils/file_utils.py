"""文件处理工具模块"""
import os
import shutil
import logging
import mimetypes
import datetime
from typing import Tuple, Optional
from fastapi import UploadFile

async def save_upload_file_temporarily(
    file: UploadFile,
    temp_dir: str = "/tmp"
) -> Tuple[str, str, str]:
    """
    保存上传的文件到临时目录
    返回 (file_path, file_name, content_type)
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_name = file.filename
    if not file_name:
        file_name = f"uploaded_file_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    file_path = os.path.join(temp_dir, file_name)
    content_type = file.content_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logging.info(f"Temporary file saved at {file_path}")
        return file_path, file_name, content_type
    except Exception as e:
        logging.error(f"Error saving uploaded file {file_name} temporarily: {e}", exc_info=True)
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Cleaned up partial temporary file {file_path} after error.")
        raise

def get_file_info(file_path: str) -> Tuple[str, str, str]:
    """
    获取文件信息
    返回 (file_name, file_extension, content_type)
    """
    file_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_name)[1].lstrip('.')
    content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    return file_name, file_extension, content_type

def cleanup_temp_file(file_path: str) -> None:
    """清理临时文件"""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logging.info(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logging.error(f"Error cleaning up temporary file {file_path}: {e}", exc_info=True)

def cleanup_temp_dir(temp_dir: str) -> None:
    """清理临时目录"""
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logging.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logging.error(f"Error cleaning up temporary directory {temp_dir}: {e}", exc_info=True) 