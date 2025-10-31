import asyncio
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging.base_logger import setup_logger

logger = setup_logger('google_slides_client')

class GoogleSlidesIntegration(BaseIntegration):
    """
    Google Slides API integration for creating and manipulating Google Slides presentations.

    Requires scope: https://www.googleapis.com/auth/presentations
    """

    def __init__(self, user_id: str):
        super().__init__(user_id)
        # Manages multiple service instances, one per connected account
        self.services: Dict[str, Any] = {}
        self.credentials: Dict[str, Any] = {}
        self.connected_accounts: List[str] = []

    async def authenticate(self) -> bool:
        """Authenticates all connected Google accounts with Slides scope."""
        logger.info(f"Authenticating Google Slides for user {self.user_id}")
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

        # Check if the account has the presentations scope
        if not self._has_slides_scope(creds):
            logger.warning(f"Account {account_email} does not have Google Slides scope")
            return False

        try:
            service = build('slides', 'v1', credentials=creds)
            self.services[account_email] = service
            self.credentials[account_email] = creds
            if account_email not in self.connected_accounts:
                self.connected_accounts.append(account_email)
            logger.info(f"Successfully authenticated Google Slides for {account_email}")
            return True
        except Exception as e:
            logger.error(f"Error building Slides service for account {account_email}: {e}")
            return False

    def _has_slides_scope(self, creds) -> bool:
        """Check if credentials have the presentations scope."""
        if not hasattr(creds, 'scopes'):
            return True  # Assume scope is present if we can't check

        required_scopes = [
            'https://www.googleapis.com/auth/presentations',
            'https://www.googleapis.com/auth/presentations.readonly'
        ]

        return any(scope in creds.scopes for scope in required_scopes)

    def get_connected_accounts(self) -> List[str]:
        return self.connected_accounts

    def _get_service_for_account(self, account: Optional[str] = None) -> Tuple[Any, str]:
        """Retrieves the correct service instance and resolved account email."""
        if account:
            service = self.services.get(account)
            if not service:
                raise ValueError(f"Account '{account}' is not authenticated or does not have Slides scope.")
            return service, account
        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.services[default_account], default_account
        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Google accounts with Slides scope found.")
        raise ValueError(f"Multiple accounts exist. Specify one with the 'account' parameter: {self.connected_accounts}")

    async def create_presentation(self, title: str, *, account: Optional[str] = None) -> Dict:
        """Creates a new Google Slides presentation.

        Args:
            title: Title of the presentation
            account: Google account to use

        Returns:
            Dict with presentationId, title, and url
        """
        service, resolved_account = self._get_service_for_account(account)

        body = {'title': title}

        try:
            presentation = service.presentations().create(body=body).execute()
            logger.info(f"Created presentation '{title}' with ID {presentation['presentationId']} for {resolved_account}")
            return {
                'presentation_id': presentation['presentationId'],
                'title': presentation['title'],
                'url': f"https://docs.google.com/presentation/d/{presentation['presentationId']}/edit"
            }
        except Exception as e:
            logger.error(f"Error creating presentation for {resolved_account}: {e}")
            raise Exception(f"Failed to create presentation: {e}")

    async def get_presentation(self, presentation_id: str, *, account: Optional[str] = None) -> Dict:
        """Gets the contents and metadata of a presentation.

        Args:
            presentation_id: ID of the presentation
            account: Google account to use

        Returns:
            Complete presentation structure
        """
        service, resolved_account = self._get_service_for_account(account)

        try:
            presentation = service.presentations().get(presentationId=presentation_id).execute()
            logger.info(f"Retrieved presentation {presentation_id} for {resolved_account}")
            return presentation
        except Exception as e:
            logger.error(f"Error retrieving presentation {presentation_id}: {e}")
            raise Exception(f"Failed to get presentation: {e}")

    async def create_slide(self, presentation_id: str, insertion_index: Optional[int] = None,
                          layout: str = 'BLANK', *, account: Optional[str] = None) -> Dict:
        """Creates a new slide in a presentation.

        Args:
            presentation_id: ID of the presentation
            insertion_index: Position to insert slide (None = end)
            layout: Layout type (BLANK, TITLE_AND_BODY, TITLE_ONLY, etc.)
            account: Google account to use

        Returns:
            Response with new slide info
        """
        service, resolved_account = self._get_service_for_account(account)

        # Get presentation to find layout ID
        presentation = await self.get_presentation(presentation_id, account=account)

        # Find the layout by predefined layout type
        layout_id = None
        for master in presentation.get('masters', []):
            for layout_obj in master.get('layouts', []):
                layout_type = layout_obj.get('layoutProperties', {}).get('displayName', '')
                if layout.replace('_', ' ').upper() in layout_type.upper():
                    layout_id = layout_obj['objectId']
                    break
            if layout_id:
                break

        # Default to first layout if specific one not found
        if not layout_id and presentation.get('masters'):
            layout_id = presentation['masters'][0]['layouts'][0]['objectId']

        requests = [{
            'createSlide': {
                'slideLayoutReference': {'layoutId': layout_id}
            }
        }]

        if insertion_index is not None:
            requests[0]['createSlide']['insertionIndex'] = insertion_index

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            slide_id = result['replies'][0]['createSlide']['objectId']
            logger.info(f"Created slide in presentation {presentation_id}")
            return result
        except Exception as e:
            logger.error(f"Error creating slide in presentation {presentation_id}: {e}")
            raise Exception(f"Failed to create slide: {e}")

    async def delete_slide(self, presentation_id: str, slide_id: str, *, account: Optional[str] = None) -> Dict:
        """Deletes a slide from a presentation.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide (object ID)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'deleteObject': {
                'objectId': slide_id
            }
        }]

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Deleted slide {slide_id} from presentation {presentation_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting slide from presentation {presentation_id}: {e}")
            raise Exception(f"Failed to delete slide: {e}")

    async def insert_text(self, presentation_id: str, slide_id: str, text: str,
                         x: float = 100, y: float = 100, width: float = 400, height: float = 100,
                         *, account: Optional[str] = None) -> Dict:
        """Inserts a text box with text into a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            text: Text to insert
            x: X position in EMUs or points (default 100)
            y: Y position in EMUs or points (default 100)
            width: Width in EMUs or points (default 400)
            height: Height in EMUs or points (default 100)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        # Convert to EMUs if values look like points
        EMU_PER_POINT = 12700
        if x < 10000:  # Likely points
            x = x * EMU_PER_POINT
            y = y * EMU_PER_POINT
            width = width * EMU_PER_POINT
            height = height * EMU_PER_POINT

        text_box_id = f'text_box_{slide_id}_{hash(text)}'

        requests = [
            {
                'createShape': {
                    'objectId': text_box_id,
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': width, 'unit': 'EMU'},
                            'height': {'magnitude': height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1,
                            'scaleY': 1,
                            'translateX': x,
                            'translateY': y,
                            'unit': 'EMU'
                        }
                    }
                }
            },
            {
                'insertText': {
                    'objectId': text_box_id,
                    'text': text
                }
            }
        ]

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted text box in slide {slide_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting text in presentation {presentation_id}: {e}")
            raise Exception(f"Failed to insert text: {e}")

    async def insert_image(self, presentation_id: str, slide_id: str, image_url: str,
                          x: float = 100, y: float = 100, width: float = 300, height: float = 300,
                          *, account: Optional[str] = None) -> Dict:
        """Inserts an image into a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the image (must be publicly accessible)
            x: X position in points (default 100)
            y: Y position in points (default 100)
            width: Width in points (default 300)
            height: Height in points (default 300)
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        # Convert to EMUs
        EMU_PER_POINT = 12700
        x_emu = x * EMU_PER_POINT
        y_emu = y * EMU_PER_POINT
        width_emu = width * EMU_PER_POINT
        height_emu = height * EMU_PER_POINT

        image_id = f'image_{slide_id}_{hash(image_url)}'

        requests = [{
            'createImage': {
                'objectId': image_id,
                'url': image_url,
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': width_emu, 'unit': 'EMU'},
                        'height': {'magnitude': height_emu, 'unit': 'EMU'}
                    },
                    'transform': {
                        'scaleX': 1,
                        'scaleY': 1,
                        'translateX': x_emu,
                        'translateY': y_emu,
                        'unit': 'EMU'
                    }
                }
            }
        }]

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted image in slide {slide_id}")
            return result
        except Exception as e:
            logger.error(f"Error inserting image in presentation {presentation_id}: {e}")
            raise Exception(f"Failed to insert image: {e}")

    async def update_text_style(self, presentation_id: str, object_id: str, start_index: int, end_index: int,
                               bold: Optional[bool] = None, italic: Optional[bool] = None,
                               font_size: Optional[int] = None, *, account: Optional[str] = None) -> Dict:
        """Updates text styling in a text box or shape.

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the text box or shape
            start_index: Start character index
            end_index: End character index
            bold: Whether to make text bold
            italic: Whether to make text italic
            font_size: Font size in points
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = []
        text_style = {}
        fields = []

        if bold is not None:
            text_style['bold'] = bold
            fields.append('bold')
        if italic is not None:
            text_style['italic'] = italic
            fields.append('italic')
        if font_size is not None:
            text_style['fontSize'] = {'magnitude': font_size, 'unit': 'PT'}
            fields.append('fontSize')

        if not fields:
            raise ValueError("At least one style option must be specified")

        requests.append({
            'updateTextStyle': {
                'objectId': object_id,
                'textRange': {
                    'type': 'FIXED_RANGE',
                    'startIndex': start_index,
                    'endIndex': end_index
                },
                'style': text_style,
                'fields': ','.join(fields)
            }
        })

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Updated text style in object {object_id}")
            return result
        except Exception as e:
            logger.error(f"Error updating text style in presentation {presentation_id}: {e}")
            raise Exception(f"Failed to update text style: {e}")

    async def create_table(self, presentation_id: str, slide_id: str, rows: int, columns: int,
                          x: float = 100, y: float = 100, width: float = 400, height: float = 200,
                          *, account: Optional[str] = None) -> Dict:
        """Creates a table in a slide.

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            rows: Number of rows
            columns: Number of columns
            x: X position in points
            y: Y position in points
            width: Width in points
            height: Height in points
            account: Google account to use

        Returns:
            Response from the API with table object ID
        """
        service, resolved_account = self._get_service_for_account(account)

        # Convert to EMUs
        EMU_PER_POINT = 12700
        x_emu = x * EMU_PER_POINT
        y_emu = y * EMU_PER_POINT
        width_emu = width * EMU_PER_POINT
        height_emu = height * EMU_PER_POINT

        table_id = f'table_{slide_id}_{rows}x{columns}'

        requests = [{
            'createTable': {
                'objectId': table_id,
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': width_emu, 'unit': 'EMU'},
                        'height': {'magnitude': height_emu, 'unit': 'EMU'}
                    },
                    'transform': {
                        'scaleX': 1,
                        'scaleY': 1,
                        'translateX': x_emu,
                        'translateY': y_emu,
                        'unit': 'EMU'
                    }
                },
                'rows': rows,
                'columns': columns
            }
        }]

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Created {rows}x{columns} table in slide {slide_id}")
            return result
        except Exception as e:
            logger.error(f"Error creating table in presentation {presentation_id}: {e}")
            raise Exception(f"Failed to create table: {e}")

    async def delete_object(self, presentation_id: str, object_id: str, *, account: Optional[str] = None) -> Dict:
        """Deletes an object (text box, image, shape, etc.) from a slide.

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the object to delete
            account: Google account to use

        Returns:
            Response from the API
        """
        service, resolved_account = self._get_service_for_account(account)

        requests = [{
            'deleteObject': {
                'objectId': object_id
            }
        }]

        try:
            result = service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Deleted object {object_id} from presentation {presentation_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting object from presentation {presentation_id}: {e}")
            raise Exception(f"Failed to delete object: {e}")
