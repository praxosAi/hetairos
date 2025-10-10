from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from datetime import datetime, timezone
import json
import os

router = APIRouter()
logger = setup_logger(__name__)

def verify_discord_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """
    Verify Discord Ed25519 signature.

    Args:
        body: Raw request body bytes
        signature: Signature from X-Signature-Ed25519 header (hex string)
        timestamp: Timestamp from X-Signature-Timestamp header (string)

    Returns:
        True if signature is valid
    """
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        # Get public key from environment
        public_key = os.getenv("DISCORD_PUBLIC_KEY")
        if not public_key:
            logger.error("DISCORD_PUBLIC_KEY not set - cannot verify Discord interactions")
            return False  # Require in production

        verify_key = VerifyKey(bytes.fromhex(public_key))

        # Discord verification: f'{timestamp}{body}' as string, then encode
        # This is the CORRECT pattern per Discord docs
        body_str = body.decode('utf-8')
        message = f'{timestamp}{body_str}'.encode()

        try:
            verify_key.verify(message, bytes.fromhex(signature))
            logger.info("Discord signature verified successfully")
            return True
        except BadSignatureError:
            logger.error("Discord signature verification failed: bad signature")
            return False
    except ImportError:
        logger.error("PyNaCl library required for Discord verification. Install: pip install PyNaCl")
        return False
    except Exception as e:
        logger.error(f"Error verifying Discord signature: {e}", exc_info=True)
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

        # Discord uses specific header names
        signature = request.headers.get("X-Signature-Ed25519")
        timestamp = request.headers.get("X-Signature-Timestamp")

        # Signature verification is REQUIRED by Discord
        if not signature or not timestamp:
            logger.error("Missing Discord signature headers")
            raise HTTPException(status_code=401, detail="Missing signature headers")

        # Verify signature BEFORE parsing JSON
        if not verify_discord_signature(body, signature, timestamp):
            logger.warning("Invalid Discord signature")
            raise HTTPException(status_code=401, detail="Invalid request signature")

        # Parse JSON body
        data = json.loads(body.decode('utf-8'))

        interaction_type = data.get("type")

        # Type 1: PING - Discord verification request
        if interaction_type == 1:
            logger.info("=" * 80)
            logger.info("DISCORD WEBHOOK VERIFICATION (PING)")
            logger.info("=" * 80)
            logger.info("Received PING request from Discord")
            logger.info("Responding with PONG (type: 1)")
            logger.info("=" * 80)
            return {"type": 1}

        # Type 2: APPLICATION_COMMAND - Slash command invocation
        if interaction_type == 2:
            command_data = data.get("data", {})
            command_name = command_data.get("name")
            guild_id = data.get("guild_id")
            channel_id = data.get("channel_id")
            user = data.get("member", {}).get("user", {}) if guild_id else data.get("user", {})
            user_id_discord = user.get("id")

            logger.info(f"Received Discord slash command: /{command_name} from user {user_id_discord} in guild {guild_id}")

            # Find user by guild_id (or user_id for DMs)
            user_id = await integration_service.get_user_by_discord_guild_id(guild_id) if guild_id else None

            if not user_id:
                logger.warning(f"No user found for Discord guild ID: {guild_id}")
                # Respond with ephemeral message
                return {
                    "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                    "data": {
                        "content": "Praxos is not configured for this server. Please connect your Discord integration.",
                        "flags": 64  # EPHEMERAL
                    }
                }

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                return {
                    "type": 4,
                    "data": {"content": "User not found", "flags": 64}
                }

            user_id_var.set(str(user_id))
            modality_var.set("discord_webhook")

            # Extract command details
            options = command_data.get("options", [])
            command_text = " ".join([opt.get("value", "") for opt in options])

            logger.info(f"Processing Discord command from user {user_id_discord}: /{command_name} {command_text}")

            # Prepare command event
            command_event = {
                "command_name": command_name,
                "command_text": command_text,
                "options": options,
                "user_id": user_id_discord,
                "channel_id": channel_id,
                "guild_id": guild_id
            }

            # Evaluate triggers
            praxos_api_key = user_record.get("praxos_api_key")
            praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

            event_eval_result = await praxos_client.eval_event(command_event, 'discord_command')

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
                            "text": f"{COMMAND}\n\nCommand: /{command_name} {command_text}\nChannel: {channel_id}\nUser: {user_id_discord}",
                            "raw_event": command_event
                        },
                        "metadata": {
                            "command_name": command_name,
                            "command_text": command_text,
                            "channel": channel_id,
                            "user": user_id_discord,
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

            # Normal command ingestion
            ingestion_event = {
                "user_id": str(user_id),
                "source": "discord",
                "payload": {
                    "text": f"/{command_name} {command_text}",
                    "raw_event": command_event
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
                    'interaction_type': 'application_command',
                    'command_name': command_name,
                    'channel': channel_id,
                    'user': user_id_discord,
                    'guild_id': guild_id
                }
            }

            # Publish to event queue
            await event_queue.publish(ingestion_event)
            logger.info(f"Published Discord command event for user {user_id}")

            # Respond to Discord with deferred response (processing)
            return {
                "type": 5  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
            }

        # Type 3: MESSAGE_COMPONENT - Button/select interactions
        if interaction_type == 3:
            logger.info("Received Discord component interaction")
            return {
                "type": 4,
                "data": {"content": "Button interaction received!", "flags": 64}
            }

        # Unknown interaction type
        logger.warning(f"Unknown Discord interaction type: {interaction_type}")
        return {"type": 4, "data": {"content": "Unknown interaction", "flags": 64}}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Discord webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing Discord webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
