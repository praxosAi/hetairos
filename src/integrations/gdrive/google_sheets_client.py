import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger('google_sheets_client')

class GoogleSheetsIntegration(BaseIntegration):
    """
    Google Sheets API integration for creating and manipulating Google Sheets.

    Requires scope: https://www.googleapis.com/auth/spreadsheets
    """

    def __init__(self, user_id: str):
        super().__init__(user_id)
        # Manages multiple service instances, one per connected account
        self.services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """Authenticates all connected Google accounts with Sheets scope."""
        logger.info(f"Authenticating Google Sheets for user {self.user_id}")
        integration_records = await integration_service.get_all_integrations_for_user_by_name(self.user_id, 'google_drive')

        if not integration_records:
            logger.warning(f"No Google Drive integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]
        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict[str, Any]) -> bool:
        """Authenticates a single account using its unique integration ID."""
        account_email = integration_record.get('connected_account')
        integration_id = integration_record.get('_id')

        if not account_email or not integration_id:
            logger.warning(f"Integration record for {self.user_id} is missing '_id' or 'connected_account'.")
            return False

        creds = await integration_service.create_google_credentials(self.user_id, 'google_drive', str(integration_id))

        if not creds:
            logger.error(f"Failed to create credentials for account {account_email}")
            return False

        # Check if the account has the spreadsheets scope
        if not self._has_sheets_scope(creds):
            logger.warning(f"Account {account_email} does not have Google Sheets scope")
            return False

        try:
            service = build('sheets', 'v4', credentials=creds)
            self.services[account_email] = service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            logger.info(f"Successfully authenticated Google Sheets for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building Sheets service for account {account_email}: {e}")
            return False

    def _has_sheets_scope(self, creds) -> bool:
        """Check if credentials have the spreadsheets scope."""
        if not hasattr(creds, 'scopes'):
            return True  # Assume scope is present if we can't check

        required_scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/spreadsheets.readonly'
        ]

        return any(scope in creds.scopes for scope in required_scopes)

    def get_connected_accounts(self) -> List[str]:
        return self.connected_accounts

    def _get_service_for_account(self, account: Optional[str] = None) -> Tuple[Any, str]:
        """Retrieves the correct service instance and resolved account email."""
        if account:
            service = self.services.get(account)
            if not service:
                raise ValueError(f"Account '{account}' is not authenticated or does not have Sheets scope.")
            return service, account
        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.services[default_account], default_account
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Google accounts with Sheets scope found.")
        raise ValueError(f"Multiple accounts exist. Specify one with the 'account' parameter: {self.connected_accounts}")

    async def create_spreadsheet(self, title: str, sheet_names: Optional[List[str]] = None,
                                *, account: Optional[str] = None) -> Dict:
        """Creates a new Google Spreadsheet.

        Args:
            title: Title of the spreadsheet
            sheet_names: Optional list of sheet names (default is one sheet named 'Sheet1')
            account: Google account to use

        Returns:
            Dict with spreadsheetId, spreadsheetUrl, and sheets info
        """
        service, resolved_account = self._get_service_for_account(account)

        spreadsheet_body = {'properties': {'title': title}}

        if sheet_names:
            spreadsheet_body['sheets'] = [
                {'properties': {'title': name}} for name in sheet_names
            ]

        try:
            spreadsheet = service.spreadsheets().create(body=spreadsheet_body).execute()
            logger.info(f"Created spreadsheet '{title}' with ID {spreadsheet['spreadsheetId']} for {resolved_account}")
            return {
                'spreadsheet_id': spreadsheet['spreadsheetId'],
                'spreadsheet_url': spreadsheet['spreadsheetUrl'],
                'title': spreadsheet['properties']['title'],
                'sheets': [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
            }
        except Exception as e:
            logger.error(f"Error creating spreadsheet for {resolved_account}: {e}")
            raise Exception(f"Failed to create spreadsheet: {e}")

    async def get_spreadsheet(self, spreadsheet_id: str, *, account: Optional[str] = None) -> Dict:
        """Gets the metadata and structure of a spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            account: Google account to use

        Returns:
            Complete spreadsheet metadata
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            logger.info(f"Retrieved spreadsheet {spreadsheet_id} for {resolved_account}")
            return spreadsheet
        except Exception as e:
            logger.error(f"Error retrieving spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to get spreadsheet: {e}")

    async def get_values(self, spreadsheet_id: str, range_name: str, *, account: Optional[str] = None) -> List[List[Any]]:
        """Gets cell values from a spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range (e.g., 'Sheet1!A1:D10')
            account: Google account to use

        Returns:
            2D list of cell values
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()

            values = result.get('values', [])
            logger.info(f"Retrieved {len(values)} rows from {range_name} in spreadsheet {spreadsheet_id}")
            return values
        except Exception as e:
            logger.error(f"Error getting values from spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to get values: {e}")

    async def update_values(self, spreadsheet_id: str, range_name: str, values: List[List[Any]],
                           value_input_option: str = 'USER_ENTERED', *, account: Optional[str] = None) -> Dict:
        """Updates cell values in a spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range (e.g., 'Sheet1!A1')
            values: 2D list of values to write
            value_input_option: How to interpret input ('RAW' or 'USER_ENTERED' for formulas/formatting)
            account: Google account to use

        Returns:
            Update response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        body = {'values': values}

        try:
            result = service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body
            ).execute()

            logger.info(f"Updated {result.get('updatedCells', 0)} cells in {range_name}")
            return result
        except Exception as e:
            logger.error(f"Error updating values in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to update values: {e}")

    async def append_values(self, spreadsheet_id: str, range_name: str, values: List[List[Any]],
                           value_input_option: str = 'USER_ENTERED', *, account: Optional[str] = None) -> Dict:
        """Appends values to a spreadsheet (adds rows at the end).

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range to append to (e.g., 'Sheet1!A:D')
            values: 2D list of values to append
            value_input_option: How to interpret input ('RAW' or 'USER_ENTERED')
            account: Google account to use

        Returns:
            Append response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        body = {'values': values}

        try:
            result = service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()

            logger.info(f"Appended {len(values)} rows to {range_name}")
            return result
        except Exception as e:
            logger.error(f"Error appending values to spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to append values: {e}")

    async def clear_values(self, spreadsheet_id: str, range_name: str, *, account: Optional[str] = None) -> Dict:
        """Clears values from a range in a spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            range_name: A1 notation range to clear (e.g., 'Sheet1!A1:D10')
            account: Google account to use

        Returns:
            Clear response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            result = service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()

            logger.info(f"Cleared range {range_name} in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error clearing values in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to clear values: {e}")

    async def batch_update_values(self, spreadsheet_id: str, updates: List[Dict[str, Any]],
                                 value_input_option: str = 'USER_ENTERED', *, account: Optional[str] = None) -> Dict:
        """Updates multiple ranges in a spreadsheet in a single request.

        Args:
            spreadsheet_id: ID of the spreadsheet
            updates: List of dicts with 'range' and 'values' keys
            value_input_option: How to interpret input
            account: Google account to use

        Returns:
            Batch update response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        body = {
            'valueInputOption': value_input_option,
            'data': updates
        }

        try:
            result = service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()

            logger.info(f"Batch updated {len(updates)} ranges in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error batch updating spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to batch update: {e}")

    async def add_sheet(self, spreadsheet_id: str, sheet_title: str, rows: int = 1000, columns: int = 26,
                       *, account: Optional[str] = None) -> Dict:
        """Adds a new sheet to an existing spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_title: Title for the new sheet
            rows: Number of rows (default 1000)
            columns: Number of columns (default 26)
            account: Google account to use

        Returns:
            Response from the API with new sheet info
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'addSheet': {
                'properties': {
                    'title': sheet_title,
                    'gridProperties': {
                        'rowCount': rows,
                        'columnCount': columns
                    }
                }
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            sheet_id = result['replies'][0]['addSheet']['properties']['sheetId']
            logger.info(f"Added sheet '{sheet_title}' (ID: {sheet_id}) to spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error adding sheet to spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to add sheet: {e}")

    async def delete_sheet(self, spreadsheet_id: str, sheet_id: int, *, account: Optional[str] = None) -> Dict:
        """Deletes a sheet from a spreadsheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: ID of the sheet to delete (not the title)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'deleteSheet': {
                'sheetId': sheet_id
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Deleted sheet ID {sheet_id} from spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting sheet from spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to delete sheet: {e}")

    async def format_cells(self, spreadsheet_id: str, sheet_id: int, start_row: int, end_row: int,
                          start_col: int, end_col: int, format_options: Dict[str, Any],
                          *, account: Optional[str] = None) -> Dict:
        """Applies formatting to a range of cells.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: ID of the sheet
            start_row: Starting row index (0-based)
            end_row: Ending row index (exclusive)
            start_col: Starting column index (0-based)
            end_col: Ending column index (exclusive)
            format_options: Dict with formatting options (backgroundColor, textFormat, etc.)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': start_row,
                    'endRowIndex': end_row,
                    'startColumnIndex': start_col,
                    'endColumnIndex': end_col
                },
                'cell': {
                    'userEnteredFormat': format_options
                },
                'fields': 'userEnteredFormat'
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Formatted cells in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error formatting cells in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to format cells: {e}")

    async def insert_rows(self, spreadsheet_id: str, sheet_id: int, start_index: int, count: int,
                         *, account: Optional[str] = None) -> Dict:
        """Inserts empty rows into a sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: ID of the sheet
            start_index: Row index where to insert (0-based)
            count: Number of rows to insert
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'insertDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': start_index,
                    'endIndex': start_index + count
                }
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted {count} rows at index {start_index} in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting rows in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to insert rows: {e}")

    async def insert_columns(self, spreadsheet_id: str, sheet_id: int, start_index: int, count: int,
                            *, account: Optional[str] = None) -> Dict:
        """Inserts empty columns into a sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: ID of the sheet
            start_index: Column index where to insert (0-based)
            count: Number of columns to insert
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'insertDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': start_index,
                    'endIndex': start_index + count
                }
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted {count} columns at index {start_index} in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting columns in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to insert columns: {e}")

    async def delete_rows(self, spreadsheet_id: str, sheet_id: int, start_index: int, end_index: int,
                         *, account: Optional[str] = None) -> Dict:
        """Deletes rows from a sheet.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_id: ID of the sheet
            start_index: Starting row index (0-based, inclusive)
            end_index: Ending row index (exclusive)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'deleteDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': start_index,
                    'endIndex': end_index
                }
            }
        }]

        try:
            result = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Deleted rows {start_index}-{end_index} in spreadsheet {spreadsheet_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting rows in spreadsheet {spreadsheet_id}: {e}")
            raise Exception(f"Failed to delete rows: {e}")

    async def get_cell_value(self, spreadsheet_id: str, sheet_name: str, row: int, col: str,
                            *, account: Optional[str] = None) -> Any:
        """Gets the value of a single cell.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_name: Name of the sheet
            row: Row number (1-based, e.g., 1 for row 1)
            col: Column letter (e.g., 'A', 'B', 'AA')
            account: Google account to use

        Returns:
            The cell value
        """
        range_name = f"{sheet_name}!{col}{row}"
        values = await self.get_values(spreadsheet_id, range_name, account=account)

        if values and len(values) > 0 and len(values[0]) > 0:
            return values[0][0]
        return None

    async def set_cell_value(self, spreadsheet_id: str, sheet_name: str, row: int, col: str, value: Any,
                            *, account: Optional[str] = None) -> Dict:
        """Sets the value of a single cell.

        Args:
            spreadsheet_id: ID of the spreadsheet
            sheet_name: Name of the sheet
            row: Row number (1-based)
            col: Column letter (e.g., 'A', 'B')
            value: Value to set
            account: Google account to use

        Returns:
            Update response from the API
        """
        range_name = f"{sheet_name}!{col}{row}"
        return await self.update_values(spreadsheet_id, range_name, [[value]], account=account)

    async def search_in_spreadsheet(self, spreadsheet_id: str, search_text: str,
                                   match_case: bool = False, sheet_name: Optional[str] = None,
                                   *, account: Optional[str] = None) -> Dict:
        """Searches for text within a Google Spreadsheet and returns all matching cells.

        Args:
            spreadsheet_id: ID of the spreadsheet
            search_text: Text to search for
            match_case: Whether to match case (default False)
            sheet_name: Optional specific sheet to search in (default: all sheets)
            account: Google account to use

        Returns:
            Dict with occurrences count and list of matching cells with positions
        """
        spreadsheet = await self.get_spreadsheet(spreadsheet_id, account=account)

        # Determine which sheets to search
        sheets_to_search = []
        if sheet_name:
            # Search only specified sheet
            for sheet in spreadsheet.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    sheets_to_search.append(sheet)
                    break
        else:
            # Search all sheets
            sheets_to_search = spreadsheet.get('sheets', [])

        matches = []
        search_lower = search_text if match_case else search_text.lower()

        # Search through each sheet
        for sheet in sheets_to_search:
            sheet_title = sheet['properties']['title']

            # Get all values from the sheet
            try:
                values = await self.get_values(spreadsheet_id, f"{sheet_title}!A:ZZ", account=account)

                # Search through all cells
                for row_idx, row in enumerate(values):
                    for col_idx, cell_value in enumerate(row):
                        if not cell_value:
                            continue

                        cell_str = str(cell_value)
                        cell_to_search = cell_str if match_case else cell_str.lower()

                        if search_lower in cell_to_search:
                            # Convert column index to letter
                            col_letter = self._column_index_to_letter(col_idx)
                            cell_address = f"{sheet_title}!{col_letter}{row_idx + 1}"

                            matches.append({
                                'sheet': sheet_title,
                                'cell': f"{col_letter}{row_idx + 1}",
                                'address': cell_address,
                                'value': cell_value,
                                'row': row_idx + 1,
                                'column': col_letter
                            })

            except Exception as e:
                logger.warning(f"Error searching sheet {sheet_title}: {e}")
                continue

        logger.info(f"Found {len(matches)} cells containing '{search_text}' in spreadsheet {spreadsheet_id}")

        return {
            'spreadsheet_id': spreadsheet_id,
            'search_text': search_text,
            'occurrences_found': len(matches),
            'matches': matches
        }

    def _column_index_to_letter(self, col_idx: int) -> str:
        """Converts a 0-based column index to column letter (A, B, ..., Z, AA, AB, ...)."""
        result = ""
        col_idx += 1  # Convert to 1-based
        while col_idx > 0:
            col_idx -= 1
            result = chr(65 + (col_idx % 26)) + result
            col_idx //= 26
        return result

    async def fetch_recent_data(self) -> None:
        """Fetches recent data for all connected accounts to refresh tokens if needed."""
        logger.info(f"Fetching recent data for Google Sheets accounts of user {self.user_id}")
        pass