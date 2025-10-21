

from ast import Dict

from typing import Any, List, Optional,Dict, Tuple
from datetime import datetime

from bson import ObjectId
from src.services.output_generator.generator import OutputGenerator
from src.utils.blob_utils import download_from_blob_storage_and_encode_to_base64
from src.utils.logging.base_logger import setup_logger
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage,ToolMessage
from src.core.context import UserContext
import asyncio
from src.core.media_bus import media_bus
from src.config.settings import settings
from src.core.models.agent_runner_models import AgentFinalResponse
logger = setup_logger(__name__)

#### media message payload handling


async def _gather_bounded(coros: List[Any], limit: int = 8):
    sem = asyncio.Semaphore(limit)

    async def _run(coro):
        async with sem:
            return await coro

    # Order of results matches order of coros
    return await asyncio.gather(*(_run(c) for c in coros), return_exceptions=True)


async def build_payload_entry(file: Dict[str, Any], add_to_media_bus=False, conversation_id: str = None) -> Optional[Dict[str, Any]]:
    """Create a single payload dict for a file entry."""
    payload = None
    url = None
    container_name = None
    ftype = file.get("type")
    mime_type = file.get("mime_type")
    ### need unification here, case in point.
    if not mime_type:
        mime_type = file.get("mimetype")

    blob_path = file.get("blob_path")
    if not blob_path or not ftype:
        return None

    if ftype in {"image", "photo"}:
        # Images are in CDN container - use public CDN URL instead of SAS URL
        from src.utils.blob_utils import get_cdn_url
        image_url = await get_cdn_url(blob_path, container_name="cdn-container")
        container_name = "cdn-container"
        url = image_url
        payload = {"type": "image_url", "image_url": image_url}

    # Download non-image files from default container
    else:
        
        data_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)

        if ftype in {"voice", "audio", "video"}:
            payload = {"type": "media", "data": data_b64, "mime_type": mime_type}
        if ftype in {"document", "file"}:
            payload = {
                "type": "file",
                "source_type": "base64",
                "mime_type": mime_type,
                "data": data_b64,
            }

    ### now, we add to media bus.
    if add_to_media_bus and conversation_id and payload:
        try:
            file_name = file.get("file_name")
            if not file_name or file_name == 'Original filename not accessible':
                file_name = blob_path.split('/')[-1]
            caption = file.get("caption", "")
            media_bus.add_media(
                conversation_id=conversation_id,
                url=url,
                file_name=file_name,
                file_type=ftype,
                description=f"User uploaded {ftype}" + (f": {caption}" if caption else ""),
                source="uploaded",
                blob_path=blob_path,
                mime_type=mime_type,  # Would need to extract from database
                metadata= file.get("metadata", {}),
                container_name = container_name if container_name else settings.AZURE_BLOB_CONTAINER_NAME,
            )
        except Exception as e:
            logger.error(f"Error adding media to media bus: {e}", exc_info=True)
    return payload

async def build_payload_entry_from_inserted_id(inserted_id: str,add_to_media_bus:bool=False, conversation_id: str = None) -> Tuple[Optional[Dict[str, Any]],Optional[Dict[str, Any]]]:
    from src.utils.database import db_manager
    file = await db_manager.get_document_by_id(inserted_id)
    if file:
        payload = await build_payload_entry(file, add_to_media_bus=add_to_media_bus, conversation_id=conversation_id)
        return payload,file
    return None,None



