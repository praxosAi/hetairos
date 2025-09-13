

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