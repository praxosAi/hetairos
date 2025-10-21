"""
Media Bus: In-memory reference system for media during agent execution.

Provides a centralized way for agents to track and reference media that has been
generated or received during the current conversation turn. This enables:
- Using previous media to inspire new media
- Referencing multiple generated items
- Building on previous outputs

The bus is execution-scoped and cleared after each conversation turn completes.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from src.utils.logging import setup_logger
from src.config.settings import settings
logger = setup_logger(__name__)


@dataclass
class MediaReference:
    """Reference to a media item in the bus."""
    media_id: str
    url: str
    file_name: str
    file_type: str  # image, audio, video, document
    description: str  # Natural language description for agent
    timestamp: datetime
    source: str  # "generated", "uploaded", "fetched"
    blob_path: Optional[str] = None  # Blob storage path for downloading
    mime_type: Optional[str] = None  # MIME type (image/png, audio/ogg, etc.)
    loaded_in_context: bool = False  # Track if already added to conversation context
    metadata: Dict[str, Any] = field(default_factory=dict)
    container_name: Optional[str] = settings.AZURE_BLOB_CONTAINER_NAME  # Blob container name

class MediaBus:
    """
    In-memory media reference system for current execution.

    Provides agent with access to media generated or received during
    the current conversation turn. Cleared after execution completes.

    This is NOT a storage system - it's a reference/catalog system.
    Actual media files are stored in blob storage; this tracks URLs and metadata.
    """

    def __init__(self):
        # Execution-scoped storage: conversation_id -> list of media references
        self._storage: Dict[str, List[MediaReference]] = {}
        logger.info("MediaBus initialized")

    def add_media(
        self,
        conversation_id: str,
        url: str,
        file_name: str,
        file_type: str,
        description: str,
        source: str = "generated",
        blob_path: Optional[str] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        container_name: Optional[str] = settings.AZURE_BLOB_CONTAINER_NAME
    ) -> str:
        """
        Add a media reference to the bus.

        Args:
            conversation_id: The conversation this media belongs to
            url: The blob URL (SAS URL for access)
            file_name: Name of the file
            file_type: Type (image, audio, video, document)
            description: Natural language description for the agent to understand context
            source: How this media was obtained (generated/uploaded/fetched)
            blob_path: Optional blob storage path (for downloading)
            mime_type: Optional MIME type (image/png, audio/ogg, video/mp4, etc.)
            metadata: Additional metadata (prompts, generation params, etc.)

        Returns:
            media_id: Unique identifier for this media reference
        """
        # media_id = str(uuid.uuid4())
        media_id = str(len(self._storage.get(conversation_id, [])) + 1)  # Use index as media ID
        ### simply use the index as media id to make it easier to reference multiple media in order
        ref = MediaReference(
            media_id=media_id,
            url=url,
            file_name=file_name,
            file_type=file_type,
            description=description,
            timestamp=datetime.utcnow(),
            source=source,
            blob_path=blob_path,
            mime_type=mime_type,
            loaded_in_context=False,
            metadata=metadata or {},
            container_name=container_name
        )

        if conversation_id not in self._storage:
            self._storage[conversation_id] = []

        self._storage[conversation_id].append(ref)

        logger.info(
            f"Added media to bus: {media_id} ({file_type}) - {description[:50]}... "
            f"(conversation={conversation_id})"
        )

        return media_id

    def get_media(self, conversation_id: str, media_id: str) -> Optional[MediaReference]:
        """
        Retrieve a specific media reference by ID.

        Args:
            conversation_id: The conversation ID
            media_id: The unique media ID

        Returns:
            MediaReference or None if not found
        """
        if conversation_id not in self._storage:
            logger.warning(f"Conversation {conversation_id} not found in media bus")
            return None

        for ref in self._storage[conversation_id]:
            if ref.media_id == media_id:
                return ref

        logger.warning(f"Media {media_id} not found in conversation {conversation_id}")
        return None

    def list_media(
        self,
        conversation_id: str,
        file_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[MediaReference]:
        """
        List media references for a conversation.

        Args:
            conversation_id: The conversation ID
            file_type: Optional filter by type (image, audio, video, document)
            limit: Optional limit on number of results

        Returns:
            List of media references, most recent first
        """
        if conversation_id not in self._storage:
            logger.debug(f"No media found for conversation {conversation_id}")
            return []

        refs = self._storage[conversation_id]

        # Filter by type if specified
        if file_type:
            refs = [r for r in refs if r.file_type == file_type]

        # Sort by timestamp, most recent first
        refs = sorted(refs, key=lambda r: r.timestamp, reverse=True)

        # Apply limit
        if limit:
            refs = refs[:limit]

        logger.debug(f"Listed {len(refs)} media items for conversation {conversation_id}")
        return refs

    def clear_conversation(self, conversation_id: str) -> int:
        """
        Clear all media for a conversation (called after execution).

        Args:
            conversation_id: The conversation ID to clear

        Returns:
            Number of media items cleared
        """
        if conversation_id in self._storage:
            count = len(self._storage[conversation_id])
            del self._storage[conversation_id]
            logger.info(f"Cleared {count} media references from bus for conversation {conversation_id}")
            return count
        return 0

    def get_stats(self, conversation_id: str) -> Dict[str, int]:
        """
        Get statistics about media in the bus for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            Dictionary with counts by type and total
        """
        if conversation_id not in self._storage:
            return {"total": 0}

        refs = self._storage[conversation_id]
        stats = {"total": len(refs)}

        # Count by type
        for ref in refs:
            stats[ref.file_type] = stats.get(ref.file_type, 0) + 1

        return stats

    def has_media(self, conversation_id: str) -> bool:
        """Check if conversation has any media in the bus."""
        return conversation_id in self._storage and len(self._storage[conversation_id]) > 0

    def mark_loaded_in_context(self, conversation_id: str, media_id: str) -> bool:
        """
        Mark a media item as loaded in conversation context.

        Args:
            conversation_id: The conversation ID
            media_id: The media ID to mark

        Returns:
            True if marked successfully, False if media not found
        """
        ref = self.get_media(conversation_id, media_id)
        if ref:
            ref.loaded_in_context = True
            logger.debug(f"Marked media {media_id} as loaded in context")
            return True
        return False


# Global singleton instance (execution-scoped, cleared between runs)
media_bus = MediaBus()
