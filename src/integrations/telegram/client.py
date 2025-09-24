import aiohttp
import asyncio
from typing import Optional
import os
import tempfile
from src.config.settings import settings
from src.utils.logging import setup_logger
from src.utils.blob_utils import download_from_blob_storage
from src.utils.text_chunker import TextChunker
import requests
class TelegramClient:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.logger = setup_logger("telegram_client")

    async def send_message(self, chat_id: int, text: str):
        """Send text message via Telegram Bot API, chunking smartly if it's too long."""
        responses = []
        # Using 4000 to be safe, as Telegram's official limit is 4096
        chunker = TextChunker(max_length=4000)
        
        for chunk in chunker.chunk(text):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
            }
            responses.append(await self._make_request("sendMessage", payload))
        
        return responses

    async def send_media(self, chat_id: int, media_obj: dict):
        media_url = media_obj.get("url")
        file_name = media_obj.get("file_name", "file")
        media_type = media_obj.get("file_type", "document")  # Default to Document if not specified
        caption = media_obj.get("caption", "")
        if media_type == 'audio':
            media_type = 'voice'
        if media_type == 'image':
            media_type = 'photo'
        """Send a media message via Telegram."""
        media_bytes = requests.get(media_url).content

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_file.write(media_bytes)
            temp_file_path = temp_file.name
        
        api_method = f"send{media_type.capitalize()}"
        
        data = aiohttp.FormData()
        data.add_field('chat_id', str(chat_id))
        data.add_field(media_type.lower(), open(temp_file_path, 'rb'), filename=os.path.basename(temp_file_path))
        if caption:
            data.add_field('caption', caption)

        result = await self._make_request(api_method, data, is_json=False)
        
        os.unlink(temp_file_path)
        return result

    async def _make_request(self, method: str, payload: dict, is_json: bool = True):
        """Make a request to the Telegram Bot API"""
        url = f"{self.base_url}/{method}"
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if is_json:
                    async with session.post(url, json=payload) as response:
                        response.raise_for_status()
                        return await response.json()
                else:
                    async with session.post(url, data=payload) as response:
                        response.raise_for_status()
                        return await response.json()
        except aiohttp.ClientError as e:
            self.logger.error(f"Telegram API error: {e}")
            return None
    async def get_file_path(self, file_id: str):
        """Get the file path of a file from Telegram Bot API"""
        url = f"{self.base_url}/getFile?file_id={file_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
    async def download_file_to_temp_path(self, file_path: str, file_unique_id: str):
        """Download a file from Telegram Bot API"""
        bytes_downloaded = 0
        extension = file_path.split(".")[-1]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                with open(file_unique_id + "." + extension, 'wb') as file:
                    async for chunk in response.content.iter_chunked(8192):  # 8KB chunks
                        file.write(chunk)
                        bytes_downloaded += len(chunk)
                return file_unique_id + "." + extension