from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
import asyncio
from src.core.event_queue import event_queue
from src.services.conversation_manager import ConversationManager
from src.utils.database import conversation_db
from src.services.integration_service import integration_service
from src.ingest.ingestion_worker import InitialIngestionCoordinator
from bson import ObjectId
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
logger = setup_logger(__name__)
from src.utils.blob_utils import upload_bytes_to_blob_storage, upload_to_blob_storage
from fastapi import UploadFile,Request, Form, File
from src.utils.database import db_manager
from src.config.settings import settings
from typing import List, Optional
import json
from src.utils.file_manager import file_manager
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


class FileUploadRequest(BaseModel):
    user_id: str
    files: Optional[List[FileInfo]] = []



class IngestionRequest(BaseModel):
    user_id: str
    integration_id: str




def content_type_to_praxos_name(content_type: str) -> str:
    """Maps common MIME types to Praxos document type names."""
    if content_type.startswith("image/"):
        return "image"
    elif content_type.startswith("video/"):
        return "video"
    elif content_type.startswith("audio/"):
        return "audio"
    elif content_type in ["application/pdf"]:
        return "document"
    elif content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        return "document"
    elif content_type in ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
        return "document"
    elif content_type in ["application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"]:
        return "document"
    elif content_type in ["text/plain"]:
        return "document"
    elif content_type in ["text/csv"]:
        return "document"
    elif content_type in ["application/zip", "application/x-7z-compressed", "application/x-rar-compressed"]:
        return "document"
    else:
        return "file"  # Generic file type

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
    user_id_var.set(str(user_id))
    modality_var.set("websocket")

    # Rate limiting for HTTP requests
    from src.utils.rate_limiter import rate_limiter
    is_allowed, remaining = rate_limiter.check_limit(user_id, "http_requests")
    if not is_allowed:
        logger.warning(f"Rate limit exceeded for user {user_id} on HTTP requests")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )

    # Increment request count
    rate_limiter.increment_usage(user_id, "http_requests", 1)

    # Check number of files
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files. Maximum {settings.MAX_FILES_PER_REQUEST} allowed."
        )

    # Process uploaded files with size limits
    file_data = []
    total_size = 0

    for file in files:
        if not file.filename:
            continue

        try:
            # Read file content with size validation
            content = await file.read()

            # Check individual file size
            if len(content) > settings.MAX_FILE_SIZE_HTTP:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"File '{file.filename}' exceeds maximum size of "
                        f"{settings.MAX_FILE_SIZE_HTTP // (1024*1024)}MB"
                    )
                )

            # Check total upload size
            total_size += len(content)
            if total_size > settings.MAX_TOTAL_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Total upload size exceeds limit of "
                        f"{settings.MAX_TOTAL_UPLOAD_SIZE // (1024*1024)}MB"
                    )
                )

            file_data.append(FileInfo(
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size=len(content),
                content=content
            ))

            logger.info(
                f"Accepted file: {file.filename} "
                f"({len(content) // 1024}KB, total: {total_size // 1024}KB)"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process file: {str(e)}"
            )
    
    # Process audio with size limits
    audio_data = None
    if audio and audio.filename:
        try:
            # Read audio content
            audio_content = await audio.read()

            # Enforce audio file size limit
            if len(audio_content) > settings.MAX_FILE_SIZE_HTTP:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Audio file exceeds maximum size of "
                        f"{settings.MAX_FILE_SIZE_HTTP // (1024*1024)}MB"
                    )
                )

            audio_data = FileInfo(
                filename=audio.filename or "recording.wav",
                content_type=audio.content_type or "audio/wav",
                size=len(audio_content),
                content=audio_content
            )

            logger.info(f"Accepted audio: {audio.filename} ({len(audio_content) // 1024}KB)")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process audio: {str(e)}"
            )
    
    # Create request object
    request_obj = HttpIngressRequest(
        user_id=user_id,
        input_text=input_text,
        token=token,
        files=file_data,
        audio=audio_data
    )



    # Build payload with files and audio
    payload = {
        "text": request_obj.input_text
    }

    # Add files to payload if present
    if request_obj.files:
        payload["files"] = []
        for f in request_obj.files:
            try:
                logger.info(f"Processing uploaded file: {f.filename} of type {f.content_type} and size {f.size}")

                # Use FileManager for unified file handling
                file_result = await file_manager.receive_file(
                    user_id=user_id,
                    platform="praxos_web",
                    file_bytes=f.content,  # Already in memory from form upload
                    filename=f.filename,
                    mime_type=f.content_type,
                    caption="",
                    platform_file_id=None,
                    platform_message_id=None,
                    conversation_id=None,  # Not known yet
                    auto_add_to_media_bus=False,  # Will be added when conversation processes it
                    auto_cleanup=False  # No temp file to cleanup
                )

                payload["files"].append(file_result.to_event_file_entry())

            except Exception as e:
                logger.error(f"Failed to process HTTP file {f.filename}: {e}", exc_info=True)

        payload["file_count"] = len(request_obj.files)
    
    # Add audio to payload if present
    if request_obj.audio:
        try:
            if "files" not in payload:
                payload["files"] = []

            logger.info(f"Processing uploaded audio: {request_obj.audio.filename}")

            # Use FileManager for unified audio handling
            file_result = await file_manager.receive_file(
                user_id=user_id,
                platform="praxos_web",
                file_bytes=request_obj.audio.content,
                filename=request_obj.audio.filename,
                mime_type=request_obj.audio.content_type,
                caption="",
                platform_file_id=None,
                platform_message_id=None,
                platform_type="voice",  # Hint that it's audio
                conversation_id=None,  # Not known yet
                auto_add_to_media_bus=False,
                auto_cleanup=False
            )

            payload["files"].append(file_result.to_event_file_entry())

        except Exception as e:
            logger.error(f"Failed to process HTTP audio {request_obj.audio.filename}: {e}", exc_info=True)

    conversation_manager = ConversationManager(conversation_db, integration_service)
    conversation_id = await conversation_manager.get_or_create_conversation(request_obj.user_id, "websocket", payload)
    

    event = {
        "user_id": request_obj.user_id,
        "source": "websocket",
        "payload": payload,
        'logging_context': {'user_id': user_id, 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
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
    logger.info(f"Published event: {json.dumps(event, indent=2, default=str)}")
    
    return {
        "status": "accepted", 
        "message": "Event queued for processing.", 
        "conversation_id": conversation_id,
        "files_received": len(request_obj.files) if request_obj.files else 0,
        "audio_received": bool(request_obj.audio)
    }


@router.post("/file_import", status_code=status.HTTP_202_ACCEPTED)
async def handle_file_upload_request(
    request_body: Optional[IngestionRequest] = None,
    raw_request: Request = None,
    user_id: str = Form(None),
    files: List[UploadFile] = File(default=[]),
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
   
    if not all([user_id]):
        raise HTTPException(
            status_code=400, 
            detail="Missing required fields: user_id and token are required"
        )
        
    # Process uploaded files
    file_data = []
    logger.info(f"Number of files received: {len(files)}")
    for file in files:
        logger.info(f"Received file: {file.filename} of type {file.content_type} and size")
        if file.filename:  
            content = await file.read()
            file_data.append(FileInfo(
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size=len(content),
                content=content
            ))
    
    # Process audio
    # Create request object
    request_obj = FileUploadRequest(
        user_id=user_id,
        files=file_data
    )
    


    # Build payload with files and audio
    payload = {
    }

    # Add files to payload if present
    if request_obj.files:
        payload["files"] = []
        for f in request_obj.files:
            try:
                logger.info(f"Processing uploaded file: {f.filename} of type {f.content_type} and size {f.size}")

                # Use FileManager for unified file handling
                file_result = await file_manager.receive_file(
                    user_id=user_id,
                    platform="import_file_upload",
                    file_bytes=f.content,  # Already in memory from form upload
                    filename=f.filename,
                    mime_type=f.content_type,
                    caption="",
                    platform_file_id=None,
                    platform_message_id=None,
                    conversation_id=None,  # Not known yet
                    auto_add_to_media_bus=False,  # Will be added when ingested
                    auto_cleanup=False  # No temp file to cleanup
                )

                payload["files"].append(file_result.to_event_file_entry())
                logger.info(f"Inserted document record with ID: {file_result.inserted_id}")

            except Exception as e:
                logger.error(f"Failed to process import file {f.filename}: {e}", exc_info=True)

        payload["file_count"] = len(request_obj.files)
    


    ### TODO: Ingest into praxos. 
    try:
        ingestion_event = {
            "user_id": request_obj.user_id,
            "source": "file_ingestion", # A new source type for our worker to identify
            "payload": payload,
            "logging_context": {'user_id':user_id_var.get(), 'request_id': str(request_id_var.get()), 'modality': 'ingestion_api'},

            "metadata": {'ingest_type':'file_upload','source':'file_upload_api'}
        }
        await event_queue.publish(ingestion_event)
    except Exception as e:
        logger.error(f"Error publishing ingestion event for user {request_obj.user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to queue ingestion event."
        )
    return {
        "status": "accepted", 
        "message": "Upload queued", 
    }
@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(request: IngestionRequest):
    """
    Triggers the initial data ingestion by publishing an event to the queue.
    """
    user_id_var.set(str(request.user_id))
    modality_var.set("ingestion_sync")
    event = {
        "user_id": request.user_id,
        "source": "ingestion", # A new source type for our worker to identify
        "logging_context": {'user_id':user_id_var.get(), 'request_id': str(request_id_var.get()), 'modality': modality_var.get()},
        "payload": {
            "integration_id": request.integration_id
        },
        "metadata": {}
    }
    # await event_queue.publish(event)
    return {"status": "success", "message": f"Initial ingestion for {request.integration_id} has been queued for user {request.user_id}."}
