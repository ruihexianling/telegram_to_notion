import os
import datetime
import mimetypes
import shutil
import tempfile
import asyncio
from urllib.request import Request

from fastapi import UploadFile, HTTPException, Form
from starlette.responses import JSONResponse
from telegram import Update
from telegram.ext import ContextTypes
from typing import Tuple, List, Dict, Optional

from common_utils import verify_signature
from config import *
import pytz
import logging
import aiohttp
from bot_setup import is_user_authorized

# Configure logging
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)

# === 配置 Notion 参数 ===
NOTION_CONFIG = {
    'NOTION_KEY': NOTION_KEY,
    'NOTION_VERSION': NOTION_VERSION,
    'PAGE_ID': PAGE_ID
}

# --- Notion API Helper Functions ---
async def _make_notion_api_request(url: str, notion_key: str, notion_version: str, method: str = 'POST', payload: Optional[dict] = None, data: Optional[aiohttp.FormData] = None, content_type: Optional[str] = 'application/json') -> dict:
    """
    Generic helper function to make requests to the Notion API.
    """
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": notion_version,
        "Content-Type": "multipart/form-data"
    }
    # Only set Content-Type header for JSON payloads if data is not present
    # aiohttp.FormData handles its own Content-Type for file uploads
    if content_type and not data:
        headers["Content-Type"] = content_type

    async with aiohttp.ClientSession() as session:
        try:
            if method == 'POST':
                async with session.post(url, json=payload, headers=headers, data=data) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == 'PATCH':
                async with session.patch(url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == 'GET':
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError as e:
            logging.error(f"Notion API request failed for {url} with error: {e}", exc_info=True)
            raise # Re-raise the exception after logging
        except Exception as e:
            logging.error(f"An unexpected error occurred during Notion API request to {url}: {e}", exc_info=True)
            raise # Re-raise the exception after logging


async def create_file_upload(notion_key: str, notion_version: str, file_name: str, content_type: str, file_size: int = None) -> Tuple[str, str, Optional[int], Optional[str]]:
    """
    在 Notion 中创建一个文件上传对象。
    如果文件大小超过20MB，则使用多部分上传模式。
    返回 (file_upload_id, upload_url, number_of_parts, mode)
    """
    logging.debug(f"Entering create_file_upload for file: {file_name}, content_type: {content_type}, size: {file_size}")
    url = "https://api.notion.com/v1/file_uploads"
    
    # 默认使用单部分上传模式
    payload = {"filename": file_name, "content_type": content_type, "mode": mode}
    
    # 如果文件大小超过20MB，使用多部分上传模式
    mode = "single_part"
    number_of_parts = None
    if file_size and file_size > 20 * 1024 * 1024:  # 20MB
        mode = "multi_part"
        # 计算需要的部分数量，每部分10MB
        part_size = 10 * 1024 * 1024  # 10MB
        number_of_parts = (file_size + part_size - 1) // part_size  # 向上取整
        payload = {
            "mode": mode,
            "number_of_parts": number_of_parts,
            "filename": file_name, 
            "content_type": content_type
        }
        logging.debug(f"Using multi-part upload mode with {number_of_parts} parts for file size {file_size}")
    
    response_json = await _make_notion_api_request(url, notion_key, notion_version, method='POST', payload=payload)
    logging.debug(f"Successfully created file upload object: ID={response_json['id']}, Upload URL={response_json['upload_url']}")
    return response_json['id'], response_json['upload_url'], number_of_parts, mode


async def upload_file_part_to_notion(notion_key: str, notion_version: str, file_path: str, upload_url: str, content_type: str, part_number: int, start_byte: int, end_byte: int) -> None:
    """
    上传文件的一部分到Notion。
    """
    logging.debug(f"Uploading file part {part_number} from byte {start_byte} to {end_byte}")
    
    async with aiohttp.ClientSession() as session:
        try:
            with open(file_path, "rb") as f:
                f.seek(start_byte)
                part_data = f.read(end_byte - start_byte)
                
                data = aiohttp.FormData()
                data.add_field('file', part_data, content_type=content_type)
                data.add_field('part_number', str(part_number))
                
                headers = {
                    "Authorization": f"Bearer {notion_key}",
                    "Notion-Version": notion_version
                }
                
                async with session.post(upload_url, headers=headers, data=data) as response:
                    response.raise_for_status()
                    
            logging.debug(f"Successfully uploaded file part {part_number}")
        except aiohttp.ClientError as e:
            logging.error(f"Error uploading file part {part_number} to Notion: {e}", exc_info=True)
            raise
        except Exception as e:
            logging.error(f"An unexpected error occurred in upload_file_part_to_notion: {e}", exc_info=True)
            raise


async def complete_multi_part_upload(notion_key: str, notion_version: str, file_upload_id: str) -> None:
    """
    完成多部分文件上传。
    """
    logging.debug(f"Completing multi-part upload for file_upload_id: {file_upload_id}")
    url = f"https://api.notion.com/v1/file_uploads/{file_upload_id}/complete"
    
    try:
        await _make_notion_api_request(url, notion_key, notion_version, method='POST', payload={})
        logging.debug(f"Successfully completed multi-part upload for file_upload_id: {file_upload_id}")
    except Exception as e:
        logging.error(f"Error completing multi-part upload: {e}", exc_info=True)
        raise


async def upload_file_to_notion(notion_key: str, notion_version: str, file_path: str, file_upload_id: str, upload_url: str, content_type: str, mode: str = "single_part", number_of_parts: int = None) -> str:
    """
    将本地文件上传到 Notion 提供的上传 URL。
    支持单部分上传和多部分上传。
    返回 file_upload_id。
    """
    logging.debug(f"Entering upload_file_to_notion for file_upload_id: {file_upload_id}, upload_url: {upload_url}, mode: {mode}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at path: {file_path}")
    
    file_size = os.path.getsize(file_path)
    logging.debug(f"File size: {file_size} bytes")
    
    if mode == "single_part" or file_size <= 20 * 1024 * 1024:  # 20MB
        # 单部分上传
        async with aiohttp.ClientSession() as session:
            try:
                with open(file_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename=os.path.basename(file_path), content_type=content_type)

                    headers = {
                        "Authorization": f"Bearer {notion_key}",
                        "Notion-Version": notion_version
                    }
                    async with session.post(upload_url, headers=headers, data=data) as response:
                        response.raise_for_status()
                logging.debug(f"Successfully uploaded file with ID: {file_upload_id}")
                return file_upload_id
            except aiohttp.ClientError as e:
                logging.error(f"Error uploading file to Notion: {e}", exc_info=True)
                raise
            except Exception as e:
                logging.error(f"An unexpected error occurred in upload_file_to_notion: {e}", exc_info=True)
                raise
            finally:
                pass
    else:
        # 多部分上传
        try:
            # 如果没有指定部分数量，计算需要的部分数量
            if not number_of_parts:
                part_size = 10 * 1024 * 1024  # 10MB
                number_of_parts = (file_size + part_size - 1) // part_size  # 向上取整
            
            part_size = (file_size + number_of_parts - 1) // number_of_parts  # 确保每个部分大小均匀
            # 确保部分大小在5-20MB之间（除了最后一部分可以小于5MB）
            if part_size < 5 * 1024 * 1024 and number_of_parts > 1:
                part_size = 5 * 1024 * 1024
            elif part_size > 20 * 1024 * 1024:
                part_size = 20 * 1024 * 1024
            
            # 上传每个部分
            tasks = []
            for part_number in range(1, number_of_parts + 1):
                start_byte = (part_number - 1) * part_size
                end_byte = min(part_number * part_size, file_size)
                
                task = upload_file_part_to_notion(
                    notion_key, notion_version, file_path, upload_url,
                    content_type, part_number, start_byte, end_byte
                )
                tasks.append(task)
            
            # 并行上传所有部分
            await asyncio.gather(*tasks)
            
            # 完成多部分上传
            await complete_multi_part_upload(notion_key, notion_version, file_upload_id)
            
            logging.debug(f"Successfully uploaded multi-part file with ID: {file_upload_id}")
            return file_upload_id
        except Exception as e:
            logging.error(f"Error in multi-part upload: {e}", exc_info=True)
            raise


def is_image_mime_type(mime_type: str) -> bool:
    """
    判断 MIME 类型是否为图片。
    """
    return mime_type and mime_type.startswith('image/')


async def create_notion_page(notion_key: str, notion_version: str, parent_page_id: str, title: str, content_text: str = None) -> str:
    """
    在 Notion 中创建新页面。
    注意：此函数仅创建页面标题和可选的初始文本内容。文件块将通过 append_block_to_notion_page 追加。
    """
    logging.debug(f"Entering create_notion_page with title: {title}")
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {
            "type": "page_id",
            "page_id": parent_page_id
        },
        "properties": {
            "title": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            }
        },
        "children": []
    }

    if content_text:
        payload["children"].append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": content_text
                        }
                    }
                ]
            }
        })

    response_json = await _make_notion_api_request(url, notion_key, notion_version, method='POST', payload=payload)
    logging.info(f"Successfully created Notion page with ID: {response_json['id']}")
    return response_json['id']


