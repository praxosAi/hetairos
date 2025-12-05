"""
File Content Validator

Validates uploaded files to prevent:
- Malicious file uploads (executables disguised as images)
- XSS attacks (HTML/JavaScript files)
- MIME type spoofing
- Polyglot files (valid image + embedded script)

Uses magic number detection to verify actual file content matches claimed type.
"""

import os
import re
from typing import Tuple, Optional
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

# Define allowed file types and their MIME types
ALLOWED_FILE_TYPES = {
    'image': {
        'mime_types': [
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'image/bmp',
            'image/svg+xml',
            'image/x-icon',
            'image/vnd.microsoft.icon'
        ],
        'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico']
    },
    'video': {
        'mime_types': [
            'video/mp4',
            'video/quicktime',
            'video/x-msvideo',
            'video/webm',
            'video/x-matroska',
            'video/mpeg'
        ],
        'extensions': ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.mpeg', '.mpg']
    },
    'audio': {
        'mime_types': [
            'audio/mpeg',
            'audio/ogg',
            'audio/wav',
            'audio/webm',
            'audio/mp4',
            'audio/x-m4a',
            'audio/aac',
            'audio/flac'
        ],
        'extensions': ['.mp3', '.ogg', '.wav', '.m4a', '.aac', '.flac', '.opus']
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
            'application/json',
            'application/rtf'
        ],
        'extensions': [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx',
            '.ppt', '.pptx', '.txt', '.csv', '.json', '.rtf'
        ]
    }
}

# Dangerous file types to always block
BLOCKED_FILE_TYPES = [
    # Executables
    'application/x-executable',
    'application/x-dosexec',
    'application/x-mach-binary',
    'application/x-sharedlib',
    'application/x-msdownload',
    'application/x-elf',

    # Scripts (XSS prevention)
    'text/html',
    'application/xhtml+xml',
    'text/javascript',
    'application/javascript',
    'application/x-javascript',

    # Shell scripts
    'application/x-sh',
    'application/x-bash',
    'text/x-shellscript',

    # Other scripting languages
    'application/x-python',
    'application/x-python-code',
    'text/x-python',
    'application/x-perl',
    'application/x-php',
    'text/x-php',

    # Archives that could contain executables
    # Note: .zip is intentionally not blocked as documents use it (docx, xlsx)
    # But we should scan archive contents in the future
]

# Dangerous extensions to block
BLOCKED_EXTENSIONS = [
    # Windows executables
    '.exe', '.dll', '.com', '.bat', '.cmd', '.msi', '.scr',

    # Unix executables
    '.sh', '.bash', '.bin', '.run', '.app', '.out',

    # Libraries
    '.so', '.dylib',

    # Scripts
    '.py', '.pyc', '.pyo', '.pyw',
    '.php', '.phtml', '.php3', '.php4', '.php5',
    '.js', '.mjs', '.jsx',
    '.pl', '.pm', '.cgi',
    '.rb', '.rbw',
    '.vbs', '.vbe',

    # Web files (XSS prevention)
    '.html', '.htm', '.xhtml',

    # Mac
    '.dmg', '.pkg',

    # Java
    '.jar', '.war', '.ear', '.class',
]


