from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from datetime import datetime, timezone
import json
import hmac
import hashlib
import os

router = APIRouter()
logger = setup_logger(__name__)

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify Slack webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes
        timestamp: Timestamp from X-Slack-Request-Timestamp header
        signature: Signature from X-Slack-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Get Slack signing secret from environment
        signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        if not signing_secret:
            logger.warning("SLACK_SIGNING_SECRET not set - skipping signature verification")
            return True  # Allow for development

        # Slack signature format: v0=<hash>
        # Compute HMAC-SHA256(signing_secret, "v0:" + timestamp + ":" + body)
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed = 'v0=' + hmac.new(
            signing_secret.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Timing-safe comparison
        return hmac.compare_digest(computed, signature)

    except Exception as e:
        logger.error(f"Error verifying Slack signature: {e}")
        return False

@router.post("/slack")
async def handle_slack_events(request: Request):
    """
    Handles incoming Slack Events API notifications.

    Slack sends webhooks for:
    - message.im (DMs to bot)
    - app_mention (bot mentioned in channel)
    - message.channels (messages in channels bot is in)

    Reference: https://api.slack.com/apis/events-api
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")

        if timestamp and signature:
            # Check timestamp freshness (prevent replay attacks)
            if abs(int(datetime.now(timezone.utc).timestamp()) - int(timestamp)) > 300:  # 5 minutes
                logger.warning("Slack webhook timestamp too old")
                raise HTTPException(status_code=401, detail="Timestamp too old")

            if not verify_slack_signature(body, timestamp, signature):
                logger.warning("Invalid Slack webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON body
        data = json.loads(body.decode('utf-8'))

        # Handle URL verification challenge (first-time setup)
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info("=" * 80)
            logger.info("SLACK WEBHOOK VERIFICATION")
            logger.info("=" * 80)
            logger.info(f"Received challenge: {challenge}")
            logger.info("Responding with challenge to verify endpoint")
            logger.info("=" * 80)
            return {"challenge": challenge}

        # Handle event callbacks
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_type = event.get("type")  # message.im, app_mention, etc.
            team_id = data.get("team_id")

            logger.info(f"Received Slack event: {event_type} from team {team_id}")

            # Find user by team_id
            # Team ID is stored in integration.metadata.webhook_info.team_id
            user_id = await integration_service.get_user_by_slack_team_id(team_id)

            if not user_id:
                logger.warning(f"No user found for Slack team ID: {team_id}")
                return {"status": "ok"}

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                return {"status": "ok"}

            user_id_var.set(str(user_id))
            modality_var.set("slack_webhook")

            # Extract message details
            message_text = event.get("text", "")
            user_slack_id = event.get("user")
            channel = event.get("channel")
            thread_ts = event.get("thread_ts")
            ts = event.get("ts")

            # Ignore bot messages to prevent loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                logger.info("Ignoring bot message to prevent loops")
                return {"status": "ok"}

            logger.info(f"Processing Slack message from user {user_slack_id} in channel {channel}")

            # Evaluate triggers
            praxos_api_key = user_record.get("praxos_api_key")
            praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

            event_eval_result = await praxos_client.eval_event(event, 'slack_message')

            if event_eval_result.get('trigger'):
                # Process triggered actions
                for rule_id, action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)

                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found for rule_id {rule_id}")
                        continue

                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon receiving a Slack message at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger. \n\n The event (Slack message) that triggered this action is as follows: "

                    normalized = {
                        "payload": {
                            "text": f"{COMMAND}\n\nMessage: {message_text}\nChannel: {channel}\nUser: {user_slack_id}",
                            "raw_event": event
                        },
                        "metadata": {
                            "message_text": message_text,
                            "channel": channel,
                            "user": user_slack_id,
                            "source": "slack"
                        }
                    }

                    triggered_event = {
                        "user_id": str(user_id),
                        "source": "triggered",
                        "payload": normalized["payload"],
                        "logging_context": {
                            "user_id": user_id_var.get(),
                            "request_id": str(request_id_var.get()),
                            "modality": "triggered",
                        },
                        "metadata": {
                            **normalized["metadata"],
                            "conversation_id": rule_details.get('conversation_id'),
                        },
                    }
                    if not triggered_event["metadata"].get("conversation_id"):
                        triggered_event['metadata'].pop('conversation_id', None)

                    await event_queue.publish(triggered_event)
                    logger.info(f"Published triggered event for Slack message based on rule {rule_id}")
            else:
                logger.info(f"No trigger found for Slack message.")

            # Normal message ingestion
            ingestion_event = {
                "user_id": str(user_id),
                "source": "slack",
                "payload": {
                    "text": message_text,
                    "raw_event": event
                },
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'slack_webhook'
                },
                "metadata": {
                    'ingest_type': 'slack_webhook',
                    'source': 'slack',
                    'webhook_event': True,
                    'event_type': event_type,
                    'channel': channel,
                    'user': user_slack_id,
                    'thread_ts': thread_ts,
                    'ts': ts,
                    'team_id': team_id
                }
            }

            # Publish to event queue
            await event_queue.publish(ingestion_event)
            logger.info(f"Published Slack message event for user {user_id}")

            return {"status": "ok"}

        # Handle other event types
        logger.info(f"Received Slack event type: {data.get('type')}")
        return {"status": "ok"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Slack webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Slack webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