async def append_block_to_notion_page(notion_key: str, notion_version: str, page_id: str, content_text: str = None, file_upload_id: str = None, file_name: str = None, file_mime_type: str = None):
    """
    向一个已存在的 Notion 页面追加一个文件/图片块或文本块。
    """
    logging.debug(f"Appending block to Notion page {page_id}...")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    new_blocks = []

    if file_upload_id:
        block_type = "image" if is_image_mime_type(file_mime_type) else "file"
        block_content_key = "image" if block_type == "image" else "file"
        new_blocks.append({
            "object": "block",
            "type": block_type,
            block_content_key: {
                "type": "file_upload",
                "file_upload": {
                    "id": file_upload_id
                },
                "caption": [
                    {
                        "type": "text",
                        "text": {
                            "content": file_name if file_name else "Uploaded file"
                        }
                    }
                ]
            }
        })
    if content_text:
        new_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": content_text
                        }
                    }
                ]
            }
        })

    if not new_blocks:
        logging.warning(f"No content provided to append_block_to_notion_page for page {page_id}. Skipping.")
        return {}  # Return an empty dict if no blocks were added

    payload = {"children": new_blocks}
    return await _make_notion_api_request(url, notion_key, notion_version, method='PATCH', payload=payload)


# --- Telegram Bot Handler Functions ---
async def _process_text_message(message, notion_config):
    """Encapsulates logic for handling standalone text messages."""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now_beijing = datetime.datetime.now(beijing_tz)
    title = f"Telegram消息 {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}"

    notion_key = notion_config['NOTION_KEY']
    notion_version = notion_config['NOTION_VERSION']
    parent_page_id = notion_config['PAGE_ID']

    logging.info(f"Creating Notion page for text message: {title}")
    page_id = await create_notion_page(
        notion_key=notion_key,
        notion_version=notion_version,
        parent_page_id=parent_page_id,
        title=title,
        content_text=message.text # Initial text content directly in page creation
    )
    logging.info(f"Notion page created for text message with ID: {page_id}")
    page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
    return page_url

