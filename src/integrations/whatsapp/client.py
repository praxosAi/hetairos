import aiohttp
import asyncio
import tempfile
import os
from typing import Dict, Tuple, Optional
from src.config.settings import settings

class WhatsAppClient:
    def __init__(self):
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN              
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        
    async def send_message(self, to_phone: str, message: str, conversation_id: int = None):
        """Send text message via WhatsApp Business API"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": message}
        }

        
        timeout = aiohttp.ClientTimeout(total=10) 
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    
                    if conversation_id and "messages" in result:
                        message_id = result["messages"][0]["id"]
                        from src.utils.database import conversation_db
                        
                        db = conversation_db
                        await db.store_message_status(
                            message_id=message_id,
                            conversation_id=conversation_id,
                            platform="whatsapp",
                            status="sent"
                        )
                    
                    return result
        except asyncio.TimeoutError:
            print(f"WhatsApp API timeout for message to {to_phone}")
            return {"error": "timeout", "message": "Message sending timed out"}
        except aiohttp.ClientError as e:
            print(f"WhatsApp send message error: {e}")
            return {"error": str(e)}
    
    async def mark_as_read(self, message_id: str):
        """Mark message as read"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        # Set timeout for read receipt calls
        timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout for read receipts
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except asyncio.TimeoutError:
            print(f"WhatsApp mark as read timeout for message {message_id}")
            return {"error": "timeout", "message": "Read receipt timed out"}
        except aiohttp.ClientError as e:
            print(f"WhatsApp mark as read error: {e}")
            return {"error": str(e)}
    
    async def retry_failed_message(self, message_id: str, to_phone: str, message: str, 
                                  conversation_id: int = None, max_retries: int = 3):
        """Retry sending a failed message"""
        for attempt in range(max_retries):
            try:
                result = await self.send_message(to_phone, message, conversation_id)
                
                # If successful, update status
                if result and not result.get('error'):
                    if conversation_id:
                        from src.utils.database import conversation_db
                        db = conversation_db
                        await db.store_message_status(
                            message_id=result["messages"][0]["id"],
                            conversation_id=conversation_id,
                            platform="whatsapp",
                            status="sent",
                            error_info=f"Retry successful after {attempt + 1} attempts"
                        )
                    return result
                
                # If failed, wait before retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
            except Exception as e:
                print(f"Retry attempt {attempt + 1} failed for message {message_id}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # All retries failed
        if conversation_id:
            from src.utils.database import conversation_db
            db = conversation_db
            await db.store_message_status(
                message_id=message_id,
                conversation_id=conversation_id,
                platform="whatsapp",
                status="failed",
                error_info=f"Failed after {max_retries} retry attempts"
            )
        
        return {"error": f"Failed after {max_retries} retries"}
    
    async def get_media_url(self, media_id: str) -> Optional[str]:
        """Get media download URL from WhatsApp API"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"https://graph.facebook.com/{self.api_version}/{media_id}",
                    headers=headers
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result.get("url")
        except Exception as e:
            print(f"Error getting media URL for {media_id}: {e}")
            return None
    
    async def download_media_to_file(self, media_url: str, target_file_path: str) -> Tuple[bool, int]:
        """Stream download media file from WhatsApp URL directly to disk"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "WhatsApp-Business-API-Client"
        }
        
        timeout = aiohttp.ClientTimeout(total=30)  # Longer timeout for file downloads
        bytes_downloaded = 0
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(media_url, headers=headers) as response:
                    response.raise_for_status()
                    
                    # Stream download in chunks
                    with open(target_file_path, 'wb') as file:
                        async for chunk in response.content.iter_chunked(8192):  # 8KB chunks
                            file.write(chunk)
                            bytes_downloaded += len(chunk)
                    
                    print(f"Streamed {bytes_downloaded} bytes to {target_file_path}")
                    return True, bytes_downloaded
                    
        except Exception as e:
            print(f"Error streaming media from {media_url}: {e}")
            # Clean up partial file on error
            if os.path.exists(target_file_path):
                try:
                    os.unlink(target_file_path)
                except:
                    pass
            return False, 0
    
    async def download_media_by_id_to_file(self, media_id: str, filename_suffix: str = ".ogg", max_retries: int = 2) -> Tuple[Optional[str], int]:
        """Download media file by media ID directly to temporary file with retry logic"""
        last_error = None
        temp_file_path = None
        
        for attempt in range(max_retries + 1):
            try:
                # Step 1: Get media URL
                media_url = await self.get_media_url(media_id)
                if not media_url:
                    error_msg = f"Failed to get media URL for {media_id}"
                    print(error_msg)
                    last_error = error_msg
                    if attempt < max_retries:
                        await asyncio.sleep(1 * (attempt + 1))  # Increasing delay
                        continue
                    return None, 0
                
                # Step 2: Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=filename_suffix) as temp_file:
                    temp_file_path = temp_file.name
                
                # Step 3: Stream download media content directly to file
                success, bytes_downloaded = await self.download_media_to_file(media_url, temp_file_path)
                if not success:
                    error_msg = f"Failed to stream download media from {media_url}"
                    print(error_msg)
                    last_error = error_msg
                    if attempt < max_retries:
                        await asyncio.sleep(1 * (attempt + 1))  # Increasing delay
                        continue
                    return None, 0
                
                # Success
                if attempt > 0:
                    print(f"Successfully downloaded media {media_id} on attempt {attempt + 1}")
                return temp_file_path, bytes_downloaded
                
            except asyncio.TimeoutError as e:
                error_msg = f"Timeout downloading media {media_id} (attempt {attempt + 1})"
                print(error_msg)
                last_error = error_msg
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))  # Longer delay for timeouts
                    continue
            except Exception as e:
                error_msg = f"Error in download_media_by_id_to_file for {media_id} (attempt {attempt + 1}): {e}"
                print(error_msg)
                last_error = str(e)
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                if attempt < max_retries:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
        
        print(f"Failed to download media {media_id} after {max_retries + 1} attempts. Last error: {last_error}")
        return None, 0