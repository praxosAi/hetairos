from fastapi import APIRouter, Request, HTTPException
import logging
from src.core.event_queue import event_queue
from src.integrations.email.gmail_pubsub import gmail_pubsub_manager
from src.services.user_service import user_service
from src.integrations.email.gmail_client import GmailIntegration
from src.services.conversation_manager import ConversationManager
from src.utils.database import db_manager
from src.core.praxos_client import PraxosClient
from src.services.integration_service import integration_service
from datetime import datetime, timezone
import json
router = APIRouter()
from src.utils.logging.base_logger import setup_logger,user_id_var, modality_var, request_id_var
logger = setup_logger(__name__)

@router.post("/gmail")
async def handle_gmail_webhook(request: Request):
    """
    Handles incoming Gmail push notifications via Google Cloud Pub/Sub.
    """
    try:
        body = await request.json()

        parsed_message = gmail_pubsub_manager.parse_pubsub_message(body)
        logger.info(f"Parsed Pub/Sub message: {parsed_message}")
        if not parsed_message or not gmail_pubsub_manager.validate_pubsub_message(parsed_message):
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message")

        gmail_data = gmail_pubsub_manager.extract_gmail_notification_data(parsed_message)
        user_email = gmail_data.get("email_address")
        history_id = gmail_data.get("history_id")

        logger.info(f"Received Gmail webhook for user {user_email} with history ID {history_id}")

        user_id = await integration_service.get_user_by_integration_name("gmail", user_email)
        if not user_id:
            logger.error(f"No user found for Gmail integration with email {user_email}")
            return {"status": "error", "message": "No user found for this Gmail integration"}
        user_id = user_id[0]
        if not user_id:
            logger.error(f"No Gmail integration found for user {user_email}")
            return {"status": "error", "message": "No Gmail integration found"}
        user_record = user_service.get_user_by_id(user_id)
        if not user_record:
            logger.error(f"User not found for ID {user_id}")
            return {"status": "error", "message": "User not found"}

        try:
            gmail_integration = GmailIntegration(user_id)
            if not await gmail_integration.authenticate():
                logger.error(f"Failed to authenticate Gmail for user {user_id} and email {user_email}")
                return {"status": "error", "message": "Failed to authenticate Gmail"}
        except Exception as e:
            logger.error(f"Exception during Gmail authentication for user {user_id} and email {user_email}: {e}")
            return {"status": "error", "message": "Exception during Gmail authentication"}
        checkpoint = await integration_service.get_gmail_checkpoint(user_id, user_email)
        if not checkpoint:
            # Seed once: store current mailbox historyId and exit (no backfill)
            prof = gmail_integration.services[user_email].users().getProfile(userId="me").execute()
            await integration_service.set_gmail_checkpoint(user_id, user_email, str(prof["historyId"]))
            logger.info(f"Seeded mailbox checkpoint for {user_email} at {prof['historyId']}")
            return {"status": "seeded"}
        message_ids, new_checkpoint = gmail_integration.get_changed_message_ids_since(
                start_history_id=checkpoint,
                account=user_email,
                history_types=["messageAdded"],  # add "labelAdded" if INBOX transitions matter
            )
        new_messages = []
        if message_ids:
            new_messages = gmail_integration.get_messages_by_ids(message_ids, account=user_email)

        if new_checkpoint:
            await integration_service.set_gmail_checkpoint(user_id, user_email, new_checkpoint)

        if not new_messages:
            logger.info(f"No new messages for {user_email} since checkpoint {checkpoint} (advanced_to={new_checkpoint})")
            return {"status": "ok", "fetched": 0, "advanced_to": new_checkpoint}
        
        inserted_ids = await db_manager.insert_or_reject_emails(new_messages, user_id)
        inserted = [iid for iid in inserted_ids if iid]
        logger.info(f"Fetched {len(new_messages)}; inserted {len(inserted)} for {user_email}")

        # Process only those actually inserted
        praxos_api_key = user_record.get("praxos_api_key")
        praxos_client = PraxosClient(f"env_for_{user_record.get('email')}", api_key=praxos_api_key)

        for message, inserted_id in zip(new_messages, inserted_ids):
            if not inserted_id:
                logger.info(f"Message {message.get('id')} already processed, skipping.")
                continue

            logger.info(f"Processing new message {message.get('id')}")
            event_eval_result = await praxos_client.eval_event(message, 'gmail')
            logger.info(f"Event evaluation result: {event_eval_result}")
            if event_eval_result.get('trigger'):




                for rule_id,action_data in event_eval_result.get('fired_rule_actions_details', {}).items():
                    if isinstance(action_data, str):
                        action_data = json.loads(action_data)
                    rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
                    if not rule_details:
                        logger.error(f"No trigger details found in DB for rule_id {rule_id}. trigger may be inactive, deleted, or flawed.")
                        continue
                    
                    COMMAND = ""
                    COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
                    COMMAND += f"Now, upon receiving a new email,  at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
                    for action in action_data:
                        COMMAND += "The following action was marked as a triggering candidate: " + action.get('simple_sentence', '') + ". \n"
                        COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action,default=str) + ". \n\n"
                    COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (email, in this case) that triggered this action is as follows: "

                    normalized = await gmail_integration.normalize_gmail_message_for_ingestion(
                                user_record=user_record,
                                message=message,
                                account=user_email,
                                command_prefix=COMMAND,
                            )
                    ingestion_event = {
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
                            'source': 'triggered_gmail',
                            "subject": normalized["subject"],
                            "from": normalized["from"],
                            "to": normalized["to"],
                            "thread_id": normalized["thread_id"],
                            "conversation_id": rule_details.get('conversation_id'),
                        },
                    }
                    if not ingestion_event["metadata"].get("conversation_id"):
                        ingestion_event['metadata'].pop('conversation_id', None)
                    await event_queue.publish(ingestion_event)
                    logger.info(f"Published triggered event for message {message.get('id')} based on rule {rule_id}")
                    ### here, we should sleep.
                # if rule_details.get('one_time', True):
                #     db_manager.mark_trigger_as_used(rule_id)
                #     logger.info(f"Marked one-time trigger {rule_id} as used.")
            else:
                logger.info(f"Evaluation found no trigger for message {message.get('id')}. Proceeding with normal ingestion.")
            user_id_var.set(str(user_id))
            modality_var.set("gmail_webhook")
            if message.get('metadata') is None:
                message['metadata'] = {}
            message['metadata']['inserted_id'] = inserted_id

            ingestion_event = {
                "user_id": str(user_id),
                "source": "event_ingestion",
                "payload": message,
                "logging_context": {
                    'user_id': user_id_var.get(),
                    'request_id': str(request_id_var.get()),
                    'modality': 'ingestion_api'
                },
                "metadata": {
                    'ingest_type': 'gmail_webhook',
                    'source': 'gmail',
                    'gmail_webhook_event': True,
                    'gmail_message_id': message.get("id"),
                    'inserted_id': inserted_id
                }
            }
            # await event_queue.publish(ingestion_event)

        return {
            "status": "ok",
            "fetched": len(new_messages),
            "inserted": len(inserted),
            "advanced_to": new_checkpoint
        }
    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {e}", exc_info=True)
        return {"status": "ok"}
        ### TODO figure out how to ingest this email.
        # await event_queue.publish(ingestion_event)
        # for user_id in user_ids:
        #     user_id_var.set(str(user_id))
        #     modality_var.set("gmail")
            
        #     event = {
        #         "user_id": str(user_id),
        #         "source": "gmail",
        #         "payload": {"text": input_text},
        #         "logging_context": {'user_id': str(user_id), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
        #         "metadata": {"gmail_message_id": message.get("id"), 'source':'gmail'}
        #     }
        #     await event_queue.publish(event)

    