async def _process_file_message(message, notion_config):
    """Encapsulates logic for handling standalone file messages."""
    file_obj = None
    file_extension = ''
    content_type = ''
    file_name_for_notion = ''
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now_beijing = datetime.datetime.now(beijing_tz)
    # Use caption as title, or a default timestamped title
    caption = message.caption or f"Telegram文件 {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}"
    temp_file_path = None

    try:
        async def _check_file_size(file_obj):
            if file_obj.file_size > 20 * 1024 * 1024:  # 20MB
                raise ValueError("文件大小超过20MB限制，无法上传。请压缩文件或选择较小的文件。")

        if message.photo:
            file_obj = message.photo[-1]
            await _check_file_size(file_obj)
            file_obj = await file_obj.get_file()
            file_extension = 'jpg'
            content_type = 'image/jpeg'
            file_name_for_notion = f"telegram_photo_{file_obj.file_id}.jpg"
        elif message.document:
            file_obj = message.document
            try:
                await _check_file_size(file_obj)
            except ValueError as e:
                return None, str(e)
            file_name = file_obj.file_name
            file_obj = await file_obj.get_file()
            file_extension = file_name.split('.')[-1] if '.' in file_name else 'file'
            content_type = file_obj.mime_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            file_name_for_notion = file_name
        elif message.video:
            file_obj = message.video
            await _check_file_size(file_obj)
            file_obj = await file_obj.get_file()
            file_extension = 'mp4'
            content_type = file_obj.mime_type or 'video/mp4'
            file_name_for_notion = f"telegram_video_{file_obj.file_id}.mp4"
        elif message.audio:
            file_obj = message.audio
            await _check_file_size(file_obj)
            file_obj = await file_obj.get_file()
            file_extension = file_obj.file_name.split('.')[-1] if file_obj.file_name and '.' in file_obj.file_name else 'mp3'
            content_type = file_obj.mime_type or 'audio/mpeg'
            file_name_for_notion = file_obj.file_name or f"telegram_audio_{file_obj.file_id}.mp3"
        elif message.voice:
            file_obj = message.voice
            await _check_file_size(file_obj)
            file_obj = await file_obj.get_file()
            file_extension = 'ogg'
            content_type = file_obj.mime_type or 'audio/ogg'
            file_name_for_notion = f"telegram_voice_{file_obj.file_id}.ogg"
        else:
            return None, "抱歉，我目前只支持照片、文档、视频、音频和语音消息。"

        if file_obj:
            temp_file_path = f"/tmp/{file_obj.file_id}.{file_extension}"
            await file_obj.download_to_drive(temp_file_path)
            logging.info("Standalone file downloaded successfully.")
            
            # 检查文件大小
            file_size = os.path.getsize(temp_file_path)
            logging.info(f"File size: {file_size} bytes ({file_size / (1024 * 1024):.2f} MB)")
            if file_size > 20 * 1024 * 1024:  # 20MB
                raise ValueError("文件大小超过20MB限制，不允许上传")

            notion_key = notion_config['NOTION_KEY']
            notion_version = notion_config['NOTION_VERSION']
            parent_page_id = notion_config['PAGE_ID']

            # Create Notion page for the file
            logging.info(f"Creating Notion page for standalone file: {caption}")
            page_id = await create_notion_page(
                notion_key=notion_key,
                notion_version=notion_version,
                parent_page_id=parent_page_id,
                title=caption,
                content_text=None # Page created, caption handled as part of title.
                                  # If caption should be a separate text block, use append_block_to_notion_page
            )
            logging.info(f"Notion page created for standalone file with ID: {page_id}")

            # Upload file to Notion
            logging.info(f"Creating file upload object in Notion for {file_name_for_notion}")
            
            # 创建文件上传对象，传递文件大小以决定是否使用多部分上传
            file_upload_id, upload_url, number_of_parts, mode = await create_file_upload(
                notion_key, notion_version, file_name_for_notion, content_type, file_size
            )
            
            # 根据模式上传文件
            if mode == "multi_part":
                logging.info(f"Using multi-part upload mode with {number_of_parts} parts for file size {file_size}")
            else:
                logging.info(f"Using single-part upload mode for file size {file_size}")
                
            logging.info(f"Uploading file to Notion URL: {upload_url}")
            uploaded_file_id = await upload_file_to_notion(
                notion_key, notion_version, temp_file_path, file_upload_id, upload_url, 
                content_type, mode, number_of_parts
            )
            logging.info(f"File uploaded to Notion with ID: {uploaded_file_id}")

            # Append file block to Notion page
            await append_block_to_notion_page(
                notion_key, notion_version, page_id,
                file_upload_id=uploaded_file_id,
                file_name=file_name_for_notion,
                file_mime_type=content_type
            )
            logging.info("File block appended to Notion page successfully.")

            # Append caption as a separate text block if it exists (and wasn't part of initial page content)
            if message.caption:
                await append_block_to_notion_page(
                    notion_key, notion_version, page_id,
                    content_text=message.caption
                )
                logging.info(f"Appended caption to Notion page {page_id}.")


            page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
            return page_url, None
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            logging.info(f"Cleaning up temporary file: {temp_file_path}")
            os.remove(temp_file_path)
            logging.info("Temporary file removed.")


