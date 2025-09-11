from pydantic import BaseModel, Field
from typing import Optional
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger
import aiohttp

logger = setup_logger(__name__)

class EmailAddress(BaseModel):
    name: Optional[str] = None
    address: str

class EmailBody(BaseModel):
    content: Optional[str] = None
    contentType: Optional[str] = None

class OutlookBotMessage(BaseModel):
    messageId: Optional[str] = None
    internetMessageId: Optional[str] = None
    conversationId: Optional[str] = None
    from_sender: EmailAddress = Field(..., alias='from')
    subject: Optional[str] = None
    body: Optional[EmailBody] = None
    bodyPreview: Optional[str] = None

async def send_unauthorised_user_bot_reply(original_message: OutlookBotMessage):
    """Sends a reply to an unregistered user via the Azure Logic App webhook."""
    if not settings.SENDER_SERVICE_URL:
        logger.error("SENDER_SERVICE_URL is not configured. Cannot send bot reply.")
        return

    reply_subject = f"Re: {original_message.subject}" if original_message.subject else "Praxos AI Assistant"
    reply_body = (
        "Hello,\n\nThank you for contacting the MyPraxos AI assistant. "
        "To use this service, you must first connect your Outlook account via the MyPraxos web application.\n\n"
        "Once your account is connected, you can email me directly from your registered address.\n\n"
        "to register your account, please visit https://www.mypraxos.com\n\n"
        "Best,\nThe Praxos Team"
    )

    payload = {
        "to": [original_message.from_sender.address],
        "subject": reply_subject,
        "message": reply_body,
        "replyToMessageId": original_message.messageId,
        "conversationId": original_message.conversationId,
        "internetMessageId": original_message.internetMessageId,
        "token": settings.OUTLOOK_VALIDATION_TOKEN
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.SENDER_SERVICE_URL, json=payload) as response:
                if response.status == 200 or response.status == 202: # Logic App returns 202 Accepted
                    logger.info(f"Successfully sent instructional reply to {original_message.from_sender.address}")
                else:
                    logger.error(f"Failed to send bot reply. Status: {response.status}, Body: {await response.text()}")
    except aiohttp.ClientError as e:
        logger.error(f"Error sending bot reply webhook: {e}", exc_info=True)


async def send_bot_reply(original_message, response_text: str):

    reply_subject = f"Re: {original_message.get('subject')}" if original_message.get('subject') else "Praxos AI Assistant"
    reply_body = response_text
    logger.info(f"Sending bot reply to {original_message.get('from').get('address')} with subject {reply_subject} and body {reply_body}")
    payload = {
        "to": [original_message.get('from').get('address')],
        "subject": reply_subject,
        "message": reply_body,
        "replyToMessageId": original_message.get('messageId'),
        "conversationId": original_message.get('conversationId'),
        "internetMessageId": original_message.get('internetMessageId'),
        "token": settings.OUTLOOK_VALIDATION_TOKEN
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.SENDER_SERVICE_URL, json=payload) as response:
                if response.status == 200 or response.status == 202: # Logic App returns 202 Accepted
                    logger.info(f"Successfully sent new email reply to {original_message.from_sender.address}")
                else:
                    logger.error(f"Failed to send new email reply. Status: {response.status}, Body: {await response.text()}")
    except aiohttp.ClientError as e:
        logger.error(f"Error sending new email reply webhook: {e}", exc_info=True)

async def send_new_email_bot(original_message: OutlookBotMessage, new_email_message: dict):
    reply_subject = f"Re: {new_email_message.get('subject')}" if new_email_message.get('subject') else "Praxos AI Assistant"
    reply_body = new_email_message.get('body')
    logger.info(f"Sending new email reply to {new_email_message.get('recipients')} with subject {reply_subject} and body {reply_body}")
    payload = {
        "to": new_email_message.get('recipients'),
        "subject": reply_subject,
        "message": reply_body,
        "token": settings.OUTLOOK_VALIDATION_TOKEN
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.SENDER_SERVICE_URL, json=payload) as response:
                if response.status == 200 or response.status == 202: # Logic App returns 202 Accepted
                    logger.info(f"Successfully sent new email reply to {new_email_message.get('recipients')}")
                else:
                    logger.error(f"Failed to send new email reply. Status: {response.status}, Body: {await response.text()}")
    except aiohttp.ClientError as e:
        logger.error(f"Error sending new email reply webhook: {e}", exc_info=True)