from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from datetime import datetime, timezone
import json

router = APIRouter()
logger = setup_logger(__name__)

def verify_discord_signature(body: bytes, signature: str, timestamp: str, public_key: str) -> bool:
    """Verify Discord Ed25519 signature."""
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + body

        try:
            verify_key.verify(message, bytes.fromhex(signature))
            return True
        except BadSignatureError:
            return False
    except Exception as e:
        logger.error(f"Error verifying Discord signature: {e}")
        return False

@router.post("/discord")
async def handle_discord_interactions(request: Request):
    """
    Handles incoming Discord interaction webhooks (slash commands, buttons).

    Discord sends webhooks for:
    - message.im (DMs to bot)
    - app_mention (bot mentioned in channel)
    - message.channels (messages in channels bot is in)

    Reference: https://api.discord.com/apis/events-api
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        timestamp = request.headers.get("X-Discord-Request-Timestamp")
        signature = request.headers.get("X-Discord-Signature")

        if timestamp and signature:
            # Check timestamp freshness (prevent replay attacks)
            if abs(int(datetime.now(timezone.utc).timestamp()) - int(timestamp)) > 300:  # 5 minutes
                logger.warning("Discord webhook timestamp too old")
                raise HTTPException(status_code=401, detail="Timestamp too old")

            if not verify_discord_signature(body, timestamp, signature):
                logger.warning("Invalid Discord webhook signature")
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
            guild_id = data.get("guild_id")

            logger.info(f"Received Discord event: {event_type} from team {guild_id}")

            # Find user by guild_id
            # Team ID is stored in integration.metadata.webhook_info.guild_id
            user_id = await integration_service.get_user_by_discord_guild_id(guild_id)

            if not user_id:
                logger.warning(f"No user found for Discord team ID: {guild_id}")
                return {"status": "ok"}

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                return {"status": "ok"}

            user_id_var.set(str(user_id))
            modality_var.set("discord_webhook")

            # Extract message details
            message_text = event.get("text", "")
            user_discord_id = event.get("user")
            channel = event.get("channel")
            thread_ts = event.get("thread_ts")
            ts = event.get("ts")

            # Ignore bot messages to prevent loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                logger.info("Ignoring bot message to prevent loops")
                return {"status": "ok"}

            logger.info(f"Processing Discord message from user {user_discord_id} in channel {channel}")

            # Evaluate triggers
            praxos_api_key = user_record.get("praxos_api_key")
            praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

            event_eval_result = await praxos_client.eval_event(event, 'discord_message')

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
                    COMMAND += f"Now, upon receiving a Discord message at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details: " + json.dumps(action, default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger. \n\n The event (Discord message) that triggered this action is as follows: "

                    normalized = {
                        "payload": {
                            "text": f"{COMMAND}\n\nMessage: {message_text}\nChannel: {channel}\nUser: {user_discord_id}",
                            "raw_event": event
                        },
                        "metadata": {
                            "message_text": message_text,
                            "channel": channel,
                            "user": user_discord_id,
                            "source": "discord"
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
                    logger.info(f"Published triggered event for Discord message based on rule {rule_id}")
            else:
                logger.info(f"No trigger found for Discord message.")

            # Normal message ingestion
            ingestion_event = {
                "user_id": str(user_id),
                "source": "discord",
                "payload": {
                    "text": message_text,
                    "raw_event": event
                },
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'discord_webhook'
                },
                "metadata": {
                    'ingest_type': 'discord_webhook',
                    'source': 'discord',
                    'webhook_event': True,
                    'event_type': event_type,
                    'channel': channel,
                    'user': user_discord_id,
                    'thread_ts': thread_ts,
                    'ts': ts,
                    'guild_id': guild_id
                }
            }

            # Publish to event queue
            await event_queue.publish(ingestion_event)
            logger.info(f"Published Discord message event for user {user_id}")

            return {"status": "ok"}

        # Handle other event types
        logger.info(f"Received Discord event type: {data.get('type')}")
        return {"status": "ok"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Discord webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Discord webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
