import aiohttp
import asyncio
import tempfile
import os
from typing import Dict, Tuple, Optional
from src.config.settings import settings
from src.utils.logging import setup_logger
from src.utils.blob_utils import get_blob_sas_url

class IMessageClient:
    def __init__(self):
        self.api_key = settings.SENDBLUE_API_KEY
        self.api_secret = settings.SENDBLUE_API_SECRET
        self.base_url = "https://api.sendblue.co/api"
        self.logger = setup_logger("imessage_client")
        
    async def send_message(self, to_number: str, message: str):
        """Send text message via Sendblue iMessage API"""
        headers = {
            "sb-api-key-id": self.api_key,
            "sb-api-secret-key": self.api_secret,
            "Content-Type": "application/json"
        }
        
        payload = {
            "number": to_number,
            "content": message
        }
        
        return await self._make_request("POST", f"{self.base_url}/send-message", payload)

    async def send_media(self, to_number: str, file_obj: str):
        """Send media message via Sendblue iMessage API"""
        url = file_obj.get("url")
        payload = {
            "number": to_number,
            "media_url": url
        }
        
        return await self._make_request("POST", f"{self.base_url}/send-message", payload)

    async def download_media_to_temp_path(self, media_url: str, file_name: str) -> Optional[str]:
        """Download a file from a URL to a temporary path"""
        bytes_downloaded = 0
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(media_url) as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_name) as temp_file:
                        async for chunk in response.content.iter_chunked(8192):
                            temp_file.write(chunk)
                            bytes_downloaded += len(chunk)
                        self.logger.info(f"Downloaded {bytes_downloaded} bytes to {temp_file.name}")
                        return temp_file.name
        except aiohttp.ClientError as e:
            self.logger.error(f"Error downloading media from {media_url}: {e}")
            return None

    async def _make_request(self, method: str, url: str, payload: dict = None):
        """Make a request to the Sendblue API"""
        headers = {
            "sb-api-key-id": self.api_key,
            "sb-api-secret-key": self.api_secret,
            "Content-Type": "application/json"
        }
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            self.logger.error(f"Sendblue API error: {e}")
            return None
