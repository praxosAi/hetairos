"""
File Retrieval Tools: Agent tools for finding and accessing previously uploaded files.

These tools enable the agent to:
- Search for files in Praxos memory (using source_id)
- Retrieve files by Praxos source_id and load into conversation
- Access file content for analysis

Key design: Uses Praxos search as the primary discovery mechanism, then
fetches files from MongoDB using source_id for consistency with memory architecture.
"""

from typing import Optional, List
from langchain_core.tools import tool
from src.core.praxos_client import PraxosClient
from src.utils.file_manager import file_manager
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


def create_file_retrieval_tools(
    praxos_client: PraxosClient,
    user_id: str,
    conversation_id: str
) -> list:
    """
    Create file retrieval tools for agent access.

    These tools allow the agent to find and retrieve files that have been
    uploaded in previous conversations.

    Args:
        praxos_client: Praxos client instance
        user_id: User ID for scoping searches
        conversation_id: Current conversation ID for media bus integration

    Returns:
        List of file retrieval tools
    """

    @tool
    async def search_uploaded_files(
        query: str,
        file_type: Optional[str] = None,
        top_k: int = 5
    ) -> ToolExecutionResponse:
        """
        Search for previously uploaded files using Praxos memory search.

        This searches the knowledge graph for files that match your query.
        Files must have been previously uploaded and ingested into Praxos memory.

        Args:
            query: Search query describing the file you're looking for
                   Examples: "contract PDF", "photo from yesterday", "budget spreadsheet"
            file_type: Optional filter by type: 'image', 'video', 'audio', 'document', 'file'
            top_k: Maximum number of results to return (default 5)

        Returns:
            List of matching files with source_id and descriptions

        Usage:
            1. Search for files: search_uploaded_files("contract PDF")
            2. Note the source_id from results
            3. Load file: retrieve_file_by_source_id(source_id)

        Example:
            # Find contract
            files = search_uploaded_files("employment contract")
            # Returns: [{"source_id": "src_123", "description": "employment_contract.pdf", ...}]

            # Load it
            file_data = retrieve_file_by_source_id("src_123")
            # Now you can see the document
        """
        try:
            # Enhance query with file type if specified
            search_query = query
            if file_type:
                search_query = f"{query} {file_type} file document"

            logger.info(f"Searching for files in Praxos: '{search_query}' (type={file_type})")

            # Search Praxos memory for files
            result = await praxos_client.search_memory(
                query=search_query,
                top_k=top_k,
                search_modality="node_vec"
            )

            if not result or 'error' in result:
                return ToolExecutionResponse(
                    status="success",
                    result="No files found matching your query. Try a different search term or check if files have been uploaded."
                )

            source_ids = result.get('source_ids', set())
            sentences = result.get('sentences', [])
            results_data = result.get('results', [])

            if not source_ids:
                return ToolExecutionResponse(
                    status="success",
                    result="No files found matching your query."
                )

            # Get file metadata from MongoDB using source_ids
            from src.utils.database import db_manager

            file_info_list = []
            for source_id in source_ids:
                # Query MongoDB for document with this source_id
                file_doc = await db_manager.documents.find_one({"source_id": source_id})

                if file_doc:
                    # Filter by file type if specified
                    if file_type and file_doc.get('type') != file_type:
                        continue

                    file_info = {
                        "source_id": source_id,
                        "file_name": file_doc.get("file_name", "unknown"),
                        "file_type": file_doc.get("type", "file"),
                        "mime_type": file_doc.get("mime_type"),
                        "platform": file_doc.get("platform", "unknown"),
                        "uploaded_at": file_doc.get("created_at"),
                        "caption": file_doc.get("caption", ""),
                        "size": file_doc.get("size", 0)
                    }
                    file_info_list.append(file_info)

            if not file_info_list:
                return ToolExecutionResponse(
                    status="success",
                    result=f"Search found {len(source_ids)} sources, but no matching files in the database. Files may not have been ingested yet."
                )

            # Format results
            result_text = f"Found {len(file_info_list)} file(s) matching '{query}':\n\n"

            for i, file_info in enumerate(file_info_list, 1):
                result_text += f"{i}. {file_info['file_name']} ({file_info['file_type']})\n"
                result_text += f"   Source ID: {file_info['source_id']}\n"
                result_text += f"   Platform: {file_info['platform']}\n"
                result_text += f"   Size: {file_info['size']} bytes\n"
                if file_info['caption']:
                    result_text += f"   Caption: {file_info['caption']}\n"
                if file_info['uploaded_at']:
                    result_text += f"   Uploaded: {file_info['uploaded_at']}\n"
                result_text += f"\n   Use retrieve_file_by_source_id('{file_info['source_id']}') to load this file\n"
                if i < len(file_info_list):
                    result_text += "\n"

            logger.info(f"Found {len(file_info_list)} files for query: {query}")

            return ToolExecutionResponse(
                status="success",
                result=result_text
            )

        except Exception as e:
            logger.error(f"Error searching files: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="search_uploaded_files",
                exception=e,
                integration="file_retrieval"
            )

    @tool
    async def retrieve_file_by_source_id(source_id: str) -> ToolExecutionResponse:
        """
        Retrieve a file by its Praxos source_id and load it into conversation context.

        This tool:
        1. Looks up the file in MongoDB using the Praxos source_id
        2. Downloads the file content
        3. Adds it to the current conversation's media bus
        4. Makes the file visible to you in the conversation

        After calling this tool, you'll be able to see and analyze the file content.

        Args:
            source_id: The Praxos source_id (from search_uploaded_files results)

        Returns:
            File metadata and confirmation that it's loaded into context

        Important:
            - Source ID comes from Praxos search or ingestion results
            - File will be loaded into conversation for analysis
            - For images, you'll see the image visually
            - For documents, you can analyze the content

        Usage:
            1. Search: search_uploaded_files("contract PDF")
            2. Get source_id from results
            3. Load: retrieve_file_by_source_id("src_abc123")
            4. Now you can see and analyze the file

        Example:
            # After searching and finding a contract with source_id="src_abc123"
            file = retrieve_file_by_source_id("src_abc123")
            # Now you can see the PDF and answer questions about it
        """
        try:
            logger.info(f"Retrieving file by source_id: {source_id}")

            # Query MongoDB for document with this source_id
            from src.utils.database import db_manager
            file_doc = await db_manager.documents.find_one({"source_id": source_id})

            if not file_doc:
                return ToolExecutionResponse(
                    status="error",
                    result=f"File not found with source_id: {source_id}. The file may not have been ingested to Praxos yet."
                )

            # Get inserted_id from document
            inserted_id = str(file_doc.get("_id"))

            # Use FileManager to build payload and get FileResult
            payload, file_result = await file_manager.build_payload_from_id(
                inserted_id=inserted_id,
                conversation_id=conversation_id,
                add_to_media_bus=True  # Add to media bus for agent access
            )

            if not payload or not file_result:
                return ToolExecutionResponse(
                    status="error",
                    result=f"Failed to load file with source_id: {source_id}"
                )

            # Add to conversation history so agent can see it
            from src.services.conversation_manager import ConversationManager
            from src.services.integration_service import integration_service
            from src.utils.database import conversation_db

            conversation_manager = ConversationManager(conversation_db, integration_service)
            await conversation_manager.add_assistant_message(
                user_id,
                conversation_id,
                f"[Retrieved file from Praxos memory] {file_result.file_name} ({file_result.file_type})",
                metadata={
                    "source_id": source_id,
                    "inserted_id": inserted_id,
                    "file_type": file_result.file_type,
                    "action": "file_retrieval_from_praxos"
                }
            )

            logger.info(f"Loaded file into conversation: {file_result.file_name} (source_id={source_id})")

            result_text = f"✅ File loaded into conversation:\n\n"
            result_text += f"File: {file_result.file_name}\n"
            result_text += f"Type: {file_result.file_type}\n"
            result_text += f"Size: {file_result.size} bytes\n"
            result_text += f"Platform: {file_result.platform}\n"
            if file_result.caption:
                result_text += f"Caption: {file_result.caption}\n"
            if file_result.created_at:
                result_text += f"Uploaded: {file_result.created_at}\n"
            result_text += f"\nThe file is now loaded in conversation context. You can see and analyze its content."

            return ToolExecutionResponse(
                status="success",
                result=result_text
            )

        except Exception as e:
            logger.error(f"Error retrieving file by source_id {source_id}: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="retrieve_file_by_source_id",
                exception=e,
                integration="file_retrieval"
            )

    @tool
    async def list_recent_uploaded_files(
        file_type: Optional[str] = None,
        limit: int = 10
    ) -> ToolExecutionResponse:
        """
        List the user's most recently uploaded files across all platforms.

        This provides a quick overview of recently uploaded files without
        requiring a Praxos search. Useful for seeing what files are available.

        Args:
            file_type: Optional filter - 'image', 'video', 'audio', 'document', 'file'
            limit: Maximum number of files to return (default 10, max 50)

        Returns:
            List of recent files with metadata

        Usage:
            # See all recent files
            list_recent_uploaded_files()

            # See only documents
            list_recent_uploaded_files(file_type='document')

        Note:
            - This shows files from MongoDB directly (not just those in Praxos)
            - Files are ordered by upload time (newest first)
            - Use retrieve_file_by_source_id() to load a specific file
        """
        try:
            limit = max(1, min(limit, 50))  # Clamp between 1 and 50

            logger.info(f"Listing recent files for user {user_id} (type={file_type}, limit={limit})")

            # Get files from MongoDB
            file_results = await file_manager.get_files_by_user(
                user_id=user_id,
                file_type=file_type,
                limit=limit
            )

            if not file_results:
                type_msg = f" of type '{file_type}'" if file_type else ""
                return ToolExecutionResponse(
                    status="success",
                    result=f"No files{type_msg} found for this user."
                )

            # Format results
            result_text = f"Recent uploaded files ({len(file_results)}):\n\n"

            for i, file_res in enumerate(file_results, 1):
                result_text += f"{i}. {file_res.file_name} ({file_res.file_type})\n"
                result_text += f"   Platform: {file_res.platform}\n"
                result_text += f"   Size: {file_res.size} bytes\n"

                if file_res.caption:
                    result_text += f"   Caption: {file_res.caption}\n"

                # Show how to retrieve
                if hasattr(file_res, 'metadata') and file_res.metadata.get('source_id'):
                    source_id = file_res.metadata['source_id']
                    result_text += f"   Source ID: {source_id}\n"
                    result_text += f"   Use: retrieve_file_by_source_id('{source_id}')\n"
                else:
                    result_text += f"   ⚠️  Not yet ingested to Praxos (no source_id)\n"

                if file_res.created_at:
                    result_text += f"   Uploaded: {file_res.created_at}\n"

                if i < len(file_results):
                    result_text += "\n"

            logger.info(f"Listed {len(file_results)} files for user {user_id}")

            return ToolExecutionResponse(
                status="success",
                result=result_text
            )

        except Exception as e:
            logger.error(f"Error listing recent files: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="list_recent_uploaded_files",
                exception=e,
                integration="file_retrieval"
            )

    logger.info(f"Created file retrieval tools for conversation {conversation_id}")
    return [search_uploaded_files, retrieve_file_by_source_id, list_recent_uploaded_files]
