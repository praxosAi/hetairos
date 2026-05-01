from fastapi import APIRouter, Request, HTTPException, Response
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

import httpx

logger = setup_logger(__name__)
router = APIRouter()


def _verify_airtable_signature(body: bytes, header_value: str, mac_secret_base64: str) -> bool:
    """
    Airtable signs webhook pings with HMAC-SHA256 keyed by the base64-decoded
    macSecretBase64 returned at webhook creation. The header value is the base64
    encoded HMAC of the raw body. Some legacy clients see an `hmac-sha256=`
    prefix — accept either shape.
    """
    if not header_value or not mac_secret_base64:
        return False
    try:
        provided = header_value.split("=", 1)[1] if header_value.startswith("hmac-sha256=") else header_value
        key = base64.b64decode(mac_secret_base64)
        digest = hmac.new(key, body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, provided)
    except Exception as e:
        logger.error(f"Error verifying Airtable signature: {e}")
        return False


async def _fetch_payloads(access_token: str, base_id: str, webhook_id: str, cursor: int) -> dict:
    """GET /v0/bases/{baseId}/webhooks/{webhookId}/payloads?cursor=N"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"https://api.airtable.com/v0/bases/{base_id}/webhooks/{webhook_id}/payloads",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"cursor": cursor},
        )
        response.raise_for_status()
        return response.json()


@router.post("/airtable")
async def handle_airtable_webhook(request: Request):
    """
    Airtable sends a thin "ping" POST with shape:
        {"base": {"id": "appXXX"}, "webhook": {"id": "achXXX"}, "timestamp": "..."}
    The actual changes are pulled from /payloads using a per-webhook cursor.
    """
    try:
        body = await request.body()
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Airtable webhook")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        base_id = (data.get("base") or {}).get("id")
        webhook_id = (data.get("webhook") or {}).get("id")
        if not base_id or not webhook_id:
            logger.warning(f"Airtable ping missing base_id/webhook_id: {data}")
            return {"status": "ok"}

        integration = await integration_service.get_user_by_airtable_webhook(base_id, webhook_id)
        if not integration:
            logger.warning(f"No Airtable integration for base={base_id} webhook={webhook_id}")
            return {"status": "ok"}

        user_id = str(integration["user_id"])
        integration_id = str(integration["_id"])
        connected_account = integration.get("connected_account")

        # Look up the matching webhook entry to get its mac secret
        airtable_info = ((integration.get("webhook_info") or {}).get("airtable") or {})
        hooks = airtable_info.get("webhooks", [])
        hook_entry = next(
            (h for h in hooks if h.get("base_id") == base_id and h.get("webhook_id") == webhook_id),
            None,
        )
        if not hook_entry:
            logger.warning(f"No webhook entry found in integration {integration_id} for {webhook_id}")
            return {"status": "ok"}

        signature = request.headers.get("X-Airtable-Content-MAC")
        if signature and not _verify_airtable_signature(body, signature, hook_entry["mac_secret_base64"]):
            logger.warning(f"Invalid Airtable signature for webhook {webhook_id}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "ok"}

        user_id_var.set(user_id)
        modality_var.set("airtable_webhook")

        # Fetch all available payloads, advancing the cursor
        token_info = await integration_service.get_integration_token(user_id, "airtable")
        if not token_info or not token_info.get("access_token"):
            logger.error(f"No Airtable token for user {user_id} during webhook fetch")
            return {"status": "ok"}

        cursor = await integration_service.get_airtable_webhook_cursor(integration_id, webhook_id) or 1
        access_token = token_info["access_token"]

        payloads_collected = []
        for _ in range(20):  # bounded loop in case might_have_more keeps flapping
            payloads_response = await _fetch_payloads(access_token, base_id, webhook_id, cursor)
            payloads = payloads_response.get("payloads", []) or []
            payloads_collected.extend(payloads)
            cursor = payloads_response.get("cursor", cursor)
            if not payloads_response.get("mightHaveMore"):
                break

        await integration_service.set_airtable_webhook_cursor(integration_id, webhook_id, cursor)

        if not payloads_collected:
            logger.info(f"Airtable ping for webhook {webhook_id} but no new payloads")
            return {"status": "ok"}

        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

        for payload in payloads_collected:
            event_for_eval = {
                "base_id": base_id,
                "webhook_id": webhook_id,
                "payload": payload,
            }

            event_eval_result = await praxos_client.eval_event(event_for_eval, "airtable")

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
                    COMMAND += f"Now, upon receiving an Airtable change at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action_item in action_data_list:
                        COMMAND += "The following action was marked as a triggering candidate: " + action_item.get("simple_sentence", "") + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action_item, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. The Airtable event that triggered this action is as follows: "

                    triggered_event = {
                        "user_id": user_id,
                        "source": "triggered",
                        "payload": {
                            "text": COMMAND + json.dumps(event_for_eval, default=str),
                        },
                        "logging_context": {
                            "user_id": user_id_var.get(),
                            "request_id": str(request_id_var.get()),
                            "modality": "triggered",
                        },
                        "metadata": {
                            "ingest_type": "airtable_webhook_triggered",
                            "source": "airtable",
                            "webhook_event": True,
                            "base_id": base_id,
                            "webhook_id": webhook_id,
                            "connected_account": connected_account,
                            "conversation_id": rule_details.get("conversation_id"),
                        },
                    }
                    if not triggered_event["metadata"].get("conversation_id"):
                        triggered_event["metadata"].pop("conversation_id", None)

                    await event_queue.publish(triggered_event)
                    logger.info(f"Published triggered Airtable event for rule {rule_id}")

        logger.info(
            f"Processed {len(payloads_collected)} Airtable payload(s) for user {user_id}, webhook {webhook_id} (advanced cursor to {cursor})"
        )
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Airtable webhook: {e}", exc_info=True)
        return {"status": "ok"}
