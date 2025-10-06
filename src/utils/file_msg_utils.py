

from ast import Dict

from typing import Any, List, Optional,Dict
from src.utils.blob_utils import download_from_blob_storage_and_encode_to_base64
async def build_payload_entry(file: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create a single payload dict for a file entry."""
    ftype = file.get("type")
    mime_type = file.get("mime_type")
    blob_path = file.get("blob_path")
    if not blob_path or not ftype:
        return None

    data_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)

    if ftype in {"voice", "audio", "video"}:
        return {"type": "media", "data": data_b64, "mime_type": mime_type}
    if ftype == "image":
        return {"type": "image_url", "image_url": f"data:{mime_type};base64,{data_b64}"}
    if ftype in {"document", "file"}:
        return {
            "type": "file",
            "source_type": "base64",
            "mime_type": mime_type,
            "data": data_b64,
        }
    return None


async def build_payload_entry_from_inserted_id(inserted_id: str) -> Optional[Dict[str, Any]]:
    from src.utils.database import db_manager
    file = await db_manager.get_document_by_id(inserted_id)
    return await build_payload_entry(file) if file else None


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
                    if isinstance(item, dict) and item.get('type') != 'text':
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