class FileValidator:
    """Validates file content against claimed type using magic number detection"""

    def __init__(self):
        self.magic_available = False
        try:
            import magic
            self.magic_detector = magic.Magic(mime=True)
            self.magic_available = True
            logger.info("python-magic library available - file content validation enabled")
        except ImportError:
            logger.warning(
                "python-magic library not installed. "
                "File content validation will use basic checks only. "
                "Install with: pip install python-magic"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize magic detector: {e}")

    def validate_file_content(
        self,
        file_bytes: bytes,
        claimed_mime: Optional[str],
        filename: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates file content matches claimed type.

        Args:
            file_bytes: File content
            claimed_mime: User-provided MIME type
            filename: Filename

        Returns:
            Tuple of (is_valid, actual_mime_type, reason_if_invalid)
        """
        # Step 1: Check file is not empty
        if not file_bytes or len(file_bytes) == 0:
            return False, None, "File is empty"

        # Step 2: Check extension against blocklist
        ext = os.path.splitext(filename)[1].lower()
        if ext in BLOCKED_EXTENSIONS:
            logger.warning(f"Blocked dangerous file extension: {ext} in {filename}")
            return False, None, f"File extension '{ext}' is blocked for security reasons"

        # Step 3: Detect actual MIME type from content (if magic available)
        actual_mime = None
        if self.magic_available:
            try:
                actual_mime = self.magic_detector.from_buffer(file_bytes)
                logger.debug(f"Detected MIME type: {actual_mime} for {filename}")
            except Exception as e:
                logger.error(f"Magic detection failed for {filename}: {e}")
                # Continue with other checks

        # Step 4: Check against blocked MIME types
        if actual_mime and actual_mime in BLOCKED_FILE_TYPES:
            logger.warning(f"Blocked dangerous file type: {actual_mime} in {filename}")
            return False, actual_mime, f"File type '{actual_mime}' is blocked for security reasons"

        # Step 5: Verify claimed MIME matches actual (if both available)
        if actual_mime and claimed_mime:
            claimed_category = claimed_mime.split('/')[0]
            actual_category = actual_mime.split('/')[0]

            # Categories must match (image vs image, video vs video, etc.)
            if claimed_category != actual_category:
                logger.warning(
                    f"MIME type mismatch for {filename}: "
                    f"claimed={claimed_mime}, actual={actual_mime}"
                )
                return False, actual_mime, (
                    f"File type mismatch: claimed '{claimed_mime}' "
                    f"but actual content is '{actual_mime}'"
                )

        # Step 6: Validate against allowed types
        if actual_mime:
            allowed = self._is_mime_allowed(actual_mime)
            if not allowed:
                logger.warning(f"File type not allowed: {actual_mime} in {filename}")
                return False, actual_mime, (
                    f"File type '{actual_mime}' is not allowed. "
                    f"Only images, videos, audio, and documents are permitted."
                )

        # Step 7: Additional checks for potential polyglots
        if actual_mime and actual_mime.startswith('image/'):
            # Check for embedded HTML/scripts in images
            if self._contains_html_tags(file_bytes):
                logger.warning(f"Image contains embedded HTML: {filename}")
                return False, actual_mime, "Image file contains embedded HTML code (potential XSS)"

            if self._contains_script_tags(file_bytes):
                logger.warning(f"Image contains embedded scripts: {filename}")
                return False, actual_mime, "Image file contains embedded script code (potential XSS)"

        # All checks passed
        logger.info(f"File validation passed: {filename} - {actual_mime or claimed_mime}")
        return True, actual_mime or claimed_mime, None

    def _is_mime_allowed(self, mime_type: str) -> bool:
        """Check if MIME type is in allowed list"""
        for category, config in ALLOWED_FILE_TYPES.items():
            if mime_type in config['mime_types']:
                return True

            # Check if it's a valid subtype of allowed category
            mime_category = mime_type.split('/')[0]
            allowed_category = any(
                allowed.split('/')[0] == mime_category
                for allowed in config['mime_types']
            )
            if allowed_category and mime_category in ['image', 'video', 'audio']:
                # Allow image/*, video/*, audio/* even if not explicitly listed
                return True

        return False

    def _contains_html_tags(self, file_bytes: bytes) -> bool:
        """
        Check if file contains HTML tags that could enable XSS.

        Checks first and last 8KB for efficiency (polyglots often at start/end).
        """
        try:
            # Check first 8KB and last 8KB for HTML tags
            check_bytes = file_bytes[:8192]
            if len(file_bytes) > 8192:
                check_bytes += file_bytes[-8192:]

            # Decode as text (ignore errors)
            text = check_bytes.decode('utf-8', errors='ignore').lower()

            # HTML/XSS indicators
            html_indicators = [
                '<script', '<iframe', '<object', '<embed',
                '<html', '<body', '<head',
                'javascript:',
                'onerror=', 'onload=', 'onclick=', 'onmouseover='
            ]

            for indicator in html_indicators:
                if indicator in text:
                    logger.debug(f"Found HTML indicator: {indicator}")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking for HTML tags: {e}")
            return False

    def _contains_script_tags(self, file_bytes: bytes) -> bool:
        """Check if file contains script tags"""
        try:
            check_bytes = file_bytes[:8192]
            if len(file_bytes) > 8192:
                check_bytes += file_bytes[-8192:]

            # Check for script tags in both text and binary form
            return (
                b'<script' in check_bytes.lower() or
                b'javascript:' in check_bytes.lower() or
                b'<iframe' in check_bytes.lower()
            )

        except Exception as e:
            logger.debug(f"Error checking for script tags: {e}")
            return False


# Singleton instance
file_validator = FileValidator()
