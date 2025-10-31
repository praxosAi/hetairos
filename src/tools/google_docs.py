from typing import Optional, List
from langchain_core.tools import tool
from src.integrations.gdrive.google_docs_client import GoogleDocsIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_docs_tools(docs_integration: GoogleDocsIntegration) -> List:
    """Creates all Google Docs related tools, dynamically configured for the user's accounts."""

    @tool
    async def create_google_doc(
        title: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new empty Google Doc.

        Args:
            title: Title of the document
            account: The specific account to use if the user has multiple

        Returns:
            Document ID and URL of the created document
        """
        try:
            result = await docs_integration.create_document(title, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error creating Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="create_google_doc",
                exception=e,
                integration="Google Docs",
                context={"title": title}
            )

    @tool
    async def get_google_doc_content(
        document_id: str,
        plain_text_only: bool = False,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Retrieves the content of a Google Doc.

        Args:
            document_id: ID of the document
            plain_text_only: If True, returns only plain text. If False, returns full document structure
            account: The specific account to use if the user has multiple

        Returns:
            Document content (plain text or full structure)
        """
        try:
            if plain_text_only:
                result = await docs_integration.get_document_text(document_id, account=account)
            else:
                result = await docs_integration.get_document(document_id, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error getting Google Doc content: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_google_doc_content",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id}
            )

    @tool
    async def insert_text_in_doc(
        document_id: str,
        text: str,
        index: int = 1,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts text at a specific position in a Google Doc.

        Args:
            document_id: ID of the document
            text: Text to insert
            index: Character index where to insert (1 = beginning after title, default 1)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of insertion
        """
        try:
            result = await docs_integration.insert_text(document_id, text, index, account=account)
            return ToolExecutionResponse(status="success", result=f"Text inserted at index {index}")
        except Exception as e:
            logger.error(f"Error inserting text in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_text_in_doc",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "index": index}
            )

    @tool
    async def append_text_to_doc(
        document_id: str,
        text: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Appends text to the end of a Google Doc.

        Args:
            document_id: ID of the document
            text: Text to append
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of append
        """
        try:
            result = await docs_integration.append_text(document_id, text, account=account)
            return ToolExecutionResponse(status="success", result="Text appended to document")
        except Exception as e:
            logger.error(f"Error appending text to Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="append_text_to_doc",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id}
            )

    @tool
    async def format_doc_text(
        document_id: str,
        start_index: int,
        end_index: int,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        underline: Optional[bool] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Applies text formatting to a range in a Google Doc.

        Args:
            document_id: ID of the document
            start_index: Start of the range to format
            end_index: End of the range to format
            bold: Whether to make text bold
            italic: Whether to make text italic
            underline: Whether to underline text
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of formatting applied
        """
        try:
            result = await docs_integration.format_text(
                document_id, start_index, end_index,
                bold=bold, italic=italic, underline=underline,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Formatting applied to range {start_index}-{end_index}")
        except Exception as e:
            logger.error(f"Error formatting text in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="format_doc_text",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "range": f"{start_index}-{end_index}"}
            )

    @tool
    async def insert_paragraph_in_doc(
        document_id: str,
        text: str,
        index: int = 1,
        heading_level: Optional[int] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts a paragraph into a Google Doc, optionally as a heading.

        Args:
            document_id: ID of the document
            text: Paragraph text
            index: Character index where to insert (default 1)
            heading_level: If specified, makes the paragraph a heading (1-6, where 1 is the largest)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of paragraph insertion
        """
        try:
            result = await docs_integration.insert_paragraph(
                document_id, text, index,
                heading_level=heading_level,
                account=account
            )
            heading_info = f" as Heading {heading_level}" if heading_level else ""
            return ToolExecutionResponse(status="success", result=f"Paragraph inserted{heading_info}")
        except Exception as e:
            logger.error(f"Error inserting paragraph in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_paragraph_in_doc",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "index": index}
            )

    @tool
    async def insert_table_in_doc(
        document_id: str,
        rows: int,
        columns: int,
        index: int = 1,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts a table into a Google Doc.

        Args:
            document_id: ID of the document
            rows: Number of rows
            columns: Number of columns
            index: Character index where to insert (default 1)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of table insertion
        """
        try:
            result = await docs_integration.insert_table(
                document_id, rows, columns, index,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Inserted {rows}x{columns} table")
        except Exception as e:
            logger.error(f"Error inserting table in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_table_in_doc",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "dimensions": f"{rows}x{columns}"}
            )

    @tool
    async def delete_doc_content(
        document_id: str,
        start_index: int,
        end_index: int,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Deletes content in a specific range of a Google Doc.

        Args:
            document_id: ID of the document
            start_index: Start of the range to delete
            end_index: End of the range to delete
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of deletion
        """
        try:
            result = await docs_integration.delete_content_range(
                document_id, start_index, end_index,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Deleted content range {start_index}-{end_index}")
        except Exception as e:
            logger.error(f"Error deleting content in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_doc_content",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "range": f"{start_index}-{end_index}"}
            )

    @tool
    async def replace_text_in_doc(
        document_id: str,
        find_text: str,
        replace_text: str,
        match_case: bool = True,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Finds and replaces all occurrences of text in a Google Doc.

        Args:
            document_id: ID of the document
            find_text: Text to find
            replace_text: Text to replace with
            match_case: Whether to match case (default True)
            account: The specific account to use if the user has multiple

        Returns:
            Number of replacements made
        """
        try:
            result = await docs_integration.replace_all_text(
                document_id, find_text, replace_text,
                match_case=match_case,
                account=account
            )
            return ToolExecutionResponse(
                status="success",
                result=f"Replaced {result['occurrences_changed']} occurrences of '{find_text}'"
            )
        except Exception as e:
            logger.error(f"Error replacing text in Google Doc: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="replace_text_in_doc",
                exception=e,
                integration="Google Docs",
                context={"document_id": document_id, "find_text": find_text}
            )

    # Dynamic account description logic
    accounts = docs_integration.get_connected_accounts()
    if not accounts:
        return []

    all_tools = [
        create_google_doc,
        get_google_doc_content,
        insert_text_in_doc,
        append_text_to_doc,
        format_doc_text,
        insert_paragraph_in_doc,
        insert_table_in_doc,
        delete_doc_content,
        replace_text_in_doc
    ]

    if len(accounts) == 1:
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected Google account with Docs access is {user_email}."
    else:
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            t.description += (
                f" The user has multiple accounts with Docs access. You MUST use the 'account' parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )

    return all_tools