async def generate_user_messages_parallel(
    conversation_manager: Any,
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
        ### TODO: Unify file interfaces into a pydantic object. it's annoying that I have to check.
        for file_info in files_content:
            all_file_tasks.append(build_payload_entry(file_info, add_to_media_bus=True, conversation_id=conversation_id))
        
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
            text_content = text_content.strip().replace('/START_NEW','').replace('/start_new','').strip()
            if not text_content:
                text_content = "The user sent a message with no text. if there are also no files, indicate that the user sent an empty message."
            full_message = message_prefix + text_content
    
                
            await conversation_manager.add_user_message(user_context.user_id, conversation_id, full_message, metadata)
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
                    await conversation_manager.add_user_media_message(
                        user_context.user_id,
                        conversation_id, message_prefix, inserted_id,
                        message_type=ftype,
                        metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                    )
                    if ftype in {'image', 'photo'}:
                        logger.info(f"adding the link to the conversation as a text message too, for image/photo types")
                        caption += " [Image Attached], the link to the image is: " + payload.get("image_url", "")
                    if caption:
                        await conversation_manager.add_user_message(
                            user_context.user_id,
                            conversation_id,
                            message_prefix + " as caption for media in the previous message: " + caption,
                            metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                        )


                
                # Add to LLM message history
                logger.info(f"caption is {caption}")
                content = ([{"type": "text", "text": caption}] if caption else []) + [payload]
                messages.append(HumanMessage(content=content))
            
            logger.info(f"Added {file_count} files for message {i+1}/{len(input_messages)}")
    
    return messages, has_media

# ---------------------------------------------------
# Generate file messages (parallel, order preserved)
# ---------------------------------------------------
async def generate_file_messages(
    conversation_manager: Any,
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
    captions: List[Optional[str]] = [f.get("caption",'') for f in input_files]
    file_types: List[Optional[str]] = [f.get("type") for f in input_files]
    inserted_ids: List[Optional[str]] = [f.get("inserted_id") for f in input_files]
    payload_tasks = [build_payload_entry(f,add_to_media_bus=True, conversation_id=conversation_id) for f in input_files]
    payloads = await _gather_bounded(payload_tasks, limit=max_concurrency)

    # Assemble messages & persist conversation log in order
    for idx, (ftype, cap, payload, ins_id) in enumerate(zip(file_types, captions, payloads, inserted_ids)):
        if isinstance(payload, Exception) or payload is None:
            logger.warning(f"Skipping file at index {idx} due to payload error/None")
            continue

        # Persist to conversation log first, in-order
        if ins_id and conversation_id:
            await conversation_manager.add_user_media_message(
                user_id,
                conversation_id,
                message_prefix,
                ins_id,
                message_type=ftype,
                metadata={"inserted_id": ins_id, "timestamp": datetime.utcnow().isoformat()},
            )
            if ftype in {'image', 'photo'}:
                logger.info(f"adding the link to the conversation as a text message too, for image/photo types")
                cap += " [Image Attached], the link to the image is: " + payload.get("image_url", "")
            if cap:
                await conversation_manager.add_user_message(
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



async def process_media_output(conversation_manager:Any,final_response:AgentFinalResponse, user_context: UserContext, source: str, conversation_id: str) -> AgentFinalResponse:
    try:
        output_blobs = []
        if final_response.output_modality and final_response.output_modality != "text":
            logger.info(f"Non-text output modality '{final_response.output_modality}' detected; invoking output generator")
            generation_instructions = final_response.generation_instructions or f"Generate a {final_response.output_modality} based on the following text: {final_response.response}"
            output_generator = OutputGenerator()
            prefix = f"{user_context.user_id}/{source}/{conversation_id}/"
            if final_response.output_modality == "image":
                try:
                    image_blob_url, image_file_name, image_blob_name = await output_generator.generate_image(generation_instructions, prefix)

                    
                    if image_blob_url:
                        document_entry = {
                            "user_id": ObjectId(user_context.user_id),
                            "platform_file_id": image_file_name,
                            "platform_message_id": image_file_name,
                            "platform": source,
                            'type': 'image',
                            "blob_path": image_blob_name,
                            "mime_type": "image/png",
                            "caption": 'we generated an image for the user. this image was described as follows: ' + generation_instructions,
                            'file_name':    image_file_name,
                        }
                        from src.utils.database import db_manager
                        inserted_id = await db_manager.add_document(document_entry)
                        output_blobs.append({"url": image_blob_url, "file_type": "image", "file_name": image_file_name})
                        await conversation_manager.add_assistant_media_message(
                            user_context.user_id,
                            conversation_id, 'we generated an image for the user. this image was described as follows: " + generation_instructions', inserted_id,
                            message_type='image',
                            metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                        )
                except Exception as e:
                    logger.info(f"Error generating image output: {e}", exc_info=True)
                    await conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate an image for the user. there was an error: " + str(e) + " the image was described as follows: " + generation_instructions)
            if final_response.output_modality in {"audio", "voice"}:
                is_imessage = final_response.delivery_platform == "imessage"
                logger.info(f"Generating audio with is_imessage={is_imessage}")
                try:
                    audio_blob_url, audio_file_name, audio_blob_name = await output_generator.generate_speech(generation_instructions, prefix, is_imessage)
                    if audio_blob_url:
                        document_entry = {
                            "user_id": ObjectId(user_context.user_id),
                            "platform_file_id": audio_file_name,
                            "platform_message_id": audio_file_name,
                            "platform": source,
                            'type': 'audio',
                            "blob_path": audio_blob_name,
                            "mime_type": 'audio/x-caf' if is_imessage else 'audio/ogg',
                            "caption": 'we generated an audio for the user. this audio was described as follows: ' + generation_instructions,
                            'file_name':    audio_file_name,
                        }
                        from src.utils.database import db_manager
                        inserted_id = await db_manager.add_document(document_entry)
                        output_blobs.append({"url": audio_blob_url, "file_type": "audio", "file_name": audio_file_name})

                        await conversation_manager.add_assistant_media_message(
                            user_context.user_id,
                            conversation_id, "we generated audio for the user. this audio was described as follows: " + generation_instructions, inserted_id,
                            message_type='audio',
                            metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                        )
                except Exception as e:
                    logger.info(f"Error generating audio output: {e}", exc_info=True)
                    await conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate audio for the user. there was an error: " + str(e) + " the audio was described as follows: " + generation_instructions)

            if final_response.output_modality == "video":
                try:
                    video_blob_url, video_file_name, video_blob_name = await output_generator.generate_video(generation_instructions, prefix)
                    if video_blob_url:
                        document_entry = {
                            "user_id": ObjectId(user_context.user_id),
                            "platform_file_id": video_file_name,
                            "platform_message_id": video_file_name,
                            "platform": source,
                            'type': 'video',
                            "blob_path": video_blob_name,
                            "mime_type": 'video/mp4',
                            "caption": 'we generated a video for the user. this video was described as follows: ' + generation_instructions,
                            'file_name':    video_file_name,
                        }
                        from src.utils.database import db_manager
                        inserted_id = await db_manager.add_document(document_entry)
                        output_blobs.append({"url": video_blob_url, "file_type": "video", "file_name": video_file_name})
                        await conversation_manager.add_assistant_media_message(
                            user_context.user_id,
                            conversation_id, "we generated video for the user. this video was described as follows: " + generation_instructions, inserted_id,
                            message_type='video',
                            metadata={"inserted_id": inserted_id, "timestamp": datetime.utcnow().isoformat()}
                        )                
                except Exception as e:
                    logger.info(f"Error generating video output: {e}", exc_info=True)
                    await conversation_manager.add_assistant_message(user_context.user_id, conversation_id, "we failed to generate a video for the user. there was an error: " + str(e) + " the video was described as follows: " + generation_instructions)
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




async def get_conversation_history(
    conversation_manager: Any,
    conversation_id: str,
    max_concurrency: int = 8,
) -> List[BaseMessage]:
    """Fetches and formats the conversation history with concurrent media fetches."""
    context = await conversation_manager.get_conversation_context(conversation_id)
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
        metadata = msg.get("metadata", {})

        if msg_type == "text":
            content = msg.get("content", "")
            # Check if this is a tool result message
            if role == "assistant" and metadata.get("message_type") == "tool_result":
                tool_name = metadata.get("tool_name", "unknown_tool")
                # Reconstruct as ToolMessage
                history_slots[i] = ToolMessage(content=content, name=tool_name, tool_call_id=metadata.get("tool_call_id", ""))
            elif role == "user":
                history_slots[i] = HumanMessage(content=content)
            else:
                # Regular assistant message (may have tool_calls metadata)
                history_slots[i] = AIMessage(content=content)
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
                task = build_payload_entry_from_inserted_id(inserted_id, add_to_media_bus=True, conversation_id=conversation_id)
                cache[inserted_id] = task

            fetch_tasks.append(task)
            task_meta.append((i, role))
            continue

        logger.warning(f"Unknown message_type '{msg_type}' at index {i}")

    # Run all media fetches concurrently, keeping order by input task list
    results = await _gather_bounded(fetch_tasks, limit=max_concurrency)

    # Place media messages back into the original positions and populate media bus
    

    for (i, role), (payload,file_info) in zip(task_meta, results):
        if isinstance(payload, Exception) or payload is None:
            logger.warning(f"Failed to build payload for message at index {i}")
            continue

        msg_obj = HumanMessage(content=[payload]) if role == "user" else AIMessage(content=[payload])
        history_slots[i] = msg_obj

        # Add media to bus for agent reference
        try:
            raw_msg = raw_msgs[i]
            msg_type = raw_msg.get("message_type")
            inserted_id = (raw_msg.get("metadata") or {}).get("inserted_id")
            container_name = 'cdn-container' if msg_type in {'image', 'photo'} else settings.AZURE_BLOB_CONTAINER_NAME
            # Try to extract URL from payload
            media_url = None
            if payload.get("type") == "image_url":
                media_url = payload.get("image_url")

            # Get file info from database if we have inserted_id
            if inserted_id and media_url:
                # Add to media bus
                file_name = media_url.split('/')[-1] if '/' in media_url else "media_file"
                caption = raw_msg.get("content", "")  # Use message content as description
                
                # media_bus.add_media(
                #     conversation_id=conversation_id,
                #     url=media_url,
                #     file_name=file_name,
                #     file_type=msg_type,
                #     description=f"User uploaded {msg_type}" + (f": {caption}" if caption else ""),
                #     source="uploaded",
                #     blob_path=file_info.get('blob_path'),  # Would need to extract from database
                #     mime_type=file_info.get('mime_type'),  # Would need to extract from database
                #     metadata={"inserted_id": inserted_id, "from_history": True},
                #     container_name=container_name,
                # )
                logger.debug(f"Added historical media to bus: {msg_type} - {file_name}")
        except Exception as e:
            logger.warning(f"Could not add media to bus: {e}")

    logger.info(f"Fetched and reconstructed {len(fetch_tasks)} media messages")
    # Return in original order, skipping any None (e.g., malformed entries)
    return [m for m in history_slots if m is not None],has_media


##### placeholder for planner
def replace_media_with_placeholders(messages: List) -> List:
    """
    Replace media content in messages with text placeholders.
    Creates new message objects without mutating originals.

    Args:
        messages: List of LangChain message objects

    Returns:
        New list of messages with media replaced by placeholders
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    msgs_with_placeholders = []

    for msg in messages:
        # Skip system messages
        if isinstance(msg, SystemMessage):
            continue

        try:
            content = msg.content

            # Case 1: List content (multimodal messages)
            if isinstance(content, list):
                # Create new content list with placeholders for non-text items
                new_content = []
                for item in content:
                    if isinstance(item, dict) and item.get('type') not in ['media','text']:
                        # Replace media with placeholder
                        media_type = item.get('type', 'media').upper()
                        new_content.append({'type': 'text', 'text': f"[{media_type}]"})
                    else:
                        new_content.append(item)

                # Create new message with modified content (don't mutate original)
                if isinstance(msg, HumanMessage):
                    msgs_with_placeholders.append(HumanMessage(content=new_content))
                elif isinstance(msg, AIMessage):
                    msgs_with_placeholders.append(AIMessage(content=new_content))
                else:
                    msgs_with_placeholders.append(msg)

            # Case 2: String content (text-only messages) - pass through unchanged
            else:
                msgs_with_placeholders.append(msg)

        except Exception as e:
            from src.utils.logging import setup_logger
            logger = setup_logger(__name__)
            logger.error(f"Error processing message content: {e}", exc_info=True)
            # On error, include original message as fallback
            msgs_with_placeholders.append(msg)

    return msgs_with_placeholders



async def update_history( conversation_manager: Any, new_messages: List[BaseMessage], conversation_id: str, user_context: UserContext, final_state: Dict[str, Any]):
    inserted_ct = 0
    for msg in new_messages:
        try:
        # Skip the final AI message (will be added separately below)
            if msg == final_state['messages'][-1]:
                continue

            if isinstance(msg, AIMessage) and msg.tool_calls:
                # Persist AI messages with tool calls
                tool_names = ', '.join([tc.get('name', 'unknown') for tc in msg.tool_calls])
                content = msg.content if msg.content else f"[Calling tools: {tool_names}]"
                await conversation_manager.add_assistant_message(
                    user_context.user_id,
                    conversation_id,
                    content,
                    metadata={"tool_calls": [tc.get('name') for tc in msg.tool_calls]}
                )
            elif isinstance(msg, ToolMessage):
                # Persist tool results
                content = str(msg.content)
                await conversation_manager.add_assistant_message(
                    user_context.user_id,
                    conversation_id,
                    f"[Tool: {msg.name}] {content}",
                    metadata={
                        "tool_name": msg.name,
                        "message_type": "tool_result",
                        "tool_call_id": msg.tool_call_id if hasattr(msg, 'tool_call_id') else ""
                    }
                )
            inserted_ct += 1
        except Exception as e:
            logger.error(f"Error persisting intermediate message: {e}", exc_info=True)
    logger.info(f"Persisted {inserted_ct} new intermediate messages to conversation log")