async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE, notion_config: dict) -> None:
    """
    处理所有消息，包括识别媒体组、文本消息和单个文件消息。
    """
    message = update.message
    if not message:
        logging.warning("Received an update without a message object.")
        return

    if not is_user_authorized(update.effective_user.id):
        await message.reply_text("您没有权限使用此功能。")
        logging.warning(f"Unauthorized user attempted to use the bot: {update.effective_user.username}, {update.effective_user.id}, Message: {message.text}")
        return

    if message.text:
        logging.info("Received standalone text message.")
        try:
            page_url = await _process_text_message(message, notion_config)
            await message.reply_text(f"您的文本已保存到Notion页面：{page_url}")
        except Exception as e:
            logging.exception("Error handling standalone text message:")
            await message.reply_text(f"处理您的文本消息时发生错误：{type(e).__name__}")
    elif message.effective_attachment: # Checks for photo, document, video, audio, voice
        logging.info("Received standalone file message.")
        try:
            page_url, error_message = await _process_file_message(message, notion_config)
            if page_url:
                await message.reply_text(f"您上传的文件已保存到Notion页面：{page_url}")
            elif error_message:
                await message.reply_text(error_message)
        except Exception as e:
            logging.exception("Error handling standalone file message:")
            await message.reply_text(f"处理您的文件时发生错误：{type(e).__name__}")
    else:
        logging.warning("Received message with no text, effective_attachment, or media_group_id.")
        await update.message.reply_text("收到一条空消息或不支持的消息类型。")


