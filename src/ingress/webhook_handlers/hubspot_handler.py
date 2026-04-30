from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.utils.database import db_manager
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
import time

logger = setup_logger(__name__)
router = APIRouter()

_MAX_TIMESTAMP_SKEW_MS = 5 * 60 * 1000  # HubSpot rejects > 5 min


def _verify_hubspot_signature(method: str, url: str, body: bytes, signature: str, timestamp: str) -> bool:
    """
    HubSpot v3 signature: base64( HMAC-SHA256( client_secret, method + url + body + timestamp ) ).
    See https://developers.hubspot.com/docs/api/webhooks/validating-requests
    """
    secret = os.getenv("HUBSPOT_CLIENT_SECRET")
    if not secret:
        logger.warning("HUBSPOT_CLIENT_SECRET not set — skipping signature verification")
        return True
    if not signature or not timestamp:
        return False

    try:
        ts_ms = int(timestamp)
        if abs(int(time.time() * 1000) - ts_ms) > _MAX_TIMESTAMP_SKEW_MS:
            logger.warning(f"HubSpot timestamp skew too large: {ts_ms}")
            return False

        message = method.upper().encode() + url.encode() + body + timestamp.encode()
        digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"Error verifying HubSpot signature: {e}")
        return False


@router.post("/hubspot")
async def handle_hubspot_webhook(request: Request):
    """
    HubSpot webhooks are app-level: subscriptions are configured once in the
    developer portal, and HubSpot delivers an array of events keyed by
    portalId. We map portalId -> Praxos user via the integration record.
    """
    try:
        body = await request.body()

        # HubSpot v3 signs against the URL it POSTs to. Behind a proxy, prefer
        # an explicit override so signing matches the public URL.
        public_url = os.getenv("HUBSPOT_WEBHOOK_URL") or str(request.url)
        signature = request.headers.get("X-HubSpot-Signature-v3")
        timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
        if signature and not _verify_hubspot_signature(request.method, public_url, body, signature, timestamp):
            logger.warning("Invalid HubSpot webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        try:
            events = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in HubSpot webhook")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        if not isinstance(events, list):
            logger.warning(f"Unexpected HubSpot payload shape: {type(events).__name__}")
            return {"status": "ok"}

        # Group events by portalId so we look up the user once per portal
        events_by_portal: dict = {}
        for event in events:
            portal_id = event.get("portalId")
            if portal_id is None:
                continue
            events_by_portal.setdefault(portal_id, []).append(event)

        for portal_id, portal_events in events_by_portal.items():
            try:
                lookup = await integration_service.get_user_by_hubspot_portal_id(portal_id)
                if not lookup:
                    logger.warning(f"No HubSpot integration for portal_id={portal_id}")
                    continue
                user_id, connected_account = lookup

                user_record = user_service.get_user_by_id(user_id)
                if not user_record:
                    logger.error(f"User not found for ID {user_id}")
                    continue

                user_id_var.set(user_id)
                modality_var.set("hubspot_webhook")

                praxos_api_key = user_record.get("praxos_api_key")
                praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

                for event in portal_events:
                    event_eval_result = await praxos_client.eval_event(event, "hubspot_event")

                    if event_eval_result.get("trigger"):
                        for rule_id, action_data_list in event_eval_result.get("fired_rule_actions_details", {}).items():
                            if isinstance(action_data_list, str):
                                action_data_list = json.loads(action_data_list)

                            rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                            if not rule_details:
                                logger.error(f"No trigger details for rule_id {rule_id}; skipping")
                                continue

                            COMMAND = ""
                            COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                            COMMAND += f"Now, upon receiving a HubSpot event at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                            for action_item in action_data_list:
                                COMMAND += "The following action was marked as a triggering candidate: " + action_item.get("simple_sentence", "") + ". \n"
                                COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action_item, default=str) + ". \n\n"
                            COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger. The HubSpot event that triggered this action is as follows: "

                            triggered_event = {
                                "user_id": user_id,
                                "source": "triggered",
                                "payload": {
                                    "text": COMMAND + json.dumps(event, default=str),
                                },
                                "logging_context": {
                                    "user_id": user_id_var.get(),
                                    "request_id": str(request_id_var.get()),
                                    "modality": "triggered",
                                },
                                "metadata": {
                                    "ingest_type": "hubspot_webhook_triggered",
                                    "source": "hubspot",
                                    "webhook_event": True,
                                    "subscription_type": event.get("subscriptionType"),
                                    "object_id": event.get("objectId"),
                                    "portal_id": portal_id,
                                    "connected_account": connected_account,
                                    "conversation_id": rule_details.get("conversation_id"),
                                },
                            }
                            if not triggered_event["metadata"].get("conversation_id"):
                                triggered_event["metadata"].pop("conversation_id", None)

                            await event_queue.publish(triggered_event)
                            logger.info(f"Published triggered HubSpot event for rule {rule_id}")

                logger.info(f"Processed {len(portal_events)} HubSpot event(s) for user {user_id} (portal {portal_id})")
            except Exception as e:
                logger.error(f"Error processing HubSpot events for portal {portal_id}: {e}", exc_info=True)
                continue

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing HubSpot webhook: {e}", exc_info=True)
        return {"status": "ok"}
