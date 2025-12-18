import aiohttp
from typing import Optional
import os
import tempfile
import re
from src.config.settings import settings
from src.utils.logging import setup_logger
from src.integrations.telegram.formatter import TelegramHTMLFormatter
from src.integrations.telegram.chunker import TelegramHTMLChunker
from src.utils.text_chunker import TextChunker
import requests
import json
class TelegramClient:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.logger = setup_logger("telegram_client")

    async def send_typing_action(self, chat_id: int):
        """Send typing action to show the bot is typing."""
        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }
        return await self._make_request("sendChatAction", payload)

    async def send_message(self, chat_id: int, text: str):
        """Send text message via Telegram Bot API with HTML formatting support."""
        responses = []

        try:
            # Convert markdown to HTML
            formatter = TelegramHTMLFormatter()
            html_text = formatter.convert_markdown_to_html(text)
            parse_mode = "HTML"
        except Exception as e:
            # Level 1 fallback: If formatting fails, use plain text
            self.logger.warning(f"HTML formatting failed, using plain text: {e}", exc_info=True)
            html_text = text
            parse_mode = None
        
        if parse_mode is None:
            chunker = TextChunker(max_length=4000)
        else :
            # Chunk with formatting awareness
            chunker = TelegramHTMLChunker(max_length=4000)

        for chunk in chunker.chunk(html_text):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            response = await self._make_request("sendMessage", payload)

            # Level 2 fallback: If API returns 400 error (bad formatting),
            # retry the same chunk as plain text
            if not response or not response.get("ok"):
                self.logger.warning(
                    f"Telegram API returned error for formatted chunk, "
                    f"retrying as plain text. Error: {response.get('description') if response else 'No response'}"
                )
                # Strip HTML tags and retry as plain text
                if parse_mode:
                    chunk = self._strip_html_tags(chunk)

                plain_payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                }
                response = await self._make_request("sendMessage", plain_payload)

            responses.append(response)

        return responses

    def _strip_html_tags(self, html: str) -> str:
        """Strip HTML tags from text for plain text fallback."""
        # Remove HTML tags but keep content
        return re.sub(r'<[^>]+>', '', html)

    async def send_media(self, chat_id: int, media_obj: dict):
        if not isinstance(media_obj, dict):
            if isinstance(media_obj, str):
                media_obj = json.loads(media_obj)
            else:
                try:
                    media_obj = media_obj.dict()
                except:
                    self.logger.error(f"Invalid media_obj format: {media_obj}")
                    return None
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

    async def send_location(self, chat_id: int, latitude: float, longitude: float, location_name: Optional[str] = None):
        """Send a location via Telegram Bot API."""
        payload = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
        }
        self.logger.info(f"Sending location to chat {chat_id}: {latitude}, {longitude} ({location_name or 'unnamed'})")
        return await self._make_request("sendLocation", payload)

    async def request_location(self, chat_id: int, message: str = "Please share your location"):
        """Request location from user via keyboard button."""
        payload = {
            "chat_id": chat_id,
            "text": message,
            "reply_markup": {
                "keyboard": [
                    [
                        {
                            "text": "📍 Share My Location",
                            "request_location": True
                        }
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
        }
        self.logger.info(f"Requesting location from chat {chat_id}")
        return await self._make_request("sendMessage", payload)

    async def send_message_with_inline_keyboard(self, chat_id: int, text: str, inline_keyboard: dict):
        """Send text message with inline keyboard buttons."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": inline_keyboard
        }
        return await self._make_request("sendMessage", payload)

    async def send_account_selection_prompt(self, chat_id: int, first_name: str):
        """Send interactive prompt asking if user has existing account."""
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Yes, I have an account", "callback_data": "link_account"}
                ],
                [
                    {"text": "🆕 No, create my account", "callback_data": "create_account"}
                ]
            ]
        }

        welcome_text = f"👋 Hello {first_name}!\n\nAre you already registered on Praxos?"

        return await self.send_message_with_inline_keyboard(
            chat_id=chat_id,
            text=welcome_text,
            inline_keyboard=inline_keyboard
        )
    
    async def send_account_connection_prompt(self, chat_id: int, account_id: str, first_name: str):
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Connect my telegram account", "url": f"https://app.mypraxos.com/integrations?auto-connect=true&provider=telegram&username=@{account_id}"}
                ]
            ]
        }

        welcome_text = f"👋 Hello {first_name}!\n\nLet's connect your Telegram account to myPraxos. Click the button below to proceed."

        return await self.send_message_with_inline_keyboard(
            chat_id=chat_id,
            text=welcome_text,
            inline_keyboard=inline_keyboard
        )

    async def send_language_selection(self, chat_id: int, first_name: str):
        """Send language selection prompt to new user."""
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🇺🇸 English", "callback_data": "lang_en"},
                    {"text": "🇪🇸 Español", "callback_data": "lang_es"}
                ],
                [
                    {"text": "🇵🇹 Português", "callback_data": "lang_pt"},
                    {"text": "🇷🇺 Русский", "callback_data": "lang_ru"}
                ],
                [
                    {"text": "🇮🇷 فارسی", "callback_data": "lang_fa"},
                    {"text": "🇫🇷 Français", "callback_data": "lang_fr"}
                ],
                [
                    {"text": "🇩🇪 Deutsch", "callback_data": "lang_de"},
                    {"text": "🇸🇦 العربية", "callback_data": "lang_ar"}
                ]
            ]
        }

        text = f"👋 Welcome, {first_name}!\n\n🌍 Please select your preferred language:"

        return await self.send_message_with_inline_keyboard(
            chat_id=chat_id,
            text=text,
            inline_keyboard=inline_keyboard
        )

    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None):
        """Answer a callback query from inline keyboard button."""
        payload = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text

        return await self._make_request("answerCallbackQuery", payload)

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