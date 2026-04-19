"""
File proxy tool: rehost third-party authenticated files to blob storage.

Some cloud-storage URLs (Google Drive, Dropbox, etc.) are only reachable by the
user's OAuth token — they cannot be handed to the mobile/web client directly or
forwarded via messaging platforms. This tool fetches the file bytes using the
already-authenticated integration client and uploads them to Azure Blob Storage,
returning a SAS URL the agent can pass to `attach_file_to_response`.
"""

import mimetypes
import uuid
from typing import List, Optional

from langchain_core.tools import tool

from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.integrations.dropbox.dropbox_client import DropboxIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.blob_utils import upload_bytes_to_blob_storage, get_blob_sas_url
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".heif"}
_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus"}
_VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".csv", ".txt", ".md", ".json", ".html", ".rtf"}


def _classify_file_type(file_name: str, mime_type: Optional[str]) -> str:
    name = (file_name or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""

    if ext in _IMAGE_EXT:
        return "image"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _DOC_EXT:
        return "document"

    if mime_type:
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith(("application/", "text/")):
            return "document"

    return "other_file"


def create_file_proxy_tools(
    gdrive_integration: Optional[GoogleDriveIntegration] = None,
    dropbox_integration: Optional[DropboxIntegration] = None,
    tool_registry=None,
) -> List:
    """Build the upload_third_party_file_to_blob tool bound to the authenticated integrations."""

    @tool
    async def upload_third_party_file_to_blob(
        integration: str,
        file_identifier: str,
        file_name: str,
        account: Optional[str] = None,
    ) -> ToolExecutionResponse:
        """Fetch a file from a user's connected cloud storage and rehost it on blob storage.

        Returns a public (SAS-signed) URL suitable for `attach_file_to_response`. Use this
        whenever a user asks you to send them a file stored in Google Drive, Dropbox, or
        similar — raw share URLs from those services require the user's OAuth token and
        will not work when forwarded to WhatsApp, mypraxos-mobile, or other clients.

        Args:
            integration: Which cloud storage to fetch from. One of "google_drive", "dropbox".
            file_identifier: Source-specific identifier. For Google Drive this is the file_id.
                For Dropbox this is the file path (e.g. "/Reports/Q3.pdf").
            file_name: Filename to use on the rehosted blob and in the delivered attachment.
            account: Optional account selector when the user has multiple accounts for the
                integration. Omit if only one account is connected.

        Returns:
            ToolExecutionResponse with result dict: {url, file_type, file_name, mime_type}.
            Pass `url`, `file_type`, `file_name` straight into attach_file_to_response.
        """
        try:
            integ_key = (integration or "").lower().strip()
            file_bytes: Optional[bytes] = None
            resolved_mime: Optional[str] = None
            effective_name = file_name

            if integ_key in {"google_drive", "gdrive", "drive"}:
                if not gdrive_integration:
                    raise Exception("Google Drive integration is not connected for this user")
                result = await gdrive_integration.download_or_export_file(
                    file_identifier, account=account
                )
                if result is None:
                    raise Exception(
                        "Could not download file from Google Drive "
                        "(file missing, unsupported native type, or permission denied)"
                    )
                file_bytes, resolved_mime, suggested_ext = result
                # If Drive exported a native Doc/Sheet/Slide/Drawing, the bytes are in
                # a different format than the agent-supplied filename implies. Append
                # the correct extension so the delivered attachment opens correctly.
                if suggested_ext and not effective_name.lower().endswith(suggested_ext):
                    effective_name = effective_name + suggested_ext
            elif integ_key in {"dropbox"}:
                if not dropbox_integration:
                    raise Exception("Dropbox integration is not connected for this user")
                file_bytes = await dropbox_integration.read_file(file_identifier, account=account)
            else:
                raise Exception(
                    f"Unsupported integration '{integration}'. Supported: google_drive, dropbox"
                )

            if not file_bytes:
                raise Exception(f"Fetched empty file bytes for {file_name}")

            if not resolved_mime:
                guessed, _ = mimetypes.guess_type(effective_name)
                resolved_mime = guessed or "application/octet-stream"
            mime_type = resolved_mime
            safe_name = effective_name.replace("/", "_").replace("\\", "_")
            blob_name = f"proxied_files/{uuid.uuid4().hex}_{safe_name}"

            await upload_bytes_to_blob_storage(file_bytes, blob_name, content_type=mime_type)
            sas_url = await get_blob_sas_url(blob_name)

            file_type = _classify_file_type(effective_name, mime_type)

            logger.info(
                f"Rehosted {integ_key} file '{effective_name}' "
                f"({len(file_bytes)} bytes, {mime_type}) to blob {blob_name}"
            )

            return ToolExecutionResponse(
                status="success",
                result={
                    "url": sas_url,
                    "file_type": file_type,
                    "file_name": effective_name,
                    "mime_type": mime_type,
                    "message": (
                        "File rehosted on blob storage. Call attach_file_to_response with "
                        "this url, file_type, and file_name to deliver it to the user."
                    ),
                },
            )

        except Exception as e:
            logger.error(
                f"upload_third_party_file_to_blob failed ({integration}/{file_name}): {e}",
                exc_info=True,
            )
            return ErrorResponseBuilder.from_exception(
                operation="upload_third_party_file_to_blob",
                exception=e,
                integration=integration,
                context={"file_identifier": file_identifier, "file_name": file_name},
            )

    tools = [upload_third_party_file_to_blob]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(tools)
    return tools
