import pytz
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from src.config.settings import settings
from src.core.context import UserContext
from src.tools.tool_factory import AgentToolsFactory
from src.services.conversation_manager import ConversationManager
from src.utils.database import db_manager
from src.services.integration_service import integration_service
from pydantic import BaseModel, Field
from src.utils.logging import setup_logger
from src.core.praxos_client import PraxosClient
from langgraph.graph import MessagesState
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chat_models import init_chat_model
import uuid
from src.services.output_generator.generator import OutputGenerator
from bson import ObjectId
from src.utils.blob_utils import download_from_blob_storage_and_encode_to_base64
from src.utils.audio import convert_ogg_b64_to_wav_b64
from src.services.user_service import user_service

logger = setup_logger(__name__)

LANGUAGE_MAP = {
    'en': 'English',
    'es': 'Spanish',
    'pt': 'Portuguese',
    'fr': 'French',
    'it': 'Italian',
    'de': 'German',
    'ja': 'Japanese',
    'vn': 'Vietnamese',
}
import asyncio
async def _gather_bounded(coros: List[Any], limit: int = 8):
    sem = asyncio.Semaphore(limit)

    async def _run(coro):
        async with sem:
            return await coro

    # Order of results matches order of coros
    return await asyncio.gather(*(_run(c) for c in coros), return_exceptions=True)
# --- 1. Define the Structured Output and State ---
class FileLink(BaseModel):
    url: str = Field(description="URL to the file.")
    file_type: Optional[str] = Field(description="Type of the file, e.g., image, document, etc.", enum=["image", "document", "audio", "video","other_file"])
    file_name: Optional[str] = Field(description=" name of the file, if available. if not, come up with a descriptive name based on the content of the file.")
class AgentFinalResponse(BaseModel):
    """The final structured response from the agent."""
    response: str = Field(description="The final, user-facing response to be delivered.")
    execution_notes: Optional[str] = Field(description="Internal notes about the execution, summarizing tool calls or errors.")

    delivery_platform: str = Field(description="The channel for the response. Should be the same as the input source, unless otherwise specified.", enum=["email", "whatsapp", "websocket", "telegram",'imessage'])
    output_modality: Optional[str] = Field(description="The modality of the output, e.g., text, image, file, etc. unless otherwise specified by user needs, this should be text", enum=["text", "voice", 'audio', "image", "video",'file'])
    generation_instructions: Optional[str] = Field(description="Instructions for generating audio, video, or image if applicable.")
    file_links: Optional[List[FileLink]] = Field(description="Links to any files generated or used in the response.")
    class Config:
        extra = "forbid"
        arbitrary_types_allowed = True

class AgentState(MessagesState):
    user_context: UserContext
    metadata: Optional[Dict[str, Any]]
    final_response: Optional[AgentFinalResponse] # To hold the structured output

