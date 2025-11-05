from typing import Optional, List
from langchain_core.tools import tool
from src.integrations.gdrive.google_slides_client import GoogleSlidesIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_slides_tools(slides_integration: GoogleSlidesIntegration, tool_registry) -> List:
    """Creates all Google Slides related tools, dynamically configured for the user's accounts."""

    @tool
    async def create_google_presentation(
        title: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new Google Slides presentation.

        Args:
            title: Title of the presentation
            account: The specific account to use if the user has multiple

        Returns:
            Presentation ID and URL of the created presentation
        """
        try:
            result = await slides_integration.create_presentation(title, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error creating Google Slides presentation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="create_google_presentation",
                exception=e,
                integration="Google Slides",
                context={"title": title}
            )

    @tool
    async def get_presentation_info(
        presentation_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Gets metadata and structure of a Google Slides presentation.
        Use this to get slide IDs and other properties.

        Args:
            presentation_id: ID of the presentation
            account: The specific account to use if the user has multiple

        Returns:
            Complete presentation metadata including slide information
        """
        try:
            result = await slides_integration.get_presentation(presentation_id, account=account)
            # Extract useful info
            slides_info = [
                {
                    'slide_id': slide['objectId'],
                    'layout': slide.get('slideProperties', {}).get('layoutObjectId', 'unknown')
                }
                for slide in result.get('slides', [])
            ]
            simplified_result = {
                'presentation_id': result['presentationId'],
                'title': result['title'],
                'slides': slides_info,
                'slide_count': len(slides_info)
            }
            return ToolExecutionResponse(status="success", result=simplified_result)
        except Exception as e:
            logger.error(f"Error getting presentation info: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_presentation_info",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id}
            )

    @tool
    async def add_slide(
        presentation_id: str,
        insertion_index: Optional[int] = None,
        layout: str = 'BLANK',
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Adds a new slide to a Google Slides presentation.

        Args:
            presentation_id: ID of the presentation
            insertion_index: Position to insert slide (None = end of presentation)
            layout: Layout type - BLANK, TITLE_AND_BODY, TITLE_ONLY, etc. (default BLANK)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of slide creation with slide ID
        """
        try:
            result = await slides_integration.create_slide(
                presentation_id, insertion_index, layout,
                account=account
            )
            slide_id = result['replies'][0]['createSlide']['objectId']
            return ToolExecutionResponse(
                status="success",
                result=f"Added slide with ID: {slide_id}"
            )
        except Exception as e:
            logger.error(f"Error adding slide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="add_slide",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id}
            )

    @tool
    async def delete_slide(
        presentation_id: str,
        slide_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Deletes a slide from a Google Slides presentation.

        Args:
            presentation_id: ID of the presentation
            slide_id: Object ID of the slide to delete (get from get_presentation_info)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of deletion
        """
        try:
            result = await slides_integration.delete_slide(presentation_id, slide_id, account=account)
            return ToolExecutionResponse(status="success", result=f"Deleted slide {slide_id}")
        except Exception as e:
            logger.error(f"Error deleting slide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_slide",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "slide_id": slide_id}
            )

    @tool
    async def insert_text_in_slide(
        presentation_id: str,
        slide_id: str,
        text: str,
        x: float = 100,
        y: float = 100,
        width: float = 400,
        height: float = 100,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts a text box with text into a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            text: Text to insert
            x: X position in points (default 100)
            y: Y position in points (default 100)
            width: Width in points (default 400)
            height: Height in points (default 100)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of text insertion
        """
        try:
            result = await slides_integration.insert_text(
                presentation_id, slide_id, text,
                x, y, width, height,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Inserted text box in slide {slide_id}")
        except Exception as e:
            logger.error(f"Error inserting text in slide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_text_in_slide",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "slide_id": slide_id}
            )

    @tool
    async def insert_image_in_slide(
        presentation_id: str,
        slide_id: str,
        image_url: str,
        x: float = 100,
        y: float = 100,
        width: float = 300,
        height: float = 300,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts an image into a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the image (must be publicly accessible)
            x: X position in points (default 100)
            y: Y position in points (default 100)
            width: Width in points (default 300)
            height: Height in points (default 300)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of image insertion
        """
        try:
            result = await slides_integration.insert_image(
                presentation_id, slide_id, image_url,
                x, y, width, height,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Inserted image in slide {slide_id}")
        except Exception as e:
            logger.error(f"Error inserting image in slide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_image_in_slide",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "slide_id": slide_id}
            )

    @tool
    async def format_slide_text(
        presentation_id: str,
        object_id: str,
        start_index: int,
        end_index: int,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        font_size: Optional[int] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Applies text formatting to a text box or shape in a slide.

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the text box or shape (get from presentation structure)
            start_index: Start character index (0-based)
            end_index: End character index
            bold: Whether to make text bold
            italic: Whether to make text italic
            font_size: Font size in points
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of formatting applied
        """
        try:
            result = await slides_integration.update_text_style(
                presentation_id, object_id, start_index, end_index,
                bold=bold, italic=italic, font_size=font_size,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Applied formatting to text in object {object_id}")
        except Exception as e:
            logger.error(f"Error formatting slide text: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="format_slide_text",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "object_id": object_id}
            )

    @tool
    async def create_table_in_slide(
        presentation_id: str,
        slide_id: str,
        rows: int,
        columns: int,
        x: float = 100,
        y: float = 100,
        width: float = 400,
        height: float = 200,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a table in a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            rows: Number of rows
            columns: Number of columns
            x: X position in points (default 100)
            y: Y position in points (default 100)
            width: Width in points (default 400)
            height: Height in points (default 200)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of table creation
        """
        try:
            result = await slides_integration.create_table(
                presentation_id, slide_id, rows, columns,
                x, y, width, height,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Created {rows}x{columns} table in slide {slide_id}")
        except Exception as e:
            logger.error(f"Error creating table in slide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="create_table_in_slide",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "slide_id": slide_id}
            )

    @tool
    async def delete_slide_object(
        presentation_id: str,
        object_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Deletes an object (text box, image, shape, table, etc.) from a slide.

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the object to delete
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of deletion
        """
        try:
            result = await slides_integration.delete_object(presentation_id, object_id, account=account)
            return ToolExecutionResponse(status="success", result=f"Deleted object {object_id}")
        except Exception as e:
            logger.error(f"Error deleting slide object: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_slide_object",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "object_id": object_id}
            )

    @tool
    async def search_google_presentation(
        presentation_id: str,
        search_text: str,
        match_case: bool = False,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Searches for text within a Google Slides presentation and returns all matching slides.

        Args:
            presentation_id: ID of the presentation
            search_text: Text to search for
            match_case: Whether to match case (default False for case-insensitive)
            account: The specific account to use if the user has multiple

        Returns:
            Dict with number of slides containing matches and detailed match information
        """
        try:
            result = await slides_integration.search_in_presentation(
                presentation_id, search_text,
                match_case=match_case,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error searching Google Slides presentation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="search_google_presentation",
                exception=e,
                integration="Google Slides",
                context={"presentation_id": presentation_id, "search_text": search_text}
            )

    # Tool registry is passed in and already loaded

    accounts = slides_integration.get_connected_accounts()
    if not accounts:
        return []

    all_tools = [
        create_google_presentation,
        get_presentation_info,
        add_slide,
        delete_slide,
        insert_text_in_slide,
        insert_image_in_slide,
        format_slide_text,
        create_table_in_slide,
        delete_slide_object,
        search_google_presentation
    ]

    # Apply descriptions from YAML database
    tool_registry.apply_descriptions_to_tools(all_tools, accounts=accounts)

    return all_tools
