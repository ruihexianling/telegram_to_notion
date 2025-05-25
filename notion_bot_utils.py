import os
import json
import datetime
import mimetypes

# import requests # 移除 requests 导入
from telegram import Update
from telegram.ext import ContextTypes, JobQueue
from typing import Tuple, List, Dict
import pytz
import logging
import asyncio
import aiohttp  # 确保已导入 aiohttp

# 配置 logging
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.DEBUG)


# --- Notion API Helper Functions ---
async def create_file_upload(notion_key: str, notion_version: str, file_name: str, content_type: str) -> Tuple[
    str, str]:
    """
    在 Notion 中创建一个文件上传对象。
    返回 (file_upload_id, upload_url)
    """
    logging.debug(f"Entering create_file_upload for file: {file_name}, content_type: {content_type}")
    url = "https://api.notion.com/v1/file_uploads"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "accept": "application/json",
        "content-type": "application/json",
        "Notion-Version": notion_version
    }
    payload = {
        "filename": file_name,
        "content_type": content_type
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
                response_json = await response.json()
                logging.debug(
                    f"Successfully created file upload object: ID={response_json['id']}, Upload URL={response_json['upload_url']}")
                return response_json['id'], response_json['upload_url']
    except aiohttp.ClientError as e:
        logging.error(f"Error creating file upload object: {e}", exc_info=True)
        raise  # Re-raise the exception after logging
    except Exception as e:
        logging.error(f"An unexpected error occurred in create_file_upload: {e}", exc_info=True)
        raise  # Re-raise the exception


async def upload_file_to_notion(notion_key: str, notion_version: str, file_path: str, file_upload_id: str,
                                upload_url: str, content_type: str) -> str:
    """
    将本地文件上传到 Notion 提供的上传 URL。
    返回 file_upload_id。
    """
    logging.debug(f"Entering upload_file_to_notion for file_upload_id: {file_upload_id}, upload_url: {upload_url}")
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": notion_version
    }
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at path: {file_path}")

        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=os.path.basename(file_path), content_type=content_type)

                async with session.post(upload_url, headers=headers, data=data) as response:
                    response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        logging.debug(f"Successfully uploaded file with ID: {file_upload_id}")
        return file_upload_id
    except FileNotFoundError:
        logging.error(f"File not found at path: {file_path}", exc_info=True)
        raise
    except aiohttp.ClientError as e:
        logging.error(f"Error uploading file to Notion: {e}", exc_info=True)
        raise  # Re-raise the exception after logging
    except Exception as e:
        logging.error(f"An unexpected error occurred in upload_file_to_notion: {e}", exc_info=True)
        raise  # Re-raise the exception


def is_image_mime_type(mime_type: str) -> bool:
    """
    判断 MIME 类型是否为图片。
    """
    return mime_type and mime_type.startswith('image/')


async def create_notion_page(notion_key: str, notion_version: str, parent_page_id: str, title: str,
                             content_text: str = None) -> str:
    """
    在 Notion 中创建新页面。
    注意：此函数仅创建页面标题和可选的初始文本内容。文件块将通过 append_block_to_notion_page 追加。
    """
    logging.debug(f"Entering create_notion_page with title: {title}")
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Content-Type": "application/json",
        "Notion-Version": notion_version
    }
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
                response_json = await response.json()
                logging.info(f"Successfully created Notion page with ID: {response_json['id']}")
                return response_json['id']
    except aiohttp.ClientError as e:
        logging.error(f"Error creating Notion page: {e}", exc_info=True)
        raise  # Re-raise the exception after logging
    except Exception as e:
        logging.error(f"An unexpected error occurred in create_notion_page: {e}", exc_info=True)
        raise  # Re-raise the exception


async def append_block_to_notion_page(notion_key: str, notion_version: str, page_id: str, file_upload_id: str = None,
                                      file_name: str = None, file_mime_type: str = None,
                                      content_text: str = None) -> Dict:
    """
    向一个已存在的 Notion 页面追加一个文件/图片块或文本块。
    """
    logging.debug(f"Appending block to Notion page {page_id}...")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Content-Type": "application/json",
        "Notion-Version": notion_version
    }
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
        return {}

    payload = {"children": new_blocks}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                response_json = await response.json()
                logging.debug(f"Successfully appended block(s) to Notion page {page_id}")
                return response_json
    except aiohttp.ClientError as e:
        logging.error(f"Error appending block(s) to Notion page {page_id}: {e}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred in append_block_to_notion_page: {e}", exc_info=True)
        raise


