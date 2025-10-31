from fastapi import APIRouter, Request
from src.integrations.telegram.client import TelegramClient
from src.utils.logging import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.post("/telegram/notify-link-success")
async def notify_link_success(request: Request):
    """
    Internal endpoint: Notify user via Telegram that account linking succeeded.
    Called by mypraxos-backend after successful account linking.
    """
    try:
        data = await request.json()
        chat_id = data.get("telegram_chat_id")
        user_name = data.get("user_name", "")

        if not chat_id:
            return {"status": "error", "message": "telegram_chat_id required"}

        telegram_client = TelegramClient()

        message = f"""✅ Success!

Your Telegram account has been linked to your Praxos account.

You can now chat with me here anytime{', ' + user_name if user_name else ''}!

How can I help you today?"""

        await telegram_client.send_message(chat_id, message)

        logger.info(f"Sent link success notification to chat_id {chat_id}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error sending link notification: {e}")
        return {"status": "error", "message": str(e)}
