import logging
from src.config.settings import settings
from src.utils.redis_client import publish_message
from src.integrations.whatsapp.client import WhatsAppClient
from src.integrations.telegram.client import TelegramClient
from src.integrations.email.email_bot_client import send_unauthorised_user_bot_reply, send_bot_reply, send_new_email_bot
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service
from src.services.user_service import user_service
logger = setup_logger(__name__)

class EgressService:
    def __init__(self):
        self.whatsapp_client = WhatsAppClient()
        self.telegram_client = TelegramClient()

    async def send_response(self, event: dict, result: dict):
        """
        Routes the final response to the appropriate channel based on the event source.
        """
        source = event.get("source")
        response_text = result.get("response", "Sorry, something went wrong.")

        if not source:
            logger.error(f"No source found in event metadata. Cannot route response. Event: {event}")
            return

        logger.info(f"Routing response for source: {source}, output_type: {event.get('output_type')}")
        if event.get('output_type') not in ['email','websocket','telegram','whatsapp'] and event.get('source') in ['scheduled','recurring']:
            logger.info('incorrect output type for scheduled or recurring event')
            if event.get('metadata',{}).get('original_source', None):
                logger.info(f"Overriding event source from {event['output_type']} to {event['metadata']['original_source']}")
                event['output_type'] = event['metadata']['original_source']

        try:
            if event.get("output_type") == "email" or (event.get("source") == "email" and event.get("output_type") is None):
                if event.get("email_type") == "unauthorised_user":
                    await send_unauthorised_user_bot_reply(event.get("original_message"))
                elif event.get("email_type") == "new":
                    await send_new_email_bot(event.get('metadata',{}).get("original_message"), event.get("new_email_message"))
                else:
                    await send_bot_reply(event.get('metadata',{}).get("original_message"), response_text)
            elif source == "whatsapp" or (event.get("source") == "whatsapp" and event.get("output_type") is None):
                phone_number = event.get("output_phone_number")
                if not phone_number and event.get("user_id"):
                    try:
                        user_record = user_service.get_user_by_id(event.get("user_id"))
                        if user_record:
                            phone_number = user_record.get("phone_number")
                        else:
                            logger.error(f"No user record found for WhatsApp message. Event: {event}")
                            return
                        if not phone_number:
                            logger.error(f"No phone_number in user record for WhatsApp message. Event: {event}")
                            return
                    except Exception as e:
                        logger.error(f"no phone number found for WhatsApp output type. Event: {event}", exc_info=True)
                        return
                await self.whatsapp_client.send_message(phone_number, response_text)
                logger.info(f"Successfully sent response to WhatsApp user {phone_number}")

            elif event.get("output_type") == "telegram" or (event.get("source") == "telegram" and event.get("output_type") is None):
                chat_id = event.get("output_chat_id")
                if not chat_id:
                    try:
                        integration_record = await integration_service.get_integration_record_for_user_and_name(user_id=event.get("user_id"), name="telegram")
                        if integration_record:
                            chat_id = integration_record.get("telegram_chat_id")
                        else:
                            logger.error(f"No integration record found for Telegram message. Event: {event}")
                            return
                    except Exception as e:
                        logger.error(f"No chat_id in user record for Telegram message. Event: {event}, error: {e}", exc_info=True)
                        return
                await self.telegram_client.send_message(chat_id, response_text)
                logger.info(f"Successfully sent response to Telegram user {chat_id}")

            elif source == "websocket":
                logging.info('attempting to publish to websocket')
                token = event.get("metadata", {}).get("token")
                if not token:
                    logger.error(f"No user_id in event for WebSocket message. Event: {event}")
                    return
                
                # The channel name must match what the ingress WebSocket endpoint subscribes to.
                channel = f"ws-out:{token}"
                await publish_message(channel, response_text)
                logger.info(f"Successfully published response to Redis channel '{channel}' for token {token}, which belongs to user {event.get('user_id')}")

            else:
                logger.warning(f"Unknown source '{source}'. Cannot route response.")

        except Exception as e:
            logger.error(f"Failed to send response for source '{source}'. Error: {e}", exc_info=True)

# Singleton instance for easy access
egress_service = EgressService()
