import aiohttp
import asyncio
from typing import Optional

from src.config.settings import settings
from src.utils.logging import setup_logger

class TelegramClient:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.logger = setup_logger("telegram_client")

    async def send_message(self, chat_id: int, text: str):
        """Send text message via Telegram Bot API"""
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        return await self._make_request("sendMessage", payload)

    async def _make_request(self, method: str, payload: dict):
        """Make a request to the Telegram Bot API"""
        url = f"{self.base_url}/{method}"
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
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