async def download_file_from_url(file_url: str, temp_dir: str = "/tmp") -> str:
    """
    从给定的 URL 下载文件到临时目录。
    返回下载文件的完整路径。
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_name = os.path.basename(file_url)
    if not file_name: # Fallback if file_url doesn't have a recognizable filename
        file_name = f"downloaded_file_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    temp_file_path = os.path.join(temp_dir, file_name)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                with open(temp_file_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024) # Read in chunks
                        if not chunk:
                            break
                        f.write(chunk)
        logging.info(f"Successfully downloaded file from {file_url} to {temp_file_path}")
        return temp_file_path
    except aiohttp.ClientError as e:
        logging.error(f"Error downloading file from URL {file_url}: {e}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during file download from URL {file_url}: {e}", exc_info=True)
        raise


async def save_upload_file_temporarily(file: UploadFile, temp_dir: str = "/tmp") -> tuple[str, str, str]:
    """
    Saves an uploaded file temporarily to disk.
    Returns (file_path, file_name, content_type)
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_name = file.filename
    if not file_name:
        file_name = f"uploaded_file_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    file_path = os.path.join(temp_dir, file_name)
    # Prioritize content_type from UploadFile, then guess from filename, default to octet-stream
    content_type = file.content_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'

    try:
        # Use shutil.copyfileobj for efficient file copy from UploadFile's file-like object
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logging.info(f"Temporary file saved at {file_path}")
        return file_path, file_name, content_type
    except Exception as e:
        logging.error(f"Error saving uploaded file {file_name} temporarily: {e}", exc_info=True)
        # Clean up partial file if an error occurs during saving
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Cleaned up partial temporary file {file_path} after error.")
        raise


