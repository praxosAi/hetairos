"""
Unified File Manager for handling files across all platforms.

This module provides a centralized interface for file reception, storage,
type detection, media bus integration, and payload building across Telegram,
WhatsApp, iMessage, and HTTP/WebSocket platforms.

Key features:
- Eliminates duplicate downloads (file handled once at reception)
- Centralizes file handling logic from 4+ webhook handlers
- Integrates with media bus for agent access
- Replaces build_payload_entry() logic
- Consistent file type detection and blob path generation
"""

import os
import mimetypes
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict
from bson import ObjectId
from datetime import datetime

from src.utils.blob_utils import (
    upload_bytes_to_blob_storage,
    upload_to_blob_storage,
    download_from_blob_storage_and_encode_to_base64,
    get_cdn_url,
    get_blob_sas_url
)
# NOTE: db_manager imported lazily to avoid circular import
# (database.py -> ai_service -> file_msg_utils -> file_manager -> database.py)
from src.core.media_bus import media_bus
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)


def _get_db_manager():
    """Lazy import of db_manager to avoid circular imports."""
    from src.utils.database import db_manager
    return db_manager


@dataclass
class FileResult:
    """
    Result from file reception containing all information needed for:
    - Event publishing
    - Payload building
    - Media bus registration
    - Agent access

    This eliminates the need to query the database multiple times.
    """
    inserted_id: str              # MongoDB document ID
    blob_path: str                # Path in blob storage (e.g., "user_id/files/telegram/photo.jpg")
    file_name: str                # Original or generated filename
    file_type: str                # Normalized: image, video, audio, document, file
    mime_type: Optional[str]      # MIME type (e.g., "image/jpeg")
    size: int                     # File size in bytes
    user_id: str                  # User ID
    platform: str                 # Source platform (telegram, whatsapp, imessage, praxos_web)

    # Optional fields
    url: Optional[str] = None     # CDN URL (for images) or SAS URL (auto-generated if needed)
    caption: str = ""             # Caption/description
    container_name: Optional[str] = None  # Blob container name
    platform_file_id: Optional[str] = None  # Platform-specific file ID
    platform_message_id: Optional[str] = None  # Platform-specific message ID
    created_at: Optional[str] = None  # ISO timestamp
    metadata: Dict = field(default_factory=dict)  # Additional metadata

    def to_dict(self) -> Dict:
        """Convert to dictionary for event payloads"""
        return {
            'inserted_id': self.inserted_id,
            'blob_path': self.blob_path,
            'file_name': self.file_name,
            'type': self.file_type,
            'mime_type': self.mime_type,
            'size': self.size,
            'caption': self.caption,
            'url': self.url,
            'platform': self.platform,
            'platform_file_id': self.platform_file_id,
            'platform_message_id': self.platform_message_id,
            'metadata': self.metadata
        }

    def to_event_file_entry(self) -> Dict:
        """Format for event payload 'files' array"""
        return {
            'type': self.file_type,
            'blob_path': self.blob_path,
            'mime_type': self.mime_type,
            'caption': self.caption,
            'inserted_id': self.inserted_id,
            'file_name': self.file_name
        }