# --- 2. Define the Agent Runner Class ---
class LangGraphAgentRunner:
    def __init__(self,trace_id: str, has_media: bool = False,override_user_id: Optional[str] = None):
        
        self.tools_factory = AgentToolsFactory(config=settings, db_manager=db_manager)
        self.conversation_manager = ConversationManager(db_manager.db, integration_service)
        ### this is here to force langchain lazy importer to pre import before portkey corrupts.
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id=trace_id)
        ### note that this is not OpenAI, this is azure. we will use portkey to access OAI Azure.
        self.llm = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        ### temporary, investigating refusals.
        self.media_llm =ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            )
        
        self.llm = self.media_llm
        
        # else:
        #     logger.info("Using GPT-5 Mini for admin user logging")
        if has_media:
            self.llm = self.media_llm   
        self.structured_llm = self.llm.with_structured_output(AgentFinalResponse)



    async def _get_long_term_memory(self, praxos_client: PraxosClient, input_text: str) -> List[str]:
        """Fetches long-term memory for the user from Praxos."""
        praxos_history = await praxos_client.search_memory(input_text,10)
        long_term_memory_context = ''
        for i,itm in enumerate(praxos_history['sentences']):
            long_term_memory_context += f"Context Info{i+1}: {itm}\n"
        if long_term_memory_context:
            long_term_memory_context = "\n\nThe following relevant information is known about this user from their long-term memory:\n" + long_term_memory_context
        return long_term_memory_context

    def _create_system_prompt(self, user_context: UserContext, source: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Replicates the system prompt construction from the original AgentRunner."""
        user_record = user_context.user_record
        user_record_for_context = "\n\nThe following information is known about this user of the assistant:"
        if user_record:
            if user_record.get("first_name"): user_record_for_context += f"\nFirst Name: {user_record.get('first_name')}"
            if user_record.get("last_name"): user_record_for_context += f"\nLast Name: {user_record.get('last_name')}"
            if user_record.get("email"): user_record_for_context += f"\nEmail: {user_record.get('email')}"
            if user_record.get("phone_number"): user_record_for_context += f"\nPhone Number: {user_record.get('phone_number')}"
        else:
            user_record_for_context = ""


        base_prompt = (
            "You are a helpful AI assistant. Use the available tools to complete the user's request. "
            "If it's not a request, but a general conversation, just respond to the user's message. "
            "Do not mention tools if the user's final, most current request, does not require them. "
            "If the user's request requires you to do an action in the future or in a recurring manner, "
            "use the available tools to schedule the task."
            "do not confirm the scheduling with the user, just do it, unless the user specifically asks you to confirm it with them."
            "use best judgement, instead of asking the user to confirm. confirmation or clarification should only be done if absolutely necessary."
            "if the user requests generation of audio, video or image, you should simply set the appropriate flag on output_modality, and generation_instructions, and not use any tool to generate them. this will be handled after your response is processed, with systems that are capable of generating them. your response in the final_response field should always simply be to acknowledge the request and say you would be happy to help. you will then describe the media in detail in the appropriate field, using the generation_instructions field, as well as setting the output modality field to the appropriate value for what the user actually wants. do not actually tell the user you won't generate it yourself, that's overly complex and will confuse them. do not ask them for more info in your response either, as the generation will happen regardless."
            "If the user requests a trigger setup, attempt to use the other tools at your disposal to enrich the information about the trigger's rules. however, only add info that you are certain about to the conditions of the trigger."
        )



        praxos_prompt = """
        this assistant service has been developed by Praxos AI. the user can register and manage their account at https://www.mypraxos.com.
        the user can see the web application at https://app.mypraxos.com and can see their integrations at https://app.mypraxos.com/integrations. if the user is missing an integration they want, direct them there.
        """
        preferences = user_service.get_user_preferences(user_context.user_id) 
        preferences = preferences if preferences else {}
        timezone_name = preferences.get('timezone', 'America/New_York')
        annotations = preferences.get('annotations', [])

        if annotations:
            logger.info(f"User has provided additional context and preferences: {annotations}")
            praxos_prompt += f"\n\nThe user has provided the following additional context and preferences for you to consider in your responses: {'\n'.join(annotations)}\n"
        nyc_tz = pytz.timezone(timezone_name)
        current_time_nyc = datetime.now(nyc_tz).isoformat()
        time_prompt = f"\nThe current time in the user's timezone is {current_time_nyc}. You should always assume the user is in the '{timezone_name}' timezone unless specified otherwise."
        logger.info(time_prompt)
        tool_output_prompt = (
            "\nThe output format of most tools will be an object containing information, including the status of the tool execution. "
            "If the execution is successful, the status will be 'success'. In cases where the tool execution is not successful, "
            "there might be a property called 'user_message' which contains an error message. This message must be relayed to the user EXACTLY as it is. "
            "Do not add any other text to the user's message in these cases. If the preferd language has been set up to something different than English, you must translate the 'user_message' message to prefered language in the unsuccessful cases."
        )


        side_effect_explanation_prompt = """ note that there is a difference between the final output delivery modality, and using tools to send a response. the tool usage for communication is to be used when the act of sending a communication is a side effect, and not the final output or goal. """
        
        
        if source in ["scheduled", "recurring",'triggered']:
            task_prompt = "\nIMPORTANT NOTE: this is the command part of a previously scheduled task. You should now complete the task. Do not ask the user when to perform it, this task was scheduled to be performed for this exact time.  Note that at this time, you should not use the scheduling tool again, as this is the scheduled execution. Instead, perform the task now. If the task is phrased as a reminder or a request for scheduling, assume that you are now supposed to perform the reminding act itself, NOT scheduling it for the future. The task may even mention a need for a reminder, but that is because the user previously asked for it. You must now do the reminding act itself, and not schedule it again. "
            if source == "triggered":
                task_prompt += "This task was triggered by an external event, and must be performed now. Pay close attention to the user's original instructions when the task was created. Pay close attention to any delivery instructions. if the user asked for it on whatsapp/imessage/telegram/email, you must comply. "
            elif metadata and metadata.get("output_type"):
                task_prompt += f" The output modality for the final response of this scheduled task was previously specified as '{metadata.get('output_type')}'. the original source was '{metadata.get('original_source')}'."
            else:
                task_prompt += " The output modality for the final response of this scheduled task was not specified, so you should choose the most appropriate one based on the user's preferences and context. this cannot be websocket in this case."
        
        else:
            task_prompt = f"\n\nThis message was received on the '{source}' channel. \n\n"
        logger.info(f"Task prompt: {task_prompt}")

        
        assistance_name = preferences.get('assistant_name', 'Praxos')
        preferred_language = LANGUAGE_MAP[preferences.get('language_responses', 'en')]
        personilization_prompt = (f"\nYou are personilized to the user. User wants to call you '{assistance_name}' to get assistance. You should respond to the user's request as if you are the assistant named '{assistance_name}'."
         f"The prefered language to use is '{preferred_language}'. You must always respond in the prefered language, unless the user specifically asks you to respond in a different language. If the user uses a different language than the prefered one, you can respond in the language the user used. if the user asks you to use a different language, you must comply."
         "Pay attention to pronouns and formality levels in the prefered language, pronoun rules, and other similar nuances. mirror the user's language style and formality level in your responses."
        )
        total_system_capabilities_prompt = """The system is capable of integrating with various third party services. these are, Notion, Dropbox, Gmail, Google Drive, Google Calendar, Outlook and Outlook Calendar, One Drive, WhatsApp, Telegram, iMessage. The given user, however, may have not integrated any, or only integrated a subset. the user may ask for tasks that require an integration you do not have. in such cases, use the integration tool to help them integrate the tool.
            
            If the user explicitly asks for what you can do, tell them the following capabilities you have. 
            Email management: I can find, summarize, respond to, or draft emails. Just ask me to "find emails about X" or "draft a reply to Y"

            Answer questions from your data: Ask me things like "when's my flight?" or "what's the tracking number for my package?"

            General knowledge: Ask me anything from "how tall is the Eiffel Tower?" to "what's the weather in Marion, Illinois?"

            Set up automations: I can automatically forward emails, notify you about important messages, or handle repetitive tasks

            Calendar management: Create, update, or delete events and get reminders

            Research: I can look things up for you online, from restaurant recommendations to market research

            Draft emails in your voice: Need to write something? I'll draft it for you to review before sending

            I can also chain any of the above together to accomplish more complex tasks.

        """
        return base_prompt + praxos_prompt + time_prompt + tool_output_prompt + user_record_for_context + side_effect_explanation_prompt + task_prompt + personilization_prompt + total_system_capabilities_prompt

    async def _build_payload_entry(self, file: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a single payload dict for a file entry."""
        ftype = file.get("type")
        mime_type = file.get("mime_type")
        if not mime_type:
            mime_type = file.get("mimetype")

        blob_path = file.get("blob_path")
        if not blob_path or not ftype:
            return None

        data_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)

        if ftype in {"voice", "audio", "video"}:
            return {"type": "media", "data": data_b64, "mime_type": mime_type}
        if ftype in {"image", "photo"}:
            return {"type": "image_url", "image_url": f"data:{mime_type};base64,{data_b64}"}
        if ftype in {"document", "file"}:
            return {
                "type": "file",
                "source_type": "base64",
                "mime_type": mime_type,
                "data": data_b64,
            }
        return None


    async def _build_payload_entry_from_inserted_id(self, inserted_id: str) -> Optional[Dict[str, Any]]:
        file = await db_manager.get_document_by_id(inserted_id)
        return await self._build_payload_entry(file) if file else None


    # ---------------------------------------------------
    # Generate user messages from list structure (grouped messages)
    # ---------------------------------------------------
    async def _generate_user_messages(
        self,
        input_messages: List[Dict],
        messages: List[BaseMessage],
        conversation_id: str = None,
        base_message_prefix: str = "",
        user_context: UserContext = None,
    ) -> List[BaseMessage]:
        """
        Process grouped messages (list format) and add them to conversation history.
        Each message gets proper metadata and forwarding context.
        """
        logger.info(f"Processing {len(input_messages)} grouped user messages")
        
        for i, message_entry in enumerate(input_messages):
            # Extract content and metadata
            text_content = message_entry.get("text", "")
            files_content = message_entry.get("files", [])
            metadata = message_entry.get("metadata", {})
            
            # Build message prefix with forwarding context
            message_prefix = base_message_prefix
            
            if metadata.get("forwarded"):
                message_prefix += " [FORWARDED MESSAGE] "
                if forward_origin := metadata.get("forward_origin"):
                    if forward_origin.get("original_sender_identifier"):
                        message_prefix += f"originally from {forward_origin['original_sender_identifier']} "
                    if forward_origin.get("forward_date"):
                        message_prefix += f"(sent: {forward_origin['forward_date']}) "
            
            # Process this message as a complete unit (text + files together)
            if text_content and files_content:
                # Message with both text and files - process together
                full_message = message_prefix + text_content
                
                # Add text to conversation DB first
                await self.conversation_manager.add_user_message(
                    user_context.user_id,
                    conversation_id, 
                    full_message, 
                    metadata
                )
                
                # Add text to LLM message history
                messages.append(HumanMessage(content=full_message))
                
                # Then immediately add the files for this same message
                messages = await self._generate_file_messages(
                    files_content,
                    messages,
                    conversation_id=conversation_id,
                    message_prefix=message_prefix,
                    max_concurrency=8
                )
                logger.info(f"Added combined text+files message {i+1}/{len(input_messages)} to conversation")
                
            elif text_content:
                # Text-only message
                full_message = message_prefix + text_content
                
                await self.conversation_manager.add_user_message(
                    user_context.user_id,
                    conversation_id, 
                    full_message, 
                    metadata
                )
                
                messages.append(HumanMessage(content=full_message))
                logger.info(f"Added text-only message {i+1}/{len(input_messages)} to conversation")
                
            elif files_content:
                # Files-only message
                messages = await self._generate_file_messages(
                    files_content,
                    messages,
                    conversation_id=conversation_id,
                    message_prefix=message_prefix,
                    max_concurrency=8
                )
                logger.info(f"Added files-only message {i+1}/{len(input_messages)} to conversation")
            
            # If neither text nor files, skip this message entry
            else:
                logger.warning(f"Message {i+1} has neither text nor files, skipping")
        
        return messages

    async def _generate_user_messages_parallel(
        self,
        input_messages: List[Dict],
        messages: List[BaseMessage],
        conversation_id: str = None,
        base_message_prefix: str = "",
        user_context: UserContext = None,
        max_concurrency: int = 8,
    ) -> Tuple[List[BaseMessage], bool]:
        """Parallel version of _generate_user_messages with better performance."""
        logger.info(f"Processing {len(input_messages)} grouped messages with parallel file handling")
        has_media = False
        # Phase 1: Build structure and collect file tasks
        message_structure = []
        all_file_tasks = []
        
        for i, message_entry in enumerate(input_messages):
            text_content = message_entry.get("text", "")
            files_content = message_entry.get("files", [])
            metadata = message_entry.get("metadata", {})
            
            # Build prefix with forwarding context
            message_prefix = base_message_prefix
            if metadata.get("forwarded"):
                message_prefix += " [FORWARDED MESSAGE] "
                if forward_origin := metadata.get("forward_origin"):
                    if forward_origin.get("original_sender_identifier"):
                        message_prefix += f"originally from {forward_origin['original_sender_identifier']} "
                    if forward_origin.get("forward_date"):
                        message_prefix += f"(sent: {forward_origin['forward_date']}) "
            
            structure_entry = {
                "message_index": i,
                "text_content": text_content,
                "message_prefix": message_prefix,
                "metadata": metadata,
                "files_info": files_content,
                "file_task_start_index": len(all_file_tasks),
                "file_count": len(files_content)
            }
            
            # Queue file tasks
            for file_info in files_content:
                all_file_tasks.append(self._build_payload_entry(file_info))
            
            message_structure.append(structure_entry)
        
        # Phase 2: Execute all file tasks in parallel
        file_payloads = []
        if all_file_tasks:
            logger.info(f"Executing {len(all_file_tasks)} file tasks in parallel")
            file_payloads = await _gather_bounded(all_file_tasks, limit=max_concurrency)
        
        # Phase 3: Reconstruct in order
        for structure_entry in message_structure:
            i = structure_entry["message_index"]
            text_content = structure_entry["text_content"]
            message_prefix = structure_entry["message_prefix"]
            metadata = structure_entry["metadata"]
            files_info = structure_entry["files_info"]
            file_start = structure_entry["file_task_start_index"]
            file_count = structure_entry["file_count"]
            
            # Add text message
            if text_content:
                full_message = message_prefix + text_content
                await self.conversation_manager.add_user_message(user_context.user_id, conversation_id, full_message, metadata)
                messages.append(HumanMessage(content=full_message))
                logger.info(f"Added text for message {i+1}/{len(input_messages)}")
            
            # Add file messages
            if file_count > 0:
                has_media = True
                message_payloads = file_payloads[file_start:file_start + file_count]
                for file_info, payload in zip(files_info, message_payloads):
                    if isinstance(payload, Exception) or payload is None:
                        continue
                    
                    # Add to conversation DB
                    ftype = file_info.get("type")
                    caption = file_info.get("caption", "")
                    inserted_id = file_info.get("inserted_id")
                    
                    if inserted_id and conversation_id:
                        await self.conversation_manager.add_user_media_message(
                            user_context.user_id,
                            conversation_id, message_prefix, inserted_id,
                            message_type=ftype,
                            metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                        )
                        if caption:
                            await self.conversation_manager.add_user_message(
                                user_context.user_id,
                                conversation_id,
                                message_prefix + " as caption for media in the previous message: " + caption,
                                metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                            )
                    
                    # Add to LLM message history
                    content = ([{"type": "text", "text": caption}] if caption else []) + [payload]
                    messages.append(HumanMessage(content=content))
                
                logger.info(f"Added {file_count} files for message {i+1}/{len(input_messages)}")
        
        return messages, has_media

    # ---------------------------------------------------
    # Generate file messages (parallel, order preserved)
    # ---------------------------------------------------
    async def _generate_file_messages(
        self,
        input_files: List[Dict],
        messages: List[BaseMessage],
        model: str = None,           # kept for compatibility; unused
        conversation_id: str = None,
        message_prefix: str = "",
        max_concurrency: int = 8,
        user_id: str = None,
    ) -> List[BaseMessage]:
        logger.info(f"Generating file messages; current messages length: {len(messages)}")

        # Build captions list and payload tasks in the same order as input_files
        captions: List[Optional[str]] = [f.get("caption") for f in input_files]
        file_types: List[Optional[str]] = [f.get("type") for f in input_files]
        inserted_ids: List[Optional[str]] = [f.get("inserted_id") for f in input_files]

        payload_tasks = [self._build_payload_entry(f) for f in input_files]
        payloads = await _gather_bounded(payload_tasks, limit=max_concurrency)

        # Assemble messages & persist conversation log in order
        for idx, (ftype, cap, payload, ins_id) in enumerate(zip(file_types, captions, payloads, inserted_ids)):
            if isinstance(payload, Exception) or payload is None:
                logger.warning(f"Skipping file at index {idx} due to payload error/None")
                continue

            # Persist to conversation log first, in-order
            if ins_id and conversation_id:
                await self.conversation_manager.add_user_media_message(
                    user_id,
                    conversation_id,
                    message_prefix,
                    ins_id,
                    message_type=ftype,
                    metadata={"inserted_id": ins_id, "timestamp": datetime.utcnow().isoformat()},
                )
                if cap:
                    await self.conversation_manager.add_user_message(
                        user_id,
                        conversation_id,
                        message_prefix + " as caption for media in the previous message: " + cap,
                        metadata={"inserted_id": ins_id, "timestamp": datetime.utcnow().isoformat()},
                    )

            # Build LLM-facing message (caption first, then payload), in-order
            content = ([{"type": "text", "text": cap}] if cap else []) + [payload]
            messages.append(HumanMessage(content=content))
            logger.info(f"Added '{ftype}' message; messages length now {len(messages)}")

        return messages

    async def process_media_output(self,final_response:AgentFinalResponse, user_context: UserContext, source: str, conversation_id: str) -> AgentFinalResponse:
        try:
            output_blobs = []
            if final_response.output_modality and final_response.output_modality != "text":
                logger.info(f"Non-text output modality '{final_response.output_modality}' detected; invoking output generator")
                generation_instructions = final_response.generation_instructions or f"Generate a {final_response.output_modality} based on the following text: {final_response.response}"
                output_generator = OutputGenerator()
                prefix = f"{user_context.user_id}/{source}/{conversation_id}/"
                if final_response.output_modality == "image":
                    try:
                        image_blob_url, image_file_name = await output_generator.generate_image(generation_instructions, prefix)
                        if image_blob_url:
                            output_blobs.append({"url": image_blob_url, "file_type": "image", "file_name": image_file_name})
                            await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we generated an image for the user. this image was described as follows: " + generation_instructions)
                    except Exception as e:
                        logger.info(f"Error generating image output: {e}", exc_info=True)
                        await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate an image for the user. there was an error: " + str(e) + " the image was described as follows: " + generation_instructions)
                if final_response.output_modality in {"audio", "voice"}:
                    is_imessage = final_response.delivery_platform == "imessage"
                    logger.info(f"Generating audio with is_imessage={is_imessage}")
                    try:
                        audio_blob_url, audio_file_name = await output_generator.generate_speech(generation_instructions, prefix, is_imessage)
                        if audio_blob_url:
                            output_blobs.append({"url": audio_blob_url, "file_type": "audio", "file_name": audio_file_name})
                            await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we generated audio for the user. this audio was described as follows: " + generation_instructions)
                    except Exception as e:
                        logger.info(f"Error generating audio output: {e}", exc_info=True)
                        await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate audio for the user. there was an error: " + str(e) + " the audio was described as follows: " + generation_instructions)

                if final_response.output_modality == "video":
                    try:
                        video_blob_url, video_file_name = await output_generator.generate_video(generation_instructions, prefix)
                        if video_blob_url:
                            output_blobs.append({"url": video_blob_url, "file_type": "video", "file_name": video_file_name})
                            await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we generated a video for the user. this video was described as follows: " + generation_instructions)
                    except Exception as e:
                        logger.info(f"Error generating video output: {e}", exc_info=True)
                        await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate a video for the user. there was an error: " + str(e) + " the video was described as follows: " + generation_instructions)
        except Exception as e:
            logger.error(f"Error during output generation: {e}", exc_info=True)
            # Append error message to final response
            final_response.response += "\n\n(Note: There was an error generating the requested media output. Please try again later.)"
            # Downgrade to text-only response
            final_response.output_modality = "text"
            final_response.generation_instructions = None
        if not final_response.file_links:
            final_response.file_links = []
        final_response.file_links.extend(output_blobs)
        return final_response
    async def _get_conversation_history(
        self,
        conversation_id: str,
        max_concurrency: int = 8,
    ) -> List[BaseMessage]:
        """Fetches and formats the conversation history with concurrent media fetches."""
        context = await self.conversation_manager.get_conversation_context(conversation_id)
        raw_msgs: List[Dict[str, Any]] = context.get("messages", [])
        n = len(raw_msgs)
        has_media = False
        history_slots: List[Optional[BaseMessage]] = [None] * n
        fetch_tasks: List[Any] = []
        task_meta: List[Tuple[int, str]] = []  # (index, role)
        cache: Dict[str, Any] = {}  # inserted_id -> task to dedupe identical media

        media_types = {"voice", "audio", "video", "image", "document", "file"}

        for i, msg in enumerate(raw_msgs):
            msg_type = msg.get("message_type")
            role = msg.get("role")

            if msg_type == "text":
                content = msg.get("content", "")
                history_slots[i] = HumanMessage(content=content) if role == "user" else AIMessage(content=content)
                continue

            if msg_type in media_types:
                has_media = True
                inserted_id = (msg.get("metadata") or {}).get("inserted_id")
                if not inserted_id:
                    logger.warning(f"Media message missing inserted_id at index {i}")
                    continue

                # De-duplicate downloads for the same inserted_id
                task = cache.get(inserted_id)
                if task is None:
                    task = self._build_payload_entry_from_inserted_id(inserted_id)
                    cache[inserted_id] = task

                fetch_tasks.append(task)
                task_meta.append((i, role))
                continue

            logger.warning(f"Unknown message_type '{msg_type}' at index {i}")

        # Run all media fetches concurrently, keeping order by input task list
        results = await _gather_bounded(fetch_tasks, limit=max_concurrency)

        # Place media messages back into the original positions
        for (i, role), payload in zip(task_meta, results):
            if isinstance(payload, Exception) or payload is None:
                logger.warning(f"Failed to build payload for message at index {i}")
                continue
            msg_obj = HumanMessage(content=[payload]) if role == "user" else AIMessage(content=[payload])
            history_slots[i] = msg_obj

        # Return in original order, skipping any None (e.g., malformed entries)
        return [m for m in history_slots if m is not None],has_media
    async def run(self, user_context: UserContext, input: Dict, source: str, metadata: Optional[Dict] = None) -> AgentFinalResponse:
        execution_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        execution_record = {
            "execution_id": execution_id,
            "user_id": ObjectId(user_context.user_id),
            "trigger_type": source,
            "trigger_data": {"input": input, "metadata": metadata},
            "status": "running",
            "started_at": start_time,
        }

        await db_manager.db["execution_history"].insert_one(execution_record)      
        try:
            
            """Main entry point for the LangGraph agent runner."""
            ### here's what I'll do. first of all, some methods do need a flattened text input. so even in the list case, we'll generate it.
            if isinstance(input, list):
                ### this is not really the best way to do it, but for now, we'll just concatenate all text parts.
                input_text = " ".join([item.get("text", "") for item in input if item.get("text")])
                input_files = [item.get("files", []) for item in input if item.get("files")]
                input_files = [file for sublist in input_files for file in sublist]  # flatten list of lists
                all_forwarded = all([item.get("metadata", {}).get("forwarded", False) for item in input if item.get("metadata")])
            else:
                input_text = input.get("text")
                input_files = input.get("files")
                all_forwarded = input.get("metadata", {}).get("forwarded", False)
            if input_text:
                logger.info(f"Running LangGraph agent runner for user {user_context.user_id} with input {input_text} and source {source}")

            # --- Data preparation ---
            conversation_id = metadata.get("conversation_id") or await self.conversation_manager.get_or_create_conversation(user_context.user_id, source, input)
            metadata['conversation_id'] = conversation_id
            # Get conversation history first (before adding new messages)
            history, has_media = await self._get_conversation_history(conversation_id)

            


            ### TODO: use user timezone from preferences object.        
            user_preferences = user_service.get_user_preferences(user_context.user_id)    
            timezone_name = user_preferences.get('timezone', 'America/New_York') if user_preferences else 'America/New_York'
            user_tz = pytz.timezone(timezone_name)
            current_time_user = datetime.now(user_tz).isoformat()
            # Process input based on type
            if isinstance(input, list):
                # Grouped messages - use the parallel method
                base_message_prefix = f'message sent on date {current_time_user} by {user_context.user_record.get("first_name", "")} {user_context.user_record.get("last_name", "")}: '
                history, has_media = await self._generate_user_messages_parallel(
                    input, 
                    history, 
                    conversation_id=conversation_id,
                    base_message_prefix=base_message_prefix,
                    user_context=user_context
                )
            elif isinstance(input, dict):
                # Single message - existing logic
                message_prefix = f'message sent on date {current_time_user} by {user_context.user_record.get("first_name", "")} {user_context.user_record.get("last_name", "")}: '
                if input_text:
                    await self.conversation_manager.add_user_message(user_context.user_id, conversation_id, message_prefix + input_text, metadata)
                    history.append(HumanMessage(content=message_prefix + input_text))
                
                # Handle files for single message
                if input_files:
                    history = await self._generate_file_messages(
                        input_files, 
                        history, 
                        conversation_id=conversation_id,
                        message_prefix=message_prefix
                    )
            else:
                return AgentFinalResponse(response="Invalid input format.", delivery_platform=source, execution_notes="Input must be a dict or list of dicts.", output_modality="text", file_links=[], generation_instructions=None)            


            if has_media:
                logger.info(f"Conversation {conversation_id} has media; switching to media-capable LLM")
                self.llm = self.media_llm

            
            if all_forwarded:
                logger.info("All input messages are forwarded; verify with the user before taking actions.")
                return AgentFinalResponse(response="It looks like all the messages you sent were forwarded messages. Should I interpret this as a direct request to me? Awaiting confirmation.", delivery_platform=source, execution_notes="All input messages were marked as forwarded.", output_modality="text", file_links=[], generation_instructions=None)

            tools = await self.tools_factory.create_tools(user_context, metadata,timezone_name)

            tool_executor = ToolNode(tools)
            llm_with_tools = self.llm.bind_tools(tools)

            system_prompt = self._create_system_prompt(user_context, source, metadata)
            ### this creates unnecessary overhead and latency, so we'll disable it for now.
            # from src.config.settings import settings
            # if settings.OPERATING_MODE == "local":
            #     praxos_api_key = settings.PRAXOS_API_KEY
            # else:
            #     praxos_api_key = user_context.user_record.get("praxos_api_key")

            # try:
            #     if input_text and len(input_text) > 5 and praxos_api_key:
            #         praxos_client = PraxosClient(f"env_for_{user_context.user_record.get('email')}", api_key=praxos_api_key)
            #         ### @TODO: this needs a more intelligent approach. for example, if the input is just "hi" or "hello", we don't need to fetch long term memory.
            #         # long_term_memory_context = await self._get_long_term_memory(praxos_client, input_text)
            #         # if long_term_memory_context:
            #         #     system_prompt += long_term_memory_context
            # except Exception as e:
            #     logger.error(f"Error fetching long-term memory: {e}", exc_info=True)





            # --- Graph Definition ---
            async def call_model(state: AgentState):
                messages = state['messages']
                response = await llm_with_tools.ainvoke([("system", system_prompt)] + messages)
                return {"messages": state['messages'] + [response]}

            def should_continue(state: AgentState):
                last_message = state['messages'][-1]
                if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
                    return "end"
                else:
                    return "continue"

            async def generate_final_response(state: AgentState):
                final_message = state['messages'][-1].content
                source_to_use = source
                logger.info(f"Final agent message before formatting: {final_message}")
                logger.info(f"Source channel: {source}, metadata: {state['metadata']}")
                if source in ['scheduled','recurring'] and state.get('metadata') and state['metadata'].get('output_type'):
                    source_to_use = state['metadata']['output_type']
                prompt = (
                    f"Given the final response from an agent: '{final_message}', "
                    f"and knowing the initial request came from the '{source_to_use}' channel, "
                    "format this into the required JSON structure. The delivery_platform must match the source channel, unless the user indicates or implies otherwise, or the command requires a different channel. Note that a scheduled/recurring/triggered command cannot have websocket as the delivery platform. If the user has specifically asked for a different delivery platform, you must comply. for example, if the user has sent an email, but requests a response on imessage, comply. Explain the choice of delivery platform in the execution_notes field, acknowledging if the user requested a particular platform or not. "
                    f"the user's original message in this case was {input_text}. pay attention to whether it contains a particular request for delivery platform. "
                    "If the response requires generating audio, video, or image, set the output_modality and generation_instructions fields accordingly.  the response should simply acknowledge the request to generate the media, and not attempt to generate it yourself. this is not a task for you. simply trust in the systems that will handle it after you. "
                )
                response = await self.structured_llm.ainvoke(prompt)
                return {"final_response": response}

            workflow = StateGraph(AgentState)
            workflow.add_node("agent", call_model)
            workflow.add_node("action", tool_executor)
            workflow.add_node("finalize", generate_final_response)
            
            workflow.set_entry_point("agent")
            
            workflow.add_conditional_edges(
                "agent",
                should_continue,
                {"continue": "action", "end": "finalize"}
            )
            workflow.add_edge('action', 'agent')
            workflow.add_edge('finalize', END)
            
            app = workflow.compile()

            initial_state: AgentState = {
                "messages": history,
                "user_context": user_context,
                "metadata": metadata,
                "final_response": None
            }
            # --- END Graph Definition ---
            final_state = await app.ainvoke(initial_state,{"recursion_limit": 100})
            
            final_response = final_state['final_response']
            output_blobs = []
            await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, final_response.response)
            logger.info(f"Final response generated for execution {execution_id}: {final_response.model_dump_json(indent=2)}")
            final_response = await self.process_media_output(final_response, user_context, source, conversation_id)
            execution_record["status"] = "completed"
            return final_response

        except Exception as e:
            logger.error(f"Error during agent run {execution_id}: {e}", exc_info=True)
            execution_record["status"] = "failed"
            execution_record["error_message"] = str(e)
            return AgentFinalResponse(response="I'm sorry, I'm having trouble processing your request. Please try again later.", delivery_platform=source, execution_notes=str(e), output_modality="text", file_links=[], generation_instructions=None)

        finally:
            execution_record["completed_at"] = datetime.utcnow()
            execution_record["duration_seconds"] = (execution_record["completed_at"] - start_time).total_seconds()
            await db_manager.db["execution_history"].update_one(
                {"execution_id": execution_id},
                {"$set": execution_record}
            )