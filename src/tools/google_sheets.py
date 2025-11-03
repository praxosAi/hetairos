from typing import Optional, List, Any, Dict
from langchain_core.tools import tool
from src.integrations.gdrive.google_sheets_client import GoogleSheetsIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_sheets_tools(sheets_integration: GoogleSheetsIntegration) -> List:
    """Creates all Google Sheets related tools, dynamically configured for the user's accounts."""

    @tool
    async def create_google_sheet(
        title: str,
        sheet_names: Optional[List[str]] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new Google Spreadsheet.

        Args:
            title: Title of the spreadsheet
            sheet_names: Optional list of sheet names (default is one sheet named 'Sheet1')
            account: The specific account to use if the user has multiple

        Returns:
            Spreadsheet ID and URL of the created spreadsheet
        """
        try:
            result = await sheets_integration.create_spreadsheet(title, sheet_names, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error creating Google Sheet: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="create_google_sheet",
                exception=e,
                integration="Google Sheets",
                context={"title": title}
            )

    @tool
    async def get_sheet_values(
        spreadsheet_id: str,
        range_name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Gets cell values from a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range (e.g., 'Sheet1!A1:D10' or 'Sheet1!A:D')
            account: The specific account to use if the user has multiple

        Returns:
            2D list of cell values
        """
        try:
            result = await sheets_integration.get_values(spreadsheet_id, range_name, account=account)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error getting sheet values: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_sheet_values",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    @tool
    async def update_sheet_values(
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Updates cell values in a Google Sheet. Use this to write data to specific cells.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range where to start writing (e.g., 'Sheet1!A1')
            values: 2D list of values to write (e.g., [['Name', 'Age'], ['Alice', 30], ['Bob', 25]])
            account: The specific account to use if the user has multiple

        Returns:
            Number of cells updated
        """
        try:
            result = await sheets_integration.update_values(
                spreadsheet_id, range_name, values,
                value_input_option='USER_ENTERED',
                account=account
            )
            return ToolExecutionResponse(
                status="success",
                result=f"Updated {result.get('updatedCells', 0)} cells in {range_name}"
            )
        except Exception as e:
            logger.error(f"Error updating sheet values: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="update_sheet_values",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    @tool
    async def append_sheet_rows(
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Appends rows to the end of a Google Sheet. Use this to add new data without overwriting.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range to append to (e.g., 'Sheet1!A:D')
            values: 2D list of rows to append (e.g., [['Alice', 30], ['Bob', 25]])
            account: The specific account to use if the user has multiple

        Returns:
            Range where data was appended and number of cells updated
        """
        try:
            result = await sheets_integration.append_values(
                spreadsheet_id, range_name, values,
                value_input_option='USER_ENTERED',
                account=account
            )
            return ToolExecutionResponse(
                status="success",
                result=f"Appended {len(values)} rows to {result.get('updates', {}).get('updatedRange', range_name)}"
            )
        except Exception as e:
            logger.error(f"Error appending to sheet: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="append_sheet_rows",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    @tool
    async def clear_sheet_range(
        spreadsheet_id: str,
        range_name: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Clears values from a range in a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range to clear (e.g., 'Sheet1!A1:D10')
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of cleared range
        """
        try:
            result = await sheets_integration.clear_values(spreadsheet_id, range_name, account=account)
            return ToolExecutionResponse(status="success", result=f"Cleared range {range_name}")
        except Exception as e:
            logger.error(f"Error clearing sheet range: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="clear_sheet_range",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    @tool
    async def get_single_cell(
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        column: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Gets the value of a single cell in a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_name: Name of the sheet (e.g., 'Sheet1')
            row: Row number (1-based, e.g., 1 for first row)
            column: Column letter (e.g., 'A', 'B', 'AA')
            account: The specific account to use if the user has multiple

        Returns:
            Value of the cell
        """
        try:
            result = await sheets_integration.get_cell_value(
                spreadsheet_id, sheet_name, row, column,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error getting cell value: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_single_cell",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "cell": f"{sheet_name}!{column}{row}"}
            )

    @tool
    async def set_single_cell(
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        column: str,
        value: Any,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Sets the value of a single cell in a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_name: Name of the sheet (e.g., 'Sheet1')
            row: Row number (1-based)
            column: Column letter (e.g., 'A', 'B')
            value: Value to set (can be text, number, or formula like '=SUM(A1:A10)')
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of update
        """
        try:
            result = await sheets_integration.set_cell_value(
                spreadsheet_id, sheet_name, row, column, value,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Set cell {column}{row} to '{value}'")
        except Exception as e:
            logger.error(f"Error setting cell value: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="set_single_cell",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "cell": f"{sheet_name}!{column}{row}"}
            )

    @tool
    async def add_sheet_tab(
        spreadsheet_id: str,
        sheet_title: str,
        rows: int = 1000,
        columns: int = 26,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Adds a new sheet tab to an existing Google Spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_title: Title for the new sheet
            rows: Number of rows (default 1000)
            columns: Number of columns (default 26)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of sheet addition
        """
        try:
            result = await sheets_integration.add_sheet(
                spreadsheet_id, sheet_title, rows, columns,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Added sheet '{sheet_title}'")
        except Exception as e:
            logger.error(f"Error adding sheet: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="add_sheet_tab",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "sheet_title": sheet_title}
            )

    @tool
    async def delete_sheet_tab(
        spreadsheet_id: str,
        sheet_id: int,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Deletes a sheet tab from a Google Spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: Numeric ID of the sheet to delete (not the title). Get this from get_spreadsheet_info.
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of deletion
        """
        try:
            result = await sheets_integration.delete_sheet(spreadsheet_id, sheet_id, account=account)
            return ToolExecutionResponse(status="success", result=f"Deleted sheet ID {sheet_id}")
        except Exception as e:
            logger.error(f"Error deleting sheet: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_sheet_tab",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id}
            )

    @tool
    async def insert_sheet_rows(
        spreadsheet_id: str,
        sheet_id: int,
        start_index: int,
        count: int,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts empty rows into a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: Numeric ID of the sheet (get from get_spreadsheet_info)
            start_index: Row index where to insert (0-based, e.g., 0 for first row)
            count: Number of rows to insert
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of insertion
        """
        try:
            result = await sheets_integration.insert_rows(
                spreadsheet_id, sheet_id, start_index, count,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Inserted {count} rows at index {start_index}")
        except Exception as e:
            logger.error(f"Error inserting rows: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_sheet_rows",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id}
            )

    @tool
    async def insert_sheet_columns(
        spreadsheet_id: str,
        sheet_id: int,
        start_index: int,
        count: int,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Inserts empty columns into a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: Numeric ID of the sheet
            start_index: Column index where to insert (0-based, e.g., 0 for column A)
            count: Number of columns to insert
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of insertion
        """
        try:
            result = await sheets_integration.insert_columns(
                spreadsheet_id, sheet_id, start_index, count,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Inserted {count} columns at index {start_index}")
        except Exception as e:
            logger.error(f"Error inserting columns: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="insert_sheet_columns",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id}
            )

    @tool
    async def delete_sheet_rows(
        spreadsheet_id: str,
        sheet_id: int,
        start_index: int,
        end_index: int,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Deletes rows from a Google Sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: Numeric ID of the sheet
            start_index: Starting row index (0-based, inclusive)
            end_index: Ending row index (exclusive, e.g., to delete rows 1-3, use start=0, end=3)
            account: The specific account to use if the user has multiple

        Returns:
            Confirmation of deletion
        """
        try:
            result = await sheets_integration.delete_rows(
                spreadsheet_id, sheet_id, start_index, end_index,
                account=account
            )
            return ToolExecutionResponse(status="success", result=f"Deleted rows {start_index} to {end_index-1}")
        except Exception as e:
            logger.error(f"Error deleting rows: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_sheet_rows",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id}
            )

    @tool
    async def get_spreadsheet_info(
        spreadsheet_id: str,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Gets metadata and structure information about a Google Spreadsheet.
        Use this to get sheet IDs, names, and other properties.

        Args:
            spreadsheet_id: ID of the spreadsheet
            account: The specific account to use if the user has multiple

        Returns:
            Complete spreadsheet metadata including sheet IDs and names
        """
        try:
            result = await sheets_integration.get_spreadsheet(spreadsheet_id, account=account)
            # Extract useful info
            sheets_info = [
                {
                    'title': sheet['properties']['title'],
                    'sheet_id': sheet['properties']['sheetId'],
                    'index': sheet['properties']['index']
                }
                for sheet in result.get('sheets', [])
            ]
            simplified_result = {
                'spreadsheet_id': result['spreadsheetId'],
                'title': result['properties']['title'],
                'url': result['spreadsheetUrl'],
                'sheets': sheets_info
            }
            return ToolExecutionResponse(status="success", result=simplified_result)
        except Exception as e:
            logger.error(f"Error getting spreadsheet info: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_spreadsheet_info",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id}
            )

    @tool
    async def search_google_sheet(
        spreadsheet_id: str,
        search_text: str,
        match_case: bool = False,
        sheet_name: Optional[str] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Searches for text within a Google Spreadsheet and returns all matching cells.

        Args:
            spreadsheet_id: ID of the spreadsheet
            search_text: Text to search for
            match_case: Whether to match case (default False for case-insensitive)
            sheet_name: Optional specific sheet name to search in (default: all sheets)
            account: The specific account to use if the user has multiple

        Returns:
            Dict with number of occurrences and list of matching cells with their positions
        """
        try:
            result = await sheets_integration.search_in_spreadsheet(
                spreadsheet_id, search_text,
                match_case=match_case,
                sheet_name=sheet_name,
                account=account
            )
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error searching Google Sheet: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="search_google_sheet",
                exception=e,
                integration="Google Sheets",
                context={"spreadsheet_id": spreadsheet_id, "search_text": search_text}
            )

    # Dynamic account description logic
    accounts = sheets_integration.get_connected_accounts()
    if not accounts:
        return []

    all_tools = [
        create_google_sheet,
        get_sheet_values,
        update_sheet_values,
        append_sheet_rows,
        clear_sheet_range,
        get_single_cell,
        set_single_cell,
        add_sheet_tab,
        delete_sheet_tab,
        insert_sheet_rows,
        insert_sheet_columns,
        delete_sheet_rows,
        get_spreadsheet_info,
        search_google_sheet
    ]

    if len(accounts) == 1:
        user_email = accounts[0]
        for t in all_tools:
            t.description += f" The user's connected Google account with Sheets access is {user_email}."
    else:
        account_list_str = ", ".join(f"'{acc}'" for acc in accounts)
        for t in all_tools:
            t.description += (
                f" The user has multiple accounts with Sheets access. You MUST use the 'account' parameter to specify which one to use. "
                f"Available accounts are: [{account_list_str}]."
            )

    return all_tools