class FileManager:
    """
    Unified file management system for all platforms.

    Replaces scattered file handling logic across webhook handlers with
    a single, consistent interface.

    Key responsibilities:
    - File type detection and normalization
    - Blob storage with standardized paths
    - MongoDB document creation
    - Media bus integration
    - LLM payload building (replaces build_payload_entry)
    - Temp file cleanup
    """

    # Standardized file type categories
    FILE_TYPE_MAPPINGS = {
        'image': {
            'mime_prefixes': ['image/'],
            'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic', '.heif', '.ico']
        },
        'video': {
            'mime_prefixes': ['video/'],
            'extensions': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg']
        },
        'audio': {
            'mime_prefixes': ['audio/'],
            'extensions': ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma', '.caf', '.opus']
        },
        'document': {
            'mime_types': [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-powerpoint',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'text/plain',
                'text/csv',
                'text/html',
                'application/json',
                'application/xml',
                'text/xml',
                'application/rtf',
                'text/markdown',
                'text/x-markdown'
            ],
            'extensions': [
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.txt', '.csv', '.html', '.htm', '.json', '.xml', '.rtf', '.md'
            ]
        }
    }

    def __init__(self):
        """Initialize FileManager with logging."""
        self.logger = logger

    def detect_file_type(
        self,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
        platform_type: Optional[str] = None
    ) -> str:
        """
        Unified file type detection across all platforms.

        Priority order:
        1. MIME type matching (most reliable)
        2. File extension matching
        3. Platform-provided type (Telegram, WhatsApp)
        4. Default to 'file'

        Args:
            mime_type: MIME type string (e.g., 'image/jpeg')
            filename: Filename with extension (e.g., 'photo.jpg')
            platform_type: Platform-specific type (e.g., 'photo', 'voice', 'document')

        Returns:
            Normalized file type: 'image', 'video', 'audio', 'document', or 'file'
        """
        # Try MIME type first (most reliable)
        if mime_type:
            mime_type_lower = mime_type.lower().split(';')[0].strip()

            for file_type, mappings in self.FILE_TYPE_MAPPINGS.items():
                # Check exact MIME type matches
                if 'mime_types' in mappings and mime_type_lower in mappings['mime_types']:
                    return file_type

                # Check MIME type prefixes (e.g., 'image/')
                if 'mime_prefixes' in mappings:
                    if any(mime_type_lower.startswith(prefix) for prefix in mappings['mime_prefixes']):
                        return file_type

        # Try file extension
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext:
                for file_type, mappings in self.FILE_TYPE_MAPPINGS.items():
                    if 'extensions' in mappings and ext in mappings['extensions']:
                        return file_type

        # Map platform-specific types
        if platform_type:
            platform_type_lower = platform_type.lower()
            # Telegram/WhatsApp type mappings
            type_map = {
                'photo': 'image',
                'sticker': 'image',
                'voice': 'audio',
                'video_note': 'video'
            }
            if platform_type_lower in type_map:
                return type_map[platform_type_lower]
            # If platform type is already normalized (image, video, audio, document)
            if platform_type_lower in ['image', 'video', 'audio', 'document']:
                return platform_type_lower

        # Default to generic 'file'
        return 'file'

    def _sanitize_filename(self, filename: str) -> str:
        """
        Robustly sanitize filename to prevent path traversal and other attacks.

        Protections:
        - Removes path components (only keeps base filename)
        - Removes null bytes
        - Normalizes Unicode
        - Blocks dangerous characters
        - Prevents Windows reserved names
        - Limits length

        Args:
            filename: Original filename

        Returns:
            Sanitized safe filename
        """
        if not filename:
            return "unnamed_file"

        import uuid
        import unicodedata

        # Step 1: Remove any path components (most important!)
        # This extracts just the filename, removing directory paths
        filename = os.path.basename(filename)

        # Step 2: Remove null bytes (used for filter bypass)
        filename = filename.replace('\x00', '')

        # Step 3: Normalize Unicode (prevents homograph attacks)
        try:
            filename = unicodedata.normalize('NFKD', filename)
        except Exception:
            pass

        # Step 4: Remove/replace dangerous characters
        # Allowed: alphanumeric, dash, underscore, dot
        # Replace everything else with underscore
        filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

        # Step 5: Remove leading/trailing dots and spaces
        filename = filename.strip('. ')

        # Step 6: Prevent multiple consecutive dots (could be traversal attempt)
        filename = re.sub(r'\.{2,}', '.', filename)

        # Step 7: Prevent Windows reserved names
        reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]

        name_without_ext = os.path.splitext(filename)[0].upper()
        if name_without_ext in reserved_names:
            filename = f'file_{filename}'

        # Step 8: Ensure filename is not empty after sanitization
        if not filename or filename == '.' or filename == '_':
            filename = f'unnamed_{uuid.uuid4().hex[:8]}'

        # Step 9: Limit length (prevent long filename DOS)
        max_length = 255
        if len(filename) > max_length:
            # Keep extension
            name, ext = os.path.splitext(filename)
            name = name[:max_length - len(ext) - 10]  # Leave room for unique ID
            filename = f"{name}{ext}"

        return filename

    def _generate_blob_path(
        self,
        user_id: str,
        platform: str,
        filename: str
    ) -> str:
        """
        Generate standardized blob storage path with uniqueness guarantee.

        New pattern: {user_id}/files/{platform}/{timestamp}_{uuid}_{filename}

        This ensures:
        - No file overwrites (timestamp + UUID)
        - Path traversal protection (sanitized components)
        - Consistent structure across platforms

        Args:
            user_id: User ID
            platform: Platform name (telegram, whatsapp, imessage, praxos_web)
            filename: Original or generated filename

        Returns:
            Blob storage path
        """
        import uuid

        # Sanitize all path components
        safe_filename = self._sanitize_filename(filename)
        safe_user_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(user_id))
        safe_platform = re.sub(r'[^a-zA-Z0-9_-]', '_', str(platform))

        # Add timestamp and UUID for guaranteed uniqueness
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]

        # Generate path: {user_id}/files/{platform}/{timestamp}_{uuid}_{filename}
        blob_path = f"{safe_user_id}/files/{safe_platform}/{timestamp}_{unique_id}_{safe_filename}"

        # Final validation: ensure no traversal patterns remain
        if '..' in blob_path or blob_path.startswith('/'):
            logger.error(f"Generated blob path contains invalid patterns: {blob_path}")
            raise ValueError("Generated blob path failed security validation")

        return blob_path

    def _determine_container(self, file_type: str) -> Optional[str]:
        """
        Determine which blob container to use based on file type.

        Images go to CDN container for public access.
        Everything else goes to default container (more secure).

        Args:
            file_type: Normalized file type

        Returns:
            Container name or None for default
        """
        if file_type == 'image':
            return 'cdn-container'
        return None  # Use default container from settings

    def generate_filename(
        self,
        platform: str,
        platform_file_id: str,
        extension: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_filename: Optional[str] = None
    ) -> str:
        """
        Generate a filename when platform doesn't provide one.

        Useful for WhatsApp which doesn't provide original filenames.

        Args:
            platform: Platform name
            platform_file_id: Platform-specific file ID
            extension: File extension (with or without dot)
            mime_type: MIME type to guess extension from
            original_filename: Original filename if available (preferred)

        Returns:
            Generated filename
        """
        if original_filename:
            return original_filename

        # Ensure extension has dot
        if extension and not extension.startswith('.'):
            extension = f'.{extension}'

        # Try to guess extension from MIME type if not provided
        if not extension and mime_type:
            guessed_ext = mimetypes.guess_extension(mime_type)
            if guessed_ext:
                extension = guessed_ext

        # Default extension if still not found
        if not extension:
            extension = '.bin'

        # Create filename with platform prefix for easy identification
        filename = f"{platform}_{platform_file_id}{extension}"
        return filename

    async def receive_file(
        self,
        user_id: str,
        platform: str,
        file_bytes: Optional[bytes] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        caption: str = "",
        platform_file_id: Optional[str] = None,
        platform_message_id: Optional[str] = None,
        platform_type: Optional[str] = None,
        metadata: Optional[Dict] = None,
        conversation_id: Optional[str] = None,
        auto_add_to_media_bus: bool = True,
        auto_cleanup: bool = True
    ) -> FileResult:
        """
        Unified file reception handler for all platforms.

        This is the main entry point for file handling. It:
        1. Reads file bytes (from bytes or path)
        2. Detects file type using unified detection
        3. Uploads to appropriate blob container
        4. Creates MongoDB document with consistent schema
        5. Optionally adds to media bus (if conversation_id provided)
        6. Cleans up temp files if requested
        7. Returns FileResult with all info needed for events/payloads

        Args:
            user_id: User ID
            platform: Platform name (telegram, whatsapp, imessage, praxos_web)
            file_bytes: File content as bytes (preferred)
            file_path: Path to file on disk (will be read if file_bytes not provided)
            filename: Original filename (if not provided, will be generated)
            mime_type: MIME type
            caption: File caption/description
            platform_file_id: Platform-specific file ID for deduplication
            platform_message_id: Platform-specific message ID
            platform_type: Platform-specific type hint
            metadata: Additional metadata to store
            conversation_id: Optional conversation ID for media bus registration
            auto_add_to_media_bus: If True and conversation_id provided, add to media bus
            auto_cleanup: Whether to delete temp files after upload

        Returns:
            FileResult with all file information

        Raises:
            ValueError: If validation fails (missing required params, invalid values)
            FileNotFoundError: If file_path provided but doesn't exist
            IOError: If file reading fails
            Exception: If blob upload or database operations fail
        """
        # Validation
        if not user_id:
            raise ValueError("user_id is required")

        if not platform:
            raise ValueError("platform is required")

        if not file_bytes and not file_path:
            raise ValueError("Either file_bytes or file_path must be provided")

        # Validate platform is known
        valid_platforms = ['telegram', 'whatsapp', 'imessage', 'praxos_web', 'import_file_upload']
        if platform not in valid_platforms:
            self.logger.warning(f"Unknown platform: {platform}. Proceeding anyway.")

        # Read file if only path provided
        file_size = None
        if file_path and not file_bytes:
            try:
                # Check file exists first
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"File not found: {file_path}")

                # Check file is readable
                if not os.access(file_path, os.R_OK):
                    raise IOError(f"File not readable: {file_path}")

                with open(file_path, 'rb') as f:
                    file_bytes = f.read()
                file_size = os.path.getsize(file_path)

                if file_size == 0:
                    self.logger.warning(f"File is empty: {file_path}")

            except FileNotFoundError:
                self.logger.error(f"File not found: {file_path}")
                raise
            except IOError as e:
                self.logger.error(f"Failed to read file from path {file_path}: {e}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error reading file from path {file_path}: {e}")
                raise IOError(f"Failed to read file: {e}") from e

        if not file_size:
            file_size = len(file_bytes) if file_bytes else 0

        # Auto-detect MIME type if not provided
        if not mime_type and filename:
            guessed_mime = mimetypes.guess_type(filename)[0]
            if guessed_mime:
                mime_type = guessed_mime
                self.logger.debug(f"Auto-detected MIME type: {mime_type} for {filename}")

        # Generate filename if not provided (e.g., WhatsApp)
        if not filename:
            filename = self.generate_filename(
                platform=platform,
                platform_file_id=platform_file_id or "unknown",
                mime_type=mime_type
            )
            self.logger.info(f"Generated filename: {filename}")

        # SECURITY: Validate file content before upload
        from src.utils.file_validator import file_validator

        is_valid, actual_mime, error_reason = file_validator.validate_file_content(
            file_bytes=file_bytes,
            claimed_mime=mime_type,
            filename=filename
        )

        if not is_valid:
            self.logger.warning(
                f"File validation failed: {filename} - {error_reason}"
            )
            raise ValueError(f"File rejected: {error_reason}")

        # Use actual detected MIME type if available (more trustworthy)
        if actual_mime:
            mime_type = actual_mime
            self.logger.debug(f"Using validated MIME type: {mime_type}")

        # Detect unified file type
        file_type = self.detect_file_type(
            mime_type=mime_type,
            filename=filename,
            platform_type=platform_type
        )

        self.logger.info(
            f"Processing file: {filename} | "
            f"Type: {file_type} | "
            f"MIME: {mime_type} | "
            f"Platform: {platform} | "
            f"Size: {file_size} bytes"
        )

        # Generate standardized blob path
        blob_name = self._generate_blob_path(user_id, platform, filename)

        # Determine container (CDN for images, default for others)
        container = self._determine_container(file_type)

        # Upload to blob storage
        try:
            blob_path = await upload_bytes_to_blob_storage(
                data=file_bytes,
                blob_name=blob_name,
                content_type=mime_type,
                container_name=container
            )
            self.logger.info(f"Uploaded to blob storage: {blob_path} (container: {container or 'default'})")
        except ValueError as e:
            # Blob storage validation error
            self.logger.error(f"Invalid blob storage parameters for {filename}: {e}")
            raise ValueError(f"Failed to upload file: Invalid parameters - {e}") from e
        except ConnectionError as e:
            self.logger.error(f"Network error uploading {filename} to blob storage: {e}")
            raise ConnectionError(f"Failed to upload file: Network error - {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error uploading {filename} to blob storage: {e}", exc_info=True)
            raise RuntimeError(f"Failed to upload file to storage: {e}") from e

        # Create standardized MongoDB document
        document_entry = {
            "user_id": ObjectId(user_id),
            "platform": platform,
            "type": file_type,
            "blob_path": blob_path,
            "mime_type": mime_type,
            "file_name": filename,
            "caption": caption,
            "size": file_size,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Add optional fields if provided
        if platform_file_id:
            document_entry["platform_file_id"] = platform_file_id
        if platform_message_id:
            document_entry["platform_message_id"] = platform_message_id
        if metadata:
            document_entry["metadata"] = metadata

        # Insert to MongoDB
        try:
            inserted_id = await _get_db_manager().add_document(document_entry)
            self.logger.info(f"Created document in MongoDB: {inserted_id}")
        except ValueError as e:
            # Database validation error (e.g., invalid ObjectId)
            self.logger.error(f"Invalid MongoDB document data for {filename}: {e}")
            raise ValueError(f"Failed to create file record: Invalid data - {e}") from e
        except ConnectionError as e:
            self.logger.error(f"Database connection error while saving {filename}: {e}")
            raise ConnectionError(f"Failed to create file record: Database connection error - {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error creating MongoDB document for {filename}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create file record in database: {e}") from e

        # Generate URL (CDN for images, will be generated on-demand for others)
        url = None
        if file_type == 'image':
            try:
                url = await get_cdn_url(blob_path, container_name='cdn-container')
            except Exception as e:
                self.logger.warning(f"Failed to get CDN URL: {e}")

        # Create FileResult
        file_result = FileResult(
            inserted_id=inserted_id,
            blob_path=blob_path,
            file_name=filename,
            file_type=file_type,
            mime_type=mime_type,
            size=file_size,
            user_id=user_id,
            platform=platform,
            url=url,
            caption=caption,
            container_name=container or settings.AZURE_BLOB_CONTAINER_NAME,
            platform_file_id=platform_file_id,
            platform_message_id=platform_message_id,
            created_at=document_entry["created_at"],
            metadata=metadata or {}
        )

        # Add to media bus if conversation_id provided and auto_add enabled
        if conversation_id and auto_add_to_media_bus:
            try:
                await self.add_to_media_bus(file_result, conversation_id)
            except Exception as e:
                self.logger.error(f"Failed to add file to media bus: {e}")
                # Don't fail the entire operation if media bus fails

        # Clean up temp file if provided and auto_cleanup enabled
        if auto_cleanup and file_path:
            try:
                os.unlink(file_path)
                self.logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

        return file_result

    async def receive_multiple_files(
        self,
        user_id: str,
        platform: str,
        files: List[Dict],
        conversation_id: Optional[str] = None,
        auto_add_to_media_bus: bool = True,
        auto_cleanup: bool = True
    ) -> List[FileResult]:
        """
        Receive multiple files at once (batch operation).

        Args:
            user_id: User ID
            platform: Platform name
            files: List of file dictionaries with same keys as receive_file()
            conversation_id: Optional conversation ID for media bus
            auto_add_to_media_bus: If True and conversation_id provided, add to media bus
            auto_cleanup: Whether to cleanup temp files

        Returns:
            List of FileResult objects
        """
        results = []
        for file_data in files:
            try:
                file_result = await self.receive_file(
                    user_id=user_id,
                    platform=platform,
                    conversation_id=conversation_id,
                    auto_add_to_media_bus=auto_add_to_media_bus,
                    auto_cleanup=auto_cleanup,
                    **file_data
                )
                results.append(file_result)
            except Exception as e:
                self.logger.error(f"Failed to receive file {file_data.get('filename')}: {e}")
                # Continue processing other files
                continue

        return results

    async def build_payload(
        self,
        file_result: FileResult,
        force_download: bool = False
    ) -> Optional[Dict]:
        """
        Build LLM-compatible payload from FileResult.

        Replaces the logic from build_payload_entry() in file_msg_utils.py.

        This method is more efficient because it uses the FileResult that already
        has all the information, rather than querying the database again.

        Args:
            file_result: FileResult from receive_file()
            force_download: If True, download file even for images (for reprocessing)

        Returns:
            LLM payload dictionary or None if failed
        """
        try:
            ftype = file_result.file_type
            blob_path = file_result.blob_path
            mime_type = file_result.mime_type

            if ftype in {"image", "photo"}:
                # Images use CDN URL (already in file_result)
                if not file_result.url:
                    # Generate URL if not already present
                    file_result.url = await get_cdn_url(blob_path, container_name='cdn-container')

                payload = {"type": "image_url", "image_url": file_result.url}
                self.logger.debug(f"Built image payload with CDN URL")

            elif ftype in {"voice", "audio", "video"}:
                # Download and encode to base64 for LLM processing
                data_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)
                payload = {
                    "type": "media",
                    "data": data_b64,
                    "mime_type": mime_type or f"{ftype}/ogg"
                }
                self.logger.debug(f"Built {ftype} payload with base64 encoding")

            elif ftype in {"document", "file"}:
                # Documents: download and encode
                data_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)
                payload = {
                    "type": "file",
                    "source_type": "base64",
                    "mime_type": mime_type or "application/octet-stream",
                    "data": data_b64,
                }
                self.logger.debug(f"Built document payload with base64 encoding")
            else:
                self.logger.warning(f"Unknown file type: {ftype}")
                return None

            return payload

        except Exception as e:
            self.logger.error(f"Failed to build payload for {file_result.file_name}: {e}")
            return None

    async def build_payload_from_id(
        self,
        inserted_id: str,
        conversation_id: Optional[str] = None,
        add_to_media_bus: bool = False
    ) -> Tuple[Optional[Dict], Optional[FileResult]]:
        """
        Build payload from MongoDB document ID.

        Replacement for build_payload_entry_from_inserted_id() in file_msg_utils.py.

        Args:
            inserted_id: MongoDB document ID
            conversation_id: Optional conversation ID for media bus
            add_to_media_bus: If True and conversation_id provided, add to media bus

        Returns:
            Tuple of (payload_dict, file_result) or (None, None) if not found
        """
        try:
            # Get document from database
            document = await _get_db_manager().get_document_by_id(inserted_id)
            if not document:
                self.logger.warning(f"Document not found: {inserted_id}")
                return None, None

            # Convert document to FileResult
            file_result = FileResult(
                inserted_id=inserted_id,
                blob_path=document.get("blob_path"),
                file_name=document.get("file_name", "unknown"),
                file_type=document.get("type", "file"),
                mime_type=document.get("mime_type"),
                size=document.get("size", 0),
                user_id=str(document.get("user_id")),
                platform=document.get("platform", "unknown"),
                url=None,  # Will be generated if needed
                caption=document.get("caption", ""),
                container_name=document.get("container_name", settings.AZURE_BLOB_CONTAINER_NAME),
                platform_file_id=document.get("platform_file_id"),
                platform_message_id=document.get("platform_message_id"),
                created_at=document.get("created_at"),
                metadata=document.get("metadata", {})
            )

            # Build payload
            payload = await self.build_payload(file_result)

            # Add to media bus if requested
            if add_to_media_bus and conversation_id:
                await self.add_to_media_bus(file_result, conversation_id)

            return payload, file_result

        except Exception as e:
            self.logger.error(f"Failed to build payload from ID {inserted_id}: {e}")
            return None, None

    async def add_to_media_bus(
        self,
        file_result: FileResult,
        conversation_id: str,
        description: Optional[str] = None
    ) -> str:
        """
        Register file with media bus for agent access.

        Can be called at file reception (if conversation_id known) or later
        when the conversation starts.

        Args:
            file_result: FileResult from receive_file()
            conversation_id: Conversation ID to register with
            description: Optional description (auto-generated if not provided)

        Returns:
            media_id from media bus
        """
        try:
            # Generate URL if not already present
            url = file_result.url
            if not url:
                if file_result.file_type == 'image':
                    url = await get_cdn_url(file_result.blob_path, container_name='cdn-container')
                else:
                    # Generate SAS URL for non-images
                    url = await get_blob_sas_url(
                        file_result.blob_path,
                        container_name=file_result.container_name
                    )

            # Auto-generate description if not provided
            if not description:
                caption_part = f": {file_result.caption}" if file_result.caption else ""
                description = f"User uploaded {file_result.file_type}{caption_part}"

            # Add to media bus
            media_id = await media_bus.add_media(
                conversation_id=conversation_id,
                url=url,
                file_name=file_result.file_name,
                file_type=file_result.file_type,
                description=description,
                source="uploaded",
                blob_path=file_result.blob_path,
                mime_type=file_result.mime_type,
                metadata=file_result.metadata,
                container_name=file_result.container_name
            )

            self.logger.info(
                f"Added file to media bus: {media_id} "
                f"({file_result.file_type}) - {file_result.file_name} "
                f"(conversation={conversation_id})"
            )

            return media_id

        except Exception as e:
            self.logger.error(
                f"Failed to add file to media bus: {file_result.file_name} "
                f"(conversation={conversation_id}): {e}"
            )
            raise

    async def get_file_by_id(self, file_id: str) -> Optional[FileResult]:
        """
        Retrieve file metadata by MongoDB document ID as FileResult.

        Args:
            file_id: MongoDB document ID (inserted_id)

        Returns:
            FileResult or None if not found
        """
        document = await _get_db_manager().get_document_by_id(file_id)
        if not document:
            return None

        return FileResult(
            inserted_id=file_id,
            blob_path=document.get("blob_path"),
            file_name=document.get("file_name", "unknown"),
            file_type=document.get("type", "file"),
            mime_type=document.get("mime_type"),
            size=document.get("size", 0),
            user_id=str(document.get("user_id")),
            platform=document.get("platform", "unknown"),
            url=None,
            caption=document.get("caption", ""),
            container_name=document.get("container_name", settings.AZURE_BLOB_CONTAINER_NAME),
            platform_file_id=document.get("platform_file_id"),
            platform_message_id=document.get("platform_message_id"),
            created_at=document.get("created_at"),
            metadata=document.get("metadata", {})
        )

    async def get_file_by_source_id(self, source_id: str) -> Optional[FileResult]:
        """
        Retrieve file metadata by Praxos source_id as FileResult.

        This is the primary method for file retrieval after Praxos search.

        Args:
            source_id: Praxos source_id (from search results)

        Returns:
            FileResult or None if not found
        """
        document = await _get_db_manager().get_document_by_source_id(source_id)
        if not document:
            return None

        return FileResult(
            inserted_id=str(document.get("_id")),
            blob_path=document.get("blob_path"),
            file_name=document.get("file_name", "unknown"),
            file_type=document.get("type", "file"),
            mime_type=document.get("mime_type"),
            size=document.get("size", 0),
            user_id=str(document.get("user_id")),
            platform=document.get("platform", "unknown"),
            url=None,
            caption=document.get("caption", ""),
            container_name=document.get("container_name", settings.AZURE_BLOB_CONTAINER_NAME),
            platform_file_id=document.get("platform_file_id"),
            platform_message_id=document.get("platform_message_id"),
            created_at=document.get("created_at"),
            metadata=document.get("metadata", {})
        )

    async def get_files_by_user(
        self,
        user_id: str,
        platform: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 50
    ) -> List[FileResult]:
        """
        Get files for a user with optional filtering.

        Args:
            user_id: User ID
            platform: Optional platform filter
            file_type: Optional file type filter (image, video, audio, document, file)
            limit: Maximum number of results

        Returns:
            List of FileResult objects
        """
        query = {"user_id": ObjectId(user_id)}

        if platform:
            query["platform"] = platform

        if file_type:
            query["type"] = file_type

        cursor = _get_db_manager().documents.find(query).sort("created_at", -1).limit(limit)
        documents = await cursor.to_list(length=limit)

        results = []
        for doc in documents:
            file_result = FileResult(
                inserted_id=str(doc.get("_id")),
                blob_path=doc.get("blob_path"),
                file_name=doc.get("file_name", "unknown"),
                file_type=doc.get("type", "file"),
                mime_type=doc.get("mime_type"),
                size=doc.get("size", 0),
                user_id=str(doc.get("user_id")),
                platform=doc.get("platform", "unknown"),
                url=None,
                caption=doc.get("caption", ""),
                container_name=doc.get("container_name", settings.AZURE_BLOB_CONTAINER_NAME),
                platform_file_id=doc.get("platform_file_id"),
                platform_message_id=doc.get("platform_message_id"),
                created_at=doc.get("created_at"),
                metadata=doc.get("metadata", {})
            )
            results.append(file_result)

        return results


# Singleton instance
file_manager = FileManager()
