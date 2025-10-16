"""
MCP (Model Context Protocol) ingress handler
Provides API endpoint for MCP clients like Claude Code
"""

from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.core.event_queue import event_queue
from src.services.conversation_manager import ConversationManager
from src.utils.database import conversation_db
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.services.user_service import user_service
from src.utils.redis_client import subscribe_to_channel
import json
import uuid
import time
import asyncio

logger = setup_logger(__name__)

router = APIRouter()


class MCPRequest(BaseModel):
    """
    Request format for MCP endpoint
    Note: user_id is derived from API key, not provided in request
    """
    input: Dict[str, Any]  # Must contain 'text' key, optional 'metadata'


class MCPResponse(BaseModel):
    """
    Response format for MCP endpoint
    """
    response: str
    delivery_platform: Optional[str] = None
    execution_notes: Optional[str] = None
    output_modality: Optional[str] = "text"
    file_links: Optional[list] = []


@router.post("/mcp/run", status_code=status.HTTP_200_OK, response_model=MCPResponse)
async def handle_mcp_request(
    request: MCPRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Handle MCP client requests (e.g., from Claude Code)

    This endpoint:
    1. Validates the API key and derives user_id
    2. Queues the request for processing
    3. Waits for the result (TODO: implement sync response)
    4. Returns the formatted response

    Headers:
        Authorization: Bearer <api_key>

    Body:
        {
            "input": {
                "text": "Search my memory for API docs",
                "metadata": {...}  // optional
            }
        }
    """
    # Extract API key from Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <api_key>"
        )

    api_key = authorization.split("Bearer ", 1)[1].strip()

    # Get user_id from API key using user_service
    user_id = await user_service.get_user_id_from_api_key(api_key)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Set logging context
    user_id_var.set(str(user_id))
    modality_var.set("mcp")

    # Validate input format
    if not isinstance(request.input, dict) or "text" not in request.input:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input must be a dictionary with a 'text' key"
        )

    # Extract text and metadata
    input_text = request.input.get("text")
    input_metadata = request.input.get("metadata", {})

    if not input_text or not input_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input text cannot be empty"
        )

    # Generate unique request ID for this MCP request
    mcp_request_id = str(uuid.uuid4())
    response_channel = f"mcp-response:{mcp_request_id}"

    pubsub = None
    try:
        # Subscribe to response channel BEFORE publishing event
        logger.info(f"Subscribing to response channel: {response_channel}")
        pubsub = await subscribe_to_channel(response_channel)

        # Get or create conversation for MCP source
        conversation_manager = ConversationManager(conversation_db, integration_service)
        conversation_id = await conversation_manager.get_or_create_conversation(
            user_id,
            "mcp",
            {"text": input_text}
        )

        # Build event payload
        payload = {
            "text": input_text
        }

        event_metadata = {
            "conversation_id": conversation_id,
            "source": "mcp",
            "mcp_client": input_metadata.get("client", "unknown"),
            "timestamp": input_metadata.get("timestamp"),
            "mcp_request_id": mcp_request_id,
            "response_channel": response_channel,
            "capabilities": {
                "streaming": False  # MCP uses request-response, not streaming
            }
        }

        event = {
            "user_id": user_id,
            "source": "mcp",
            "output_type": "mcp",
            "payload": payload,
            "logging_context": {
                'user_id': user_id,
                'request_id': str(request_id_var.get()),
                'modality': 'mcp'
            },
            "metadata": event_metadata
        }

        # Publish event to queue
        logger.info(f"Publishing MCP event for user {user_id}: {input_text[:100]}")
        await event_queue.publish(event)

        # Wait for response via Redis pub/sub
        timeout = 120  # 2 minutes timeout
        start_time = time.time()

        logger.info(f"Waiting for response on channel {response_channel} (timeout: {timeout}s)")

        while time.time() - start_time < timeout:
            try:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0
                )

                if msg and msg.get('data'):
                    # Got response!
                    logger.info(f"Received response for MCP request {mcp_request_id}")

                    # Parse response data
                    if isinstance(msg['data'], bytes):
                        response_data = json.loads(msg['data'].decode('utf-8'))
                    else:
                        response_data = json.loads(msg['data'])

                    # Clean up subscription
                    await pubsub.close()

                    # Return response
                    return MCPResponse(**response_data)

            except asyncio.TimeoutError:
                # No message yet, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error reading from response channel: {e}", exc_info=True)
                continue

        # Timeout - no response received
        logger.error(f"Timeout waiting for response on {response_channel}")
        if pubsub:
            await pubsub.close()

        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Request timeout - agent did not respond within 2 minutes"
        )

    except HTTPException:
        if pubsub:
            await pubsub.close()
        raise
    except Exception as e:
        logger.error(f"Error processing MCP request for user {user_id}: {e}", exc_info=True)
        if pubsub:
            await pubsub.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process request: {str(e)}"
        )


@router.get("/mcp/health")
async def mcp_health_check():
    """
    Health check endpoint for MCP service
    """
    return {
        "status": "healthy",
        "service": "mcp-ingress",
        "version": "0.1.0"
    }
