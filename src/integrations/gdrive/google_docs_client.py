import asyncio
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger('google_docs_client')

class GoogleDocsIntegration(BaseIntegration):
    """
    Google Docs API integration for creating and manipulating Google Docs.

    Requires scope: https://www.googleapis.com/auth/documents
    """

    def __init__(self, user_id: str):
        super().__init__(user_id)
        # Manages multiple service instances, one per connected account
        self.services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """Authenticates all connected Google accounts with Docs scope."""
        logger.info(f"Authenticating Google Docs for user {self.user_id}")
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

        # Check if the account has the documents scope
        if not self._has_docs_scope(creds):
            logger.warning(f"Account {account_email} does not have Google Docs scope")
            return False

        try:
            service = build('docs', 'v1', credentials=creds)
            self.services[account_email] = service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            logger.info(f"Successfully authenticated Google Docs for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building Docs service for account {account_email}: {e}")
            return False

    def _has_docs_scope(self, creds) -> bool:
        """Check if credentials have the documents scope."""
        if not hasattr(creds, 'scopes'):
            return True  # Assume scope is present if we can't check

        required_scopes = [
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/documents.readonly'
        ]

        return any(scope in creds.scopes for scope in required_scopes)

    def get_connected_accounts(self) -> List[str]:
        return self.connected_accounts

    def _get_service_for_account(self, account: Optional[str] = None) -> Tuple[Any, str]:
        """Retrieves the correct service instance and resolved account email."""
        if account:
            service = self.services.get(account)
            if not service:
                raise ValueError(f"Account '{account}' is not authenticated or does not have Docs scope.")
            return service, account
        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.services[default_account], default_account
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Google accounts with Docs scope found.")
        raise ValueError(f"Multiple accounts exist. Specify one with the 'account' parameter: {self.connected_accounts}")

    async def create_document(self, title: str, *, account: Optional[str] = None) -> Dict:
        """Creates a new empty Google Doc.

        Args:
            title: Title of the document
            account: Google account to use

        Returns:
            Dict with documentId and title
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            doc = service.documents().create(body={'title': title}).execute()
            logger.info(f"Created Google Doc '{title}' with ID {doc['documentId']} for {resolved_account}")
            return {
                'document_id': doc['documentId'],
                'title': doc['title'],
                'url': f"https://docs.google.com/document/d/{doc['documentId']}/edit"
            }
        except Exception as e:
            logger.error(f"Error creating document for {resolved_account}: {e}")
            raise Exception(f"Failed to create document: {e}")

    async def get_document(self, document_id: str, *, account: Optional[str] = None) -> Dict:
        """Gets the contents and metadata of a Google Doc.

        Args:
            document_id: ID of the document
            account: Google account to use

        Returns:
            Complete document structure
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            doc = service.documents().get(documentId=document_id).execute()
            logger.info(f"Retrieved document {document_id} for {resolved_account}")
            return doc
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}")
            raise Exception(f"Failed to get document: {e}")

    async def get_document_text(self, document_id: str, *, account: Optional[str] = None) -> str:
        """Gets just the plain text content of a Google Doc.

        Args:
            document_id: ID of the document
            account: Google account to use

        Returns:
            Plain text content of the document
        """
        doc = await self.get_document(document_id, account=account)

        text_content = []
        for element in doc.get('body', {}).get('content', []):
            if 'paragraph' in element:
                paragraph = element['paragraph']
                for elem in paragraph.get('elements', []):
                    if 'textRun' in elem:
                        text_content.append(elem['textRun'].get('content', ''))

        return ''.join(text_content)

    async def insert_text(self, document_id: str, text: str, index: int = 1, *, account: Optional[str] = None) -> Dict:
        """Inserts text at a specific location in a Google Doc.

        Args:
            document_id: ID of the document
            text: Text to insert
            index: Character index where to insert (1 = beginning, after title)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'insertText': {
                'location': {'index': index},
                'text': text
            }
        }]

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Inserted text at index {index} in document {document_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting text in document {document_id}: {e}")
            raise Exception(f"Failed to insert text: {e}")

    async def append_text(self, document_id: str, text: str, *, account: Optional[str] = None) -> Dict:
        """Appends text to the end of a Google Doc.

        Args:
            document_id: ID of the document
            text: Text to append
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        # Get document to find the end index
        doc = await self.get_document(document_id, account=account)
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1) - 1

        return await self.insert_text(document_id, text, end_index, account=account)

    async def format_text(self, document_id: str, start_index: int, end_index: int,
                         bold: Optional[bool] = None, italic: Optional[bool] = None,
                         underline: Optional[bool] = None, *, account: Optional[str] = None) -> Dict:
        """Applies text formatting to a range in a Google Doc.

        Args:
            document_id: ID of the document
            start_index: Start of the range to format
            end_index: End of the range to format
            bold: Whether to make text bold
            italic: Whether to make text italic
            underline: Whether to underline text
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        text_style = {}
        fields = []

        if bold is not None:
            text_style['bold'] = bold
            fields.append('bold')
        if italic is not None:
            text_style['italic'] = italic
            fields.append('italic')
        if underline is not None:
            text_style['underline'] = underline
            fields.append('underline')

        if not fields:
            raise ValueError("At least one formatting option (bold, italic, underline) must be specified")

        requests = [{
            'updateTextStyle': {
                'range': {
                    'startIndex': start_index,
                    'endIndex': end_index
                },
                'textStyle': text_style,
                'fields': ','.join(fields)
            }
        }]

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Applied formatting to range {start_index}-{end_index} in document {document_id}")
            return result
        except Exception as e:
            logger.error(f"Error formatting text in document {document_id}: {e}")
            raise Exception(f"Failed to format text: {e}")

    async def insert_paragraph(self, document_id: str, text: str, index: int = 1,
                              heading_level: Optional[int] = None, *, account: Optional[str] = None) -> Dict:
        """Inserts a paragraph (optionally as a heading) into a Google Doc.

        Args:
            document_id: ID of the document
            text: Paragraph text
            index: Character index where to insert
            heading_level: If specified, makes the paragraph a heading (1-6)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'insertText': {
                'location': {'index': index},
                'text': text + '\n'
            }
        }]

        # If heading level specified, apply heading style
        if heading_level and 1 <= heading_level <= 6:
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': index,
                        'endIndex': index + len(text) + 1
                    },
                    'paragraphStyle': {
                        'namedStyleType': f'HEADING_{heading_level}'
                    },
                    'fields': 'namedStyleType'
                }
            })

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Inserted paragraph at index {index} in document {document_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting paragraph in document {document_id}: {e}")
            raise Exception(f"Failed to insert paragraph: {e}")

    async def insert_table(self, document_id: str, rows: int, columns: int, index: int = 1,
                          *, account: Optional[str] = None) -> Dict:
        """Inserts a table into a Google Doc.

        Args:
            document_id: ID of the document
            rows: Number of rows
            columns: Number of columns
            index: Character index where to insert
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'insertTable': {
                'rows': rows,
                'columns': columns,
                'location': {'index': index}
            }
        }]

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Inserted {rows}x{columns} table at index {index} in document {document_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting table in document {document_id}: {e}")
            raise Exception(f"Failed to insert table: {e}")

    async def delete_content_range(self, document_id: str, start_index: int, end_index: int,
                                  *, account: Optional[str] = None) -> Dict:
        """Deletes content in a specific range of a Google Doc.

        Args:
            document_id: ID of the document
            start_index: Start of the range to delete
            end_index: End of the range to delete
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'deleteContentRange': {
                'range': {
                    'startIndex': start_index,
                    'endIndex': end_index
                }
            }
        }]

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Deleted content range {start_index}-{end_index} in document {document_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting content in document {document_id}: {e}")
            raise Exception(f"Failed to delete content: {e}")

    async def replace_all_text(self, document_id: str, find_text: str, replace_text: str,
                              match_case: bool = True, *, account: Optional[str] = None) -> Dict:
        """Replaces all occurrences of text in a Google Doc.

        Args:
            document_id: ID of the document
            find_text: Text to find
            replace_text: Text to replace with
            match_case: Whether to match case
            account: Google account to use

        Returns:
            Response from the API including number of replacements made
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'replaceAllText': {
                'containsText': {
                    'text': find_text,
                    'matchCase': match_case
                },
                'replaceText': replace_text
            }
        }]

        try:
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            replacements = result.get('replies', [{}])[0].get('replaceAllText', {}).get('occurrencesChanged', 0)
            logger.info(f"Replaced {replacements} occurrences of '{find_text}' in document {document_id}")

            return {
                'occurrences_changed': replacements,
                'full_response': result
            }
        except Exception as e:
            logger.error(f"Error replacing text in document {document_id}: {e}")
            raise Exception(f"Failed to replace text: {e}")

    async def fetch_recent_data(self) -> None:
        """Fetches recent data for all connected accounts to refresh tokens if needed."""
        logger.info(f"Fetching recent data for Google Docs accounts of user {self.user_id}")
        pass