# --- Global Media Group Cache ---
media_group_cache: Dict[str, Dict] = {}
MEDIA_GROUP_PROCESS_DELAY = 5  # 设定一个合理的延迟时间


# --- Telegram Bot Handler Functions ---

async def process_media_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job Queue 回调函数，用于处理一个完成的媒体组。
    """
    job_data = context.job.data
    media_group_id = job_data['media_group_id']
    notion_config = job_data['notion_config']

    if media_group_id not in media_group_cache:
        logging.warning(
            f"Media group {media_group_id} not found in cache during processing. May have been processed already.")
        return

    group_data = media_group_cache.pop(media_group_id)  # 取出并移除缓存
    messages_in_group = group_data['messages']

    if not messages_in_group:
        logging.warning(f"Empty media group {media_group_id} received, nothing to process.")
        return

    logging.info(f"Processing media group {media_group_id} with {len(messages_in_group)} files.")

    first_message = messages_in_group[0]['update'].message
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now_beijing = datetime.datetime.now(beijing_tz)

    caption_for_page = None
    for msg_data in messages_in_group:
        if msg_data['update'].message.caption:
            caption_for_page = msg_data['update'].message.caption
            break

    if not caption_for_page:
        caption_for_page = f"媒体组消息 {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}"

    temp_files_to_clean = []
    page_id = None

    try:
        notion_key = notion_config['NOTION_KEY']
        notion_version = notion_config['NOTION_VERSION']
        parent_page_id = notion_config['PAGE_ID']

        logging.info(f"Creating Notion page for media group: {caption_for_page}")

        initial_content_text = None
        if first_message.caption and first_message.caption == caption_for_page:
            initial_content_text = first_message.caption

        page_id = await create_notion_page(
            notion_key=notion_key,
            notion_version=notion_version,
            parent_page_id=parent_page_id,
            title=caption_for_page,
            content_text=initial_content_text
        )
        logging.info(f"Notion page created for media group with ID: {page_id}")
        page_url = f"https://www.notion.so/{page_id.replace('-', '')}"

        for msg_data in messages_in_group:
            file_obj = msg_data['file_obj']
            file_path = msg_data['temp_file_path']
            file_name_for_notion = msg_data['file_name_for_notion']
            content_type = msg_data['content_type']
            msg_caption = msg_data['update'].message.caption

            temp_files_to_clean.append(file_path)

            logging.info(f"Uploading file {file_name_for_notion} from media group to Notion...")
            file_upload_id, upload_url = await create_file_upload(notion_key, notion_version, file_name_for_notion,
                                                                  content_type)
            uploaded_file_id = await upload_file_to_notion(notion_key, notion_version, file_path, file_upload_id,
                                                           upload_url, content_type)

            await append_block_to_notion_page(
                notion_key, notion_version, page_id,
                file_upload_id=uploaded_file_id,
                file_name=file_name_for_notion,
                file_mime_type=content_type
            )
            logging.info(f"File {file_name_for_notion} appended to Notion page {page_id}.")

            if msg_caption and (msg_caption != caption_for_page or not initial_content_text):
                await append_block_to_notion_page(
                    notion_key, notion_version, page_id,
                    content_text=f"文件描述: {msg_caption}"
                )

        await first_message.reply_text(f"您的媒体组消息 ({len(messages_in_group)} 个文件) 已保存到Notion页面：{page_url}")

    except Exception as e:
        logging.exception("Error processing media group:")
        if page_id:
            await first_message.reply_text(f"处理媒体组时发生错误：{type(e).__name__}\n部分内容可能已保存到页面：{page_url}")
        else:
            await first_message.reply_text(f"处理媒体组时发生错误：{type(e).__name__}")
    finally:
        for f_path in temp_files_to_clean:
            if os.path.exists(f_path):
                logging.info(f"Cleaning up temporary file: {f_path}")
                os.remove(f_path)
            else:
                logging.warning(f"Temporary file not found for cleanup: {f_path}")


# 在文件顶部或其他合适的位置定义一个集合来存储已发送反馈的媒体组ID
sent_media_group_feedback = set()


async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE, notion_config: dict) -> None:
    """
    处理所有消息，包括识别媒体组、文本消息和单个文件消息。
    """
    message = update.message
    if not message:
        logging.warning("Received an update without a message object.")
        return

    media_group_id = message.media_group_id

    if media_group_id:
        logging.info(f"Received media group message with ID: {media_group_id}")

        # 检查是否已发送即时反馈
        if media_group_id not in sent_media_group_feedback:
            # Send immediate feedback for media group
            await message.reply_text("已收到您的媒体组消息，正在处理中...")
            # 将当前媒体组ID添加到集合中
            sent_media_group_feedback.add(media_group_id)

        file_obj = None
        file_extension = ''
        content_type = ''
        file_name_for_notion = ''
        temp_file_path = None

        try:
            if message.photo:
                file_obj = await message.photo[-1].get_file()
                file_extension = 'jpg'
                content_type = 'image/jpeg'
                file_name_for_notion = f"telegram_photo_{file_obj.file_id}.jpg"
            elif message.document:
                file_name = message.document.file_name
                file_obj = await message.document.get_file()
                file_extension = file_name.split('.')[-1] if '.' in file_name else 'file'
                content_type = message.document.mime_type or mimetypes.guess_type(file_name)[
                    0] or 'application/octet-stream'
                file_name_for_notion = file_name
            elif message.video:
                file_obj = await message.video.get_file()
                file_extension = 'mp4'
                content_type = message.video.mime_type or 'video/mp4'
                file_name_for_notion = f"telegram_video_{file_obj.file_id}.mp4"
            elif message.audio:
                file_obj = await message.audio.get_file()
                file_extension = message.audio.file_name.split('.')[
                    -1] if message.audio.file_name and '.' in message.audio.file_name else 'mp3'
                content_type = message.audio.mime_type or 'audio/mpeg'
                file_name_for_notion = message.audio.file_name or f"telegram_audio_{file_obj.file_id}.mp3"
            elif message.voice:
                file_obj = await message.voice.get_file()
                file_extension = 'ogg'
                content_type = message.voice.mime_type or 'audio/ogg'
                file_name_for_notion = f"telegram_voice_{file_obj.file_id}.ogg"
            else:
                logging.warning(f"Unsupported file type in media group: {message}. Skipping.")
                return

            if file_obj:
                temp_file_path = f"/tmp/{file_obj.file_id}.{file_extension}"
                await file_obj.download_to_drive(temp_file_path)
                logging.info(f"Downloaded part of media group: {file_obj.file_id}")

                if media_group_id not in media_group_cache:
                    media_group_cache[media_group_id] = {'messages': [], 'job': None}

                media_group_cache[media_group_id]['messages'].append({
                    'update': update,
                    'file_obj': file_obj,
                    'temp_file_path': temp_file_path,
                    'file_name_for_notion': file_name_for_notion,
                    'content_type': content_type
                })

                current_job_info = media_group_cache[media_group_id].get('job')
                if current_job_info and current_job_info.get('job'):
                    current_job = current_job_info['job']
                    current_job.enabled = False
                    logging.debug(f"Disabled old job for media group {media_group_id}")

                new_job = context.job_queue.run_once(
                    process_media_group_job,
                    MEDIA_GROUP_PROCESS_DELAY,
                    data={'media_group_id': media_group_id, 'notion_config': notion_config},
                    name=f"process_media_group_{media_group_id}"
                )
                media_group_cache[media_group_id]['job'] = {'job': new_job}
                logging.info(
                    f"File from media group {media_group_id} cached. Scheduled processing in {MEDIA_GROUP_PROCESS_DELAY} seconds.")

        except Exception as e:
            logging.exception(f"Error handling media group file: {e}")

    elif message.text:
        logging.info("Received standalone text message.")
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now_beijing = datetime.datetime.now(beijing_tz)
        title = f"Telegram消息 {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}"

        try:
            notion_key = notion_config['NOTION_KEY']
            notion_version = notion_config['NOTION_VERSION']
            parent_page_id = notion_config['PAGE_ID']

            logging.info(f"Creating Notion page for text message: {title}")
            page_id = await create_notion_page(
                notion_key=notion_key,
                notion_version=notion_version,
                parent_page_id=parent_page_id,
                title=title,
                content_text=message.text
            )
            logging.info(f"Notion page created for text message with ID: {page_id}")
            page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
            await message.reply_text(f"您的文本已保存到Notion页面：{page_url}")

        except Exception as e:
            logging.exception("Error handling standalone text message:")
            await message.reply_text(f"处理您的文本消息时发生错误：{type(e).__name__}")

    elif message.effective_attachment:
        logging.info("Received standalone file message.")
        file_obj = None
        file_extension = ''
        content_type = ''
        file_name_for_notion = ''
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now_beijing = datetime.datetime.now(beijing_tz)
        caption = message.caption or f"Telegram文件 {now_beijing.strftime('%Y-%m-%d %H:%M:%S')}"
        temp_file_path = None

        try:
            if message.photo:
                file_obj = await message.photo[-1].get_file()
                file_extension = 'jpg'
                content_type = 'image/jpeg'
                file_name_for_notion = f"telegram_photo_{file_obj.file_id}.jpg"
            elif message.document:
                file_name = message.document.file_name
                file_obj = await message.document.get_file()
                file_extension = file_name.split('.')[-1] if '.' in file_name else 'file'
                content_type = message.document.mime_type or mimetypes.guess_type(file_name)[
                    0] or 'application/octet-stream'
                file_name_for_notion = file_name
            elif message.video:
                file_obj = await message.video.get_file()
                file_extension = 'mp4'
                content_type = message.video.mime_type or 'video/mp4'
                file_name_for_notion = f"telegram_video_{file_obj.file_id}.mp4"
            elif message.audio:
                file_obj = await message.audio.get_file()
                file_extension = message.audio.file_name.split('.')[
                    -1] if message.audio.file_name and '.' in message.audio.file_name else 'mp3'
                content_type = message.audio.mime_type or 'audio/mpeg'
                file_name_for_notion = message.audio.file_name or f"telegram_audio_{file_obj.file_id}.mp3"
            elif message.voice:
                file_obj = await message.voice.get_file()
                file_extension = 'ogg'
                content_type = message.voice.mime_type or 'audio/ogg'
                file_name_for_notion = f"telegram_voice_{file_obj.file_id}.ogg"
            else:
                logging.warning("Unsupported standalone file type received.")
                await message.reply_text("抱歉，我目前只支持照片、文档、视频、音频和语音消息。")
                return

            if file_obj:
                temp_file_path = f"/tmp/{file_obj.file_id}.{file_extension}"
                await file_obj.download_to_drive(temp_file_path)
                logging.info("Standalone file downloaded successfully.")

                notion_key = notion_config['NOTION_KEY']
                notion_version = notion_config['NOTION_VERSION']
                parent_page_id = notion_config['PAGE_ID']

                logging.info(f"Creating file upload object in Notion for {file_name_for_notion}")
                file_upload_id, upload_url = await create_file_upload(notion_key, notion_version, file_name_for_notion,
                                                                      content_type)
                logging.info(f"Uploading file to Notion URL: {upload_url}")
                uploaded_file_id = await upload_file_to_notion(notion_key, notion_version, temp_file_path,
                                                               file_upload_id, upload_url,
                                                               content_type)
                logging.info(f"File uploaded to Notion with ID: {uploaded_file_id}")

                logging.info(f"Creating Notion page for standalone file: {caption}")
                page_id = await create_notion_page(
                    notion_key=notion_key,
                    notion_version=notion_version,
                    parent_page_id=parent_page_id,
                    title=caption,
                    content_text=message.caption
                )

                await append_block_to_notion_page(
                    notion_key, notion_version, page_id,
                    file_upload_id=uploaded_file_id,
                    file_name=file_name_for_notion,
                    file_mime_type=content_type
                )
                logging.info("Notion page for standalone file created successfully.")
                page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
                await message.reply_text(f"您上传的{file_name_for_notion} 已保存到Notion页面：{page_url}")

        except Exception as e:
            logging.exception("Error handling standalone file message:")
            await message.reply_text(f"处理您的文件时发生错误：{type(e).__name__}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                logging.info(f"Cleaning up temporary file: {temp_file_path}")
                os.remove(temp_file_path)
                logging.info("Temporary file removed.")

    else:
        logging.warning("Received message with no text, effective_attachment, or media_group_id.")
        await update.message.reply_text("收到一条空消息或不支持的消息类型。")


# 新增一个从 URL 下载文件的异步函数
async def download_file_from_url(file_url: str, temp_dir: str = "/tmp") -> str:
    """
    从给定的 URL 下载文件到临时目录。
    返回下载文件的完整路径。
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_name = os.path.basename(file_url)
    if not file_name:  # Fallback if URL doesn't have a direct file name
        file_name = f"downloaded_file_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    temp_file_path = os.path.join(temp_dir, file_name)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                response.raise_for_status()
                with open(temp_file_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024)  # Read in chunks
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