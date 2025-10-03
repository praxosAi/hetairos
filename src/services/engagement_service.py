from src.utils.logging.base_logger import setup_logger
from src.core.event_queue import event_queue
logger = setup_logger(__name__)
async def research_user_and_engage(user_record, source, messaging_user_id,timestamp,request_id_var):
    if not user_record.get('needs_first_interaction'):
        logger.info(f"User {str(user_record['_id'])} does not need first interaction. Skipping research and engagement.")
        return
    
    logger.info(f"Researching user {str(user_record['_id'])} for user {messaging_user_id} with modality {source}")
    first_name = user_record.get("first_name", "")
    last_name = user_record.get("last_name", "")
    email = user_record.get("email", "")
    timezone = user_record.get("timezone", "UTC")
    city = user_record.get("city", "")
    country = user_record.get("country", "")

    text = f"""
        THIS IS A SYSTEM COMMAND. THIS IS WHY IT IS MORE DETAILED AND HAS PARTICULAR INSTRUCTIONS.
        A new user with the following details has just joined praxos, and this is the first interaction with them.
        Please research the user online, using only public sources. Try to learn something about them, and then ask a question about who they potentially are. Make it engaging and fun, but short. the idea is to get them to respond and start a conversation.
        if you cannot find anything about them, Just say something about them being mysterious, so you can't figure out who they are.
        In terms of tone, however, be very much like a scifi assistant. The previous message you received from them, which is not in context was:
        they sent you: "INITIALIZE COMMUNICATION PROTOCOL
            Security Code [REDACTED]
            Acknowledge handshake
            "
        you responded:
            HANDSHAKE ACKNOWLEDGED. \n\nWhatsapp Connection Initialized.
        
        Now, use the same format to ask them a question. Use your tools for some light research. Make an assumption about how they could use this system. Note that this is a user who has joined our system and wants an AI assistant that is personal for them, and wants to learn more about them.
        Name: {first_name} {last_name}
        Email: {email}
        Timezone: {timezone}
        City: {city}
        Country: {country}
        ## Note that this location information might be approximate. Further, note that it is a current location, and not necessarily where they are originally from or reside.
        Reached out on {source} with id {messaging_user_id} [phone number or telegram user name]
        """
         
    event = {
        "user_id": str(user_record["_id"]),
        'output_type': source,
        "source": source,
        "payload": {"text": text},
        "logging_context": {'user_id': str(user_record["_id"]), 'request_id': request_id_var, 'modality': source },
        "metadata": {'source':source,'forwarded':False, 'timestamp': timestamp}
        }
    if source == 'telegram':
        event['output_chat_id'] = messaging_user_id
    else:
        event['output_phone_number'] = messaging_user_id
    await event_queue.publish(event)
    ### set needs_first_interaction to false
    from src.services.user_service import user_service
    user_service.set_first_time_interaction_to_false(str(user_record["_id"]))
    return 