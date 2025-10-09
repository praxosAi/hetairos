from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
import json
import hmac
import hashlib
import base64
import os

router = APIRouter()
logger = setup_logger(__name__)

def verify_trello_webhook_signature(body: bytes, callback_url: str, signature: str) -> bool:
    """
    Verify Trello webhook signature using HMAC-SHA1.

    Args:
        body: Raw request body bytes
        callback_url: The webhook callback URL
        signature: Base64-encoded signature from X-Trello-Webhook header

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get Trello webhook secret from environment
        secret = os.getenv("TRELLO_WEBHOOK_SECRET")
        if not secret:
            logger.warning("TRELLO_WEBHOOK_SECRET not set - skipping signature verification")
            return True  # Allow for development, but should be required in production

        # Trello signature format: content + URL
        content = body + callback_url.encode('utf-8')

        # Compute HMAC-SHA1
        computed = base64.b64encode(
            hmac.new(secret.encode('utf-8'), content, hashlib.sha1).digest()
        ).decode('utf-8')

        # Timing-safe comparison
        return hmac.compare_digest(computed, signature)

    except Exception as e:
        logger.error(f"Error verifying Trello signature: {e}")
        return False

@router.post("/trello")
@router.head("/trello")
async def handle_trello_webhook(request: Request):
    """
    Handles incoming Trello webhook notifications.

    Trello sends rich webhook notifications for board/card changes.
    Reference: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/

    Trello includes full action data in the webhook payload (not just a notification).
    """
    try:
        # Trello sends HEAD requests to verify the endpoint is alive
        if request.method == "HEAD":
            logger.info("Received Trello HEAD request (health check)")
            return Response(status_code=200)

        # Get raw body for signature verification
        body = await request.body()

        # Verify signature if present
        signature = request.headers.get("X-Trello-Webhook")
        if signature:
            callback_url = str(request.url)
            if not verify_trello_webhook_signature(body, callback_url, signature):
                logger.warning("Invalid Trello webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON body
        data = json.loads(body.decode('utf-8'))

        # Extract action details
        action = data.get("action", {})
        action_type = action.get("type")  # e.g., "createCard", "updateCard", "commentCard"
        action_data = action.get("data", {})
        board = action_data.get("board", {})
        card = action_data.get("card")
        list_obj = action_data.get("list")
        member = action.get("memberCreator", {})

        logger.info(f"Received Trello webhook: {action_type} on board {board.get('name')}")

        # Find user by board ID
        # Board IDs are stored in integration.metadata.webhook_info.webhooks[].board_id
        board_id = board.get("id")
        if not board_id:
            logger.warning("No board ID in Trello webhook")
            return {"status": "ok"}

        user_id = await integration_service.get_user_by_trello_board_id(board_id)

        if not user_id:
            logger.warning(f"No user found for Trello board ID: {board_id}")
            return {"status": "ok"}

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        user_id_var.set(str(user_id))
        modality_var.set("trello_webhook")

        # Trello webhooks include full action data - very rich payload
        event = {
            "user_id": str(user_id),
            "source": "event_ingestion",
            "payload": {
                "action_type": action_type,
                "action_data": action_data,
                "member": member,
                "board": board,
                "card": card,
                "list": list_obj,
                "full_action": action
            },
            "logging_context": {
                'user_id': user_id_var.get(),
                'request_id': str(request_id_var.get()),
                'modality': 'trello_webhook'
            },
            "metadata": {
                'ingest_type': 'trello_webhook',
                'source': 'trello',
                'webhook_event': True,
                'action_type': action_type,
                'board_id': board_id,
                'board_name': board.get('name'),
                'card_id': card.get('id') if card else None,
                'card_name': card.get('name') if card else None
            }
        }

        # await event_queue.publish(event)
        logger.info(f"Processed Trello webhook for user {user_id}, action: {action_type}, board: {board.get('name')}")

        return {"status": "ok"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Trello webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Trello webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
