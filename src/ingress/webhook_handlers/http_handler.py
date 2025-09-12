from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
import asyncio
from src.core.event_queue import event_queue
from src.services.conversation_manager import ConversationManager
from src.utils.database import conversation_db
from src.services.integration_service import integration_service
from src.ingest.ingestion_worker import InitialIngestionCoordinator
from bson import ObjectId
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
from src.utils.blob_utils import upload_bytes_to_blob_storage, upload_to_blob_storage
from fastapi import UploadFile,Request, Form, UploadFile, File
from typing import List, Optional
import json
class FileInfo(BaseModel):
    filename: str
    content_type: str
    size: int
    content: bytes
router = APIRouter()

class HttpIngressRequest(BaseModel):
    user_id: str
    input_text: str
    token: str = None
    files: Optional[List[FileInfo]] = []
    audio: Optional[FileInfo] = None

class IngestionRequest(BaseModel):
    user_id: str
    integration_type: str



@router.post("/http", status_code=status.HTTP_202_ACCEPTED)
async def handle_chat_request(
    request_body: Optional[HttpIngressRequest] = None,
    raw_request: Request = None,
    user_id: str = Form(None),
    input_text: str = Form(None),
    token: str = Form(None),
    files: List[UploadFile] = File(default=[]),
    audio: UploadFile = File(None)
):
    """
    Handles a conversational request from HTTP client with optional files/audio.
    Supports both JSON and multipart/form-data requests.

    For FormData requests:
    - user_id: form field
    - input_text: form field
    - token: form field
    - file_0, file_1, etc.: uploaded files
    - audio: uploaded audio file
    """
    
    # Determine request type and extract data
    # content_type = raw_request.headers.get("content-type", "")
    
    # if content_type.startswith("multipart/form-data"):
        # Handle FormData request
    if not all([user_id, token]):
        raise HTTPException(
            status_code=400, 
            detail="Missing required fields: user_id and token are required"
        )
        
    # Process uploaded files
    file_data = []
    for file in files:
        if file.filename:  
            content = await file.read()
            file_data.append(FileInfo(
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size=len(content),
                content=content
            ))
    
    # Process audio
    audio_data = None
    if audio and audio.filename:
        audio_content = await audio.read()
        audio_data = FileInfo(
            filename=audio.filename or "recording.wav",
            content_type=audio.content_type or "audio/wav",
            size=len(audio_content),
            content=audio_content
        )
    
    # Create request object
    request_obj = HttpIngressRequest(
        user_id=user_id,
        input_text=input_text,
        token=token,
        files=file_data,
        audio=audio_data
    )
    # else:

    #     if not request_body:
    #         raise HTTPException(
    #             status_code=400, 
    #             detail="Request body required for JSON requests"
    #         )
    #     request_obj = request_body
    
    # Initialize conversation (assuming you have these imports/services)
    conversation_manager = ConversationManager(conversation_db, integration_service)
    conversation_id = await conversation_manager.get_or_create_conversation(request_obj.user_id, "websocket")
    


    # Build payload with files and audio
    payload = {
        "text": request_obj.input_text
    }
    # "payload": {"files": [{'type': 'voice', 'blob_path': blob_name, 'mime_type': mime_type[0]}]},

    # Add files to payload if present
    if request_obj.files:
        payload["files"] = []
        for f in request_obj.files:
            logger.info(f"Processing uploaded file: {f.filename} of type {f.content_type} and size {f.size}")
            blob_name = f"{user_id}/telegram/{f.filename.replace(' ', '_')}"
            blob_name = await upload_bytes_to_blob_storage(f.content, blob_name)
            payload["files"].append(
                {
                    "type": f.content_type,
                    'mime_type': f.content_type,
                    "blob_path": blob_name
                } )
        payload["file_count"] = len(request_obj.files)
    
    # Add audio to payload if present  
    if request_obj.audio:
        if "files" not in payload:
            payload["files"] = []
        
        payload["files"].append({
            "type": "voice",
            'mime_type': request_obj.audio.content_type,
            "blob_path": await upload_bytes_to_blob_storage(request_obj.audio.content, f"{user_id}/telegram/{request_obj.audio.filename.replace(' ', '_')}")
        })


    event = {
        "user_id": request_obj.user_id,
        "source": "websocket",
        "payload": payload,
        "metadata": {
            "token": request_obj.token,
            "conversation_id": conversation_id,
            "source": "websocket",
            "capabilities": {
                "streaming": False
            },
            # Add file/audio metadata for processing hints
            "has_files": bool(request_obj.files),
            "has_audio": bool(request_obj.audio),
            "total_files": len(request_obj.files) if request_obj.files else 0
        }
    }

    # Publish event to queue (assuming you have event_queue available)
    await event_queue.publish(event)
    
    # For demo purposes, just log the event structure
    print(f"Would publish event: {json.dumps(event, indent=2, default=str)}")
    
    return {
        "status": "accepted", 
        "message": "Event queued for processing.", 
        "conversation_id": conversation_id,
        "files_received": len(request_obj.files) if request_obj.files else 0,
        "audio_received": bool(request_obj.audio)
    }

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(request: IngestionRequest):
    """
    Triggers the initial data ingestion by publishing an event to the queue.
    """
    event = {
        "user_id": request.user_id,
        "source": "ingestion", # A new source type for our worker to identify
        "payload": {
            "integration_type": request.integration_type
        },
        "metadata": {}
    }
    await event_queue.publish(event)
    return {"status": "success", "message": f"Initial ingestion for {request.integration_type} has been queued for user {request.user_id}."}
