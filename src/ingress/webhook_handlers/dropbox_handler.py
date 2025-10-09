from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
import json
import hmac
import hashlib
import os

router = APIRouter()
logger = setup_logger(__name__)

def verify_dropbox_signature(body: bytes, signature: str) -> bool:
    """
    Verify Dropbox webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes
        signature: Signature from X-Dropbox-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get Dropbox app secret from environment
        app_secret = os.getenv("DROPBOX_APP_SECRET")
        if not app_secret:
            logger.warning("DROPBOX_APP_SECRET not set - skipping signature verification")
            return True  # Allow for development, but should be required in production

        # Compute HMAC-SHA256
        computed = hmac.new(
            app_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

        # Timing-safe comparison
        return hmac.compare_digest(computed, signature)

    except Exception as e:
        logger.error(f"Error verifying Dropbox signature: {e}")
        return False

@router.get("/dropbox")
async def handle_dropbox_verification(request: Request):
    """
    Handles Dropbox webhook verification (challenge request).

    Dropbox sends GET request with challenge parameter.
    We must echo back the challenge to verify endpoint ownership.
    """
    challenge = request.query_params.get("challenge")

    if challenge:
        logger.info("=" * 80)
        logger.info("DROPBOX WEBHOOK VERIFICATION")
        logger.info("=" * 80)
        logger.info(f"Received challenge: {challenge}")
        logger.info("Responding with challenge to verify endpoint")
        logger.info("=" * 80)

        # Echo back the challenge
        return Response(
            content=challenge,
            media_type="text/plain",
            status_code=200,
            headers={"Content-Type": "text/plain", "X-Content-Type-Options": "nosniff"}
        )

    logger.warning("Dropbox GET request without challenge parameter")
    return Response(status_code=400, content="Missing challenge parameter")

@router.post("/dropbox")
async def handle_dropbox_webhook(request: Request):
    """
    Handles incoming Dropbox webhook notifications.

    Dropbox webhooks are APP-LEVEL (not per-user).
    All users share the same webhook URL configured in Dropbox App Console.
    Reference: https://www.dropbox.com/developers/reference/webhooks

    IMPORTANT: Dropbox only sends user account IDs, not file details.
    You must call /files/list_folder/continue with stored cursor to get changes.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        signature = request.headers.get("X-Dropbox-Signature")
        if signature:
            if not verify_dropbox_signature(body, signature):
                logger.warning("Invalid Dropbox webhook signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse JSON body
        data = json.loads(body.decode('utf-8'))

        logger.info(f"Received Dropbox webhook notification: {json.dumps(data, indent=2)}")

        # Extract accounts with changes
        # Format: {"list_folder": {"accounts": ["dbid:xxx", "dbid:yyy"]}}
        # Or: {"delta": {"users": [12345, 67890]}}
        accounts = []

        if "list_folder" in data:
            accounts = data["list_folder"].get("accounts", [])
        elif "delta" in data:
            # Older format
            accounts = [f"dbid:{uid}" for uid in data["delta"].get("users", [])]

        if not accounts:
            logger.warning("No accounts in Dropbox webhook notification")
            return {"status": "ok"}

        logger.info(f"Dropbox changes for {len(accounts)} account(s): {accounts}")

        # Process each account
        for account_id in accounts:
            # Find user by Dropbox account ID
            # Account ID is stored in integration.metadata.webhook_info.account_id
            user_id = await integration_service.get_user_by_dropbox_account_id(account_id)

            if not user_id:
                logger.warning(f"No user found for Dropbox account ID: {account_id}")
                continue

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                continue

            user_id_var.set(str(user_id))
            modality_var.set("dropbox_webhook")

            # IMPORTANT: Dropbox webhook does NOT include file details
            # You must call /files/list_folder/continue with the stored cursor
            event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": {
                    "account_id": account_id,
                    "note": "Dropbox webhooks don't include file details - use cursor to fetch changes"
                },
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'dropbox_webhook'
                },
                "metadata": {
                    'ingest_type': 'dropbox_webhook',
                    'source': 'dropbox',
                    'webhook_event': True,
                    'account_id': account_id,
                    'requires_cursor_sync': True  # Flag to trigger list_folder/continue call
                }
            }

            # await event_queue.publish(event)
            logger.info(f"Processed Dropbox webhook for user {user_id}, account: {account_id}")

        return Response(status_code=200)

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Dropbox webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Dropbox webhook: {e}", exc_info=True)
        return Response(status_code=200)  # Always return 200 to acknowledge webhook