# This function essentially fulfills the 'api_upload' request's needs
async def create_and_append_to_notion_page(
    title: str,
    notion_config: dict,
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    file_name: Optional[str] = None,
    content_type: Optional[str] = None,
    append_only: bool = False # New parameter to control whether to create a new page or append only
) -> str:
    """
    Uploads content (text and/or file) to Notion, creating a new page and appending blocks.
    This function combines the logic for creating a page and then appending different
    types of blocks to it, which aligns with the "api_upload" concept.
    Returns the ID of the created Notion page.
    """
    notion_key = notion_config['NOTION_KEY']
    notion_version = notion_config['NOTION_VERSION']
    parent_page_id = notion_config['PAGE_ID']

    if not append_only:
        logging.info(f"Creating Notion page with title: {title}")
        # Create the Notion page initially without content, or with content if desired
        page_id = await create_notion_page(
            notion_key=notion_key,
            notion_version=notion_version,
            parent_page_id=parent_page_id,
            title=title,
            content_text=None # Initial page content can be set here or appended later
        )
        logging.info(f"Notion page created with ID: {page_id}")
    else:
        page_id = parent_page_id # Use the existing page ID for appending only

    # If a file path is provided, handle file upload and append file block
    if file_path:
        if not os.path.exists(file_path):
            logging.error(f"File not found at {file_path}. Cannot upload file.")
            # If file not found but text content exists, still try to append text
            if content:
                 await append_block_to_notion_page(
                    notion_key, notion_version, page_id,
                    content_text=content
                )
                 logging.info(f"Appended content to page {page_id} after file not found.")
                 return page_id # Return page_id even if file upload failed but content was added
            else:
                raise FileNotFoundError(f"File not found at {file_path}")

        # Determine effective file name and content type
        effective_file_name = file_name or os.path.basename(file_path) or title
        effective_content_type = content_type or mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        logging.info(f"File size: {file_size} bytes ({file_size / (1024 * 1024):.2f} MB)")
        if file_size > 20 * 1024 * 1024:  # 20MB
            raise ValueError("文件大小超过20MB限制，不允许上传。")

        logging.info(f"Uploading file {effective_file_name} to Notion...")
        # Step 1: Create file upload object in Notion，传递文件大小以决定是否使用多部分上传
        file_upload_id, upload_url, number_of_parts, mode = await create_file_upload(
            notion_key, notion_version, effective_file_name, effective_content_type, file_size
        )
        
        # Step 2: 根据模式上传文件
        if mode == "multi_part":
            logging.info(f"Using multi-part upload mode with {number_of_parts} parts for file size {file_size}")
        else:
            logging.info(f"Using single-part upload mode for file size {file_size}")
            
        # 上传文件
        uploaded_file_id = await upload_file_to_notion(
            notion_key, notion_version, file_path, file_upload_id, upload_url, 
            effective_content_type, mode, number_of_parts
        )

        # Step 3: Append the file block to the Notion page
        await append_block_to_notion_page(
            notion_key, notion_version, page_id,
            file_upload_id=uploaded_file_id,
            file_name=effective_file_name,
            file_mime_type=effective_content_type
        )
        logging.info(f"File block appended to page {page_id}.")

    # If text content is provided, append it as a paragraph block
    if content:
        logging.info(f"Appending content to page {page_id}...")
        await append_block_to_notion_page(
            notion_key, notion_version, page_id,
            content_text=content
        )
        logging.info(f"Content block appended to page {page_id}.")

    # Log a warning if no content (file or text) was provided, resulting in an empty page
    if not file_path and not content:
         logging.warning(f"No file_path or content provided for upload_as_block for title: {title}. Page {page_id} created but empty.")

    return page_id

async def api_upload(request: Request, title: str = Form(...), content: Optional[str] = Form(None), file: Optional[UploadFile] = Form(None), append_only: bool = False):
    # Verify signature
    signature = request.headers.get('X-Signature')
    if not verify_signature(signature, request):
        logging.debug(f"Invalid signature: {signature}")
        raise HTTPException(status_code=401, detail="Invalid signature")

    logging.info(f"Received API upload request: title='{title}', content_provided={content is not None}, file_provided={file is not None}")

    if not content and not file:
        logging.warning("API upload request failed: Neither content nor file provided.")
        raise HTTPException(status_code=400, detail="Either 'content' or 'file' must be provided")

    temp_dir = None
    file_path = None
    file_name = None
    content_type = None

    try:
        if file:
            # Use the new helper function to save the file temporarily
            temp_dir = tempfile.mkdtemp()
            file_path, file_name, content_type = await save_upload_file_temporarily(file, temp_dir=temp_dir)
            logging.info(f"File saved temporarily: {file_path}")

        # Call the unified upload_as_block function
        await create_and_append_to_notion_page(
            title=title,
            notion_config=NOTION_CONFIG,
            content=content, # Pass content even if file is present, upload_as_block handles it
            file_path=file_path,
            file_name=file_name,
            content_type=content_type,
            append_only=append_only
        )

        logging.info("API upload successful.")
        return JSONResponse(status_code=200, content={"message": "Content/File uploaded successfully"})

    except Exception as e:
        logging.error(f"API upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload content/file: {e}")
    finally:
        # Clean up the temporary directory and its contents if it was created
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_e:
                logging.error(f"Error cleaning up temporary directory {temp_dir}: {cleanup_e}", exc_info=True)