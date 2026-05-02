"""
Archive Tools: agent tool for inspecting and extracting ZIP archives that the
user has uploaded.

Given a previously uploaded zip (referenced by its MongoDB inserted_id), the
tool can either list its contents or extract selected entries. Extracted
entries are re-ingested through the regular file pipeline so they get their
own inserted_id and become first-class files (retrievable, ingestible to
Praxos, attachable to replies, etc.).
"""

import io
import os
import zipfile
from typing import List, Optional

from langchain_core.tools import tool

from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.blob_utils import download_from_blob_storage
from src.utils.file_manager import file_manager
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

_MAX_ENTRIES_LISTED = 200
_MAX_EXTRACT_ENTRIES = 25
_MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024  # 200 MB ceiling, zip-bomb guard
_MAX_PER_ENTRY_UNCOMPRESSED = 50 * 1024 * 1024  # 50 MB per file


def _is_safe_entry_name(name: str) -> bool:
    """Reject path-traversal / absolute paths (zip slip)."""
    if not name or name.endswith("/"):
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    norm = os.path.normpath(name)
    if norm.startswith("..") or os.path.isabs(norm):
        return False
    parts = norm.replace("\\", "/").split("/")
    return ".." not in parts


def create_archive_tools(
    user_id: str,
    conversation_id: Optional[str],
    tool_registry=None,
) -> list:
    """Build the extract_archive_contents tool bound to the current user/conversation."""

    @tool
    async def extract_archive_contents(
        inserted_id: str,
        entries: Optional[List[str]] = None,
    ) -> ToolExecutionResponse:
        """Inspect or extract the contents of a previously uploaded ZIP file.

        Args:
            inserted_id: MongoDB inserted_id of the uploaded archive (from
                list_recent_uploaded_files or similar).
            entries: Names of entries to extract. If omitted or empty, the tool
                only lists the archive contents and extracts nothing. Pass the
                literal string "all" to extract everything (subject to safety
                caps).

        Returns:
            On listing: each entry's name, uncompressed size, and a flag for
            whether it would be safe to extract.
            On extraction: for each extracted entry, the new inserted_id,
            file_name, file_type, and size — usable with the regular file
            retrieval / attachment tools.
        """
        try:
            if not inserted_id or not inserted_id.strip():
                return ErrorResponseBuilder.invalid_parameter(
                    operation="extract_archive_contents",
                    param_name="inserted_id",
                    param_value=inserted_id,
                    expected_format="Non-empty MongoDB inserted_id string",
                )

            file_result = await file_manager.get_file_by_id(inserted_id)
            if not file_result:
                return ErrorResponseBuilder.not_found(
                    operation="extract_archive_contents",
                    resource_type="file",
                    resource_id=inserted_id,
                    technical_details="No file document found for this inserted_id.",
                )

            try:
                archive_bytes = await download_from_blob_storage(
                    file_result.blob_path,
                    container_name=file_result.container_name,
                )
            except Exception as e:
                logger.error(f"Failed to download archive {inserted_id} from blob: {e}", exc_info=True)
                return ErrorResponseBuilder.file_error(
                    operation="extract_archive_contents",
                    error_type="download_failed",
                    file_name=file_result.file_name,
                    technical_details=f"Could not download archive bytes: {e}",
                )

            if not zipfile.is_zipfile(io.BytesIO(archive_bytes)):
                return ErrorResponseBuilder.invalid_parameter(
                    operation="extract_archive_contents",
                    param_name="inserted_id",
                    param_value=inserted_id,
                    expected_format=(
                        f"File '{file_result.file_name}' is not a valid ZIP archive"
                    ),
                )

            try:
                zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
            except zipfile.BadZipFile as e:
                return ErrorResponseBuilder.file_error(
                    operation="extract_archive_contents",
                    error_type="invalid_file",
                    file_name=file_result.file_name,
                    technical_details=f"Archive is corrupted: {e}",
                )

            with zf:
                infos = [info for info in zf.infolist() if not info.is_dir()]
                listing = []
                total_uncompressed = 0
                for info in infos[:_MAX_ENTRIES_LISTED]:
                    safe = _is_safe_entry_name(info.filename)
                    listing.append({
                        "name": info.filename,
                        "size": info.file_size,
                        "extractable": safe and info.file_size <= _MAX_PER_ENTRY_UNCOMPRESSED,
                    })
                    total_uncompressed += info.file_size

                if not entries:
                    return ToolExecutionResponse(
                        status="success",
                        result={
                            "archive_name": file_result.file_name,
                            "entry_count": len(infos),
                            "shown": len(listing),
                            "total_uncompressed_size": total_uncompressed,
                            "entries": listing,
                            "message": (
                                "Listing only — pass `entries=[...]` (or 'all') to extract."
                            ),
                        },
                    )

                if isinstance(entries, str):
                    requested = [info.filename for info in infos] if entries.lower() == "all" else [entries]
                else:
                    requested = list(entries)

                if len(requested) > _MAX_EXTRACT_ENTRIES:
                    return ErrorResponseBuilder.invalid_parameter(
                        operation="extract_archive_contents",
                        param_name="entries",
                        param_value=f"{len(requested)} entries",
                        expected_format=f"At most {_MAX_EXTRACT_ENTRIES} entries per call",
                    )

                info_by_name = {info.filename: info for info in infos}
                extracted = []
                skipped = []
                running_total = 0

                for name in requested:
                    info = info_by_name.get(name)
                    if info is None:
                        skipped.append({"name": name, "reason": "not_found"})
                        continue
                    if not _is_safe_entry_name(info.filename):
                        skipped.append({"name": name, "reason": "unsafe_path"})
                        continue
                    if info.file_size > _MAX_PER_ENTRY_UNCOMPRESSED:
                        skipped.append({"name": name, "reason": "too_large"})
                        continue
                    if running_total + info.file_size > _MAX_TOTAL_UNCOMPRESSED:
                        skipped.append({"name": name, "reason": "total_size_exceeded"})
                        continue

                    try:
                        with zf.open(info) as src:
                            entry_bytes = src.read()
                    except Exception as e:
                        logger.warning(f"Failed to read zip entry '{name}': {e}")
                        skipped.append({"name": name, "reason": f"read_error: {e}"})
                        continue

                    running_total += len(entry_bytes)
                    leaf = os.path.basename(info.filename) or info.filename

                    try:
                        new_file = await file_manager.receive_file(
                            user_id=user_id,
                            platform=file_result.platform or "import_file_upload",
                            file_bytes=entry_bytes,
                            filename=leaf,
                            caption=f"Extracted from {file_result.file_name}",
                            metadata={
                                "extracted_from_inserted_id": inserted_id,
                                "extracted_from_archive": file_result.file_name,
                                "archive_entry_path": info.filename,
                            },
                            conversation_id=conversation_id,
                            auto_add_to_media_bus=bool(conversation_id),
                            auto_cleanup=False,
                        )
                    except ValueError as e:
                        skipped.append({"name": name, "reason": f"rejected: {e}"})
                        continue
                    except Exception as e:
                        logger.error(f"Failed to ingest extracted entry '{name}': {e}", exc_info=True)
                        skipped.append({"name": name, "reason": f"ingest_error: {e}"})
                        continue

                    extracted.append({
                        "inserted_id": new_file.inserted_id,
                        "file_name": new_file.file_name,
                        "file_type": new_file.file_type,
                        "mime_type": new_file.mime_type,
                        "size": new_file.size,
                        "archive_entry_path": info.filename,
                    })

                logger.info(
                    f"extract_archive_contents: archive={file_result.file_name} "
                    f"extracted={len(extracted)} skipped={len(skipped)}"
                )

                return ToolExecutionResponse(
                    status="success",
                    result={
                        "archive_name": file_result.file_name,
                        "extracted": extracted,
                        "skipped": skipped,
                        "message": (
                            f"Extracted {len(extracted)} file(s) from archive. "
                            "Each is now a regular uploaded file you can attach, "
                            "retrieve, or ingest."
                        ),
                    },
                )

        except Exception as e:
            logger.error(f"extract_archive_contents failed for {inserted_id}: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="extract_archive_contents",
                exception=e,
                integration="archive",
                context={"inserted_id": inserted_id},
            )

    tools = [extract_archive_contents]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(tools)
    return tools
