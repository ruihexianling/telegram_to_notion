from config import NOTION_KEY, TELEGRAM_BOT_TOKEN, NOTION_VERSION, PAGE_ID
import os
import requests
import json
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.ext import MessageHandler, ContextTypes

# Function to create a file upload object in Notion
def create_file_upload(file_name, content_type):
    payload = {
        "filename": file_name,
        "content_type": content_type
    }
    response = requests.post("https://api.notion.com/v1/file_uploads", json=payload, headers={
        "Authorization": f"Bearer {NOTION_KEY}",
        "accept": "application/json",
        "content-type": "application/json",
        "Notion-Version": NOTION_VERSION
    })
    if response.status_code != 200:
        raise Exception(f"File creation failed with status code {response.status_code}: {response.text}")
    return response.json()['id'], response.json()['upload_url']

# Function to upload file to Notion
def upload_file_to_notion(file_path, file_upload_id, upload_url, content_type):
    with open(file_path, "rb") as f:
        files = {
            "file": (os.path.basename(file_path), f, content_type)
        }
        response = requests.post(upload_url, headers={
            "Authorization": f"Bearer {NOTION_KEY}",
            "Notion-Version": NOTION_VERSION
        }, files=files)
        if response.status_code != 200:
            raise Exception(f"File upload failed with status code {response.status_code}: {response.text}")
    # No need to return file_upload_id here, upload is complete
    return file_upload_id

# Function to create a new page in Notion under the specified parent page
def create_notion_page(title, content, file_upload_id=None, upload_url=None):
    # Create page payload with parent page ID
    payload = {
        "parent": {
            "type": "page_id",
            "page_id": PAGE_ID
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
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": content
                            }
                        }
                    ]
                }
            }
        ]
    }
    
    # If a file was uploaded, add it as a file block
    if file_upload_id: # Check for file_upload_id
        file_block = {
            "object": "block",
            "type": "image",
            "image": {
                "type": "file_upload",
                "file_upload": {
                    "id": file_upload_id
                }
            }
        }
        payload["children"].append(file_block)
    
    # Create the page
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {NOTION_KEY}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        },
        json=payload
    )
    
    if response.status_code != 200:
        raise Exception(f"Page creation failed with status code {response.status_code}: {response.text}")
    
    return response.json()

# Function to handle file messages (photos, documents, etc.)
async def handle_file_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get file information
    if update.message.photo:
        # For photos, get the largest size
        file_obj = await update.message.photo[-1].get_file()
        file_extension = 'jpg'  # Telegram usually sends photos as JPEG
        content_type = 'image/jpeg'
    elif update.message.document:
        file_obj = await update.message.document.get_file()
        file_name = update.message.document.file_name
        file_extension = file_name.split('.')[-1] if '.' in file_name else 'file'
        content_type = update.message.document.mime_type or 'application/octet-stream'
    elif update.message.video:
        file_obj = await update.message.video.get_file()
        file_extension = 'mp4'  # Telegram usually sends videos as MP4
        content_type = 'video/mp4'
    elif update.message.audio:
        file_obj = await update.message.audio.get_file()
        file_extension = 'mp3'  # Default extension for audio
        content_type = update.message.audio.mime_type or 'audio/mpeg'
    elif update.message.voice:
        file_obj = await update.message.voice.get_file()
        file_extension = 'ogg'  # Telegram usually sends voice as OGG
        content_type = 'audio/ogg'
    else:
        await update.message.reply_text('Unsupported file type.')
        return
    
    # Download the file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file_path = f"temp_file_{timestamp}.{file_extension}"
    await file_obj.download_to_drive(temp_file_path)
    
    # Create a file upload object in Notion
    file_upload_id, upload_url = create_file_upload(f"telegram_file_{timestamp}.{file_extension}", content_type)
    print(f"Created file upload object: ID={file_upload_id}, Upload URL={upload_url}")
    
    # Upload the file to Notion
    upload_result = upload_file_to_notion(temp_file_path, file_upload_id, upload_url, content_type)
    print(f"File upload result: {upload_result}")
    
    # Create a title for the page
    caption = update.message.caption or "File from Telegram"
    title = caption[:50]
    if len(caption) > 50:
        title += "..."
    
    # Create a new page with the file
    page = create_notion_page(title, caption or "File uploaded from Telegram", file_upload_id)
    
    # Clean up the temporary file
    os.remove(temp_file_path)
    
    await update.message.reply_text('Your file has been uploaded to a new Notion page.')

# Telegram text message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get message content
    message_content = update.message.text
    
    # Create a title for the page based on the first line or first few characters
    title = message_content.split('\n')[0][:50] if '\n' in message_content else message_content[:50]
    if len(title) == 50:
        title += "..."
    
    # Create a new page with the message content directly (no file upload for text)
    page = create_notion_page(title, message_content)
    
    await update.message.reply_text('Your message has been uploaded to a new Notion page.')

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all message types and routes them to appropriate handlers."""
    if update.message.text:
        await handle_message(update, context)
    elif update.message.photo or update.message.document or update.message.video or update.message.audio or update.message.voice:
        await handle_file_message(update, context)
    # Add more conditions here for other message types if needed


# Main function to start the bot
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handler for all message types
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all_messages))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(poll_interval=1)


if __name__ == "__main__":
    
    main()