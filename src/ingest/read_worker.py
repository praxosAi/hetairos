from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

class ReadWorker:
    """
    Fetches documents from a given integration and prepares them as in-memory files.
    """

    def __init__(self):
        self.integration_classes = {}
        self._load_integration_classes()

    def _load_integration_classes(self):
        """Lazy load integration classes to avoid circular imports."""
        try:
            from src.integrations.email.gmail_client import GmailIntegration
            from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
            from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
            from src.integrations.notion.notion_client import NotionIntegration
            from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
            from src.integrations.onedrive.onedrive_client import OneDriveIntegration

            self.integration_classes = {
                "gmail": GmailIntegration,
                "outlook": MicrosoftGraphIntegration, # Renamed
                "microsoft": MicrosoftGraphIntegration, # Added for clarity
                "google_calendar": GoogleCalendarIntegration,
                "notion": NotionIntegration,
                "google_drive": GoogleDriveIntegration,
                "onedrive": OneDriveIntegration,
            }
        except ImportError as e:
            print(f"Error loading integration classes: {e}")

    async def read_data(self, user_id: str, integration_type: str) -> List[Dict[str, Any]]:
        """
        Reads data from the specified integration and returns a list of in-memory files.
        """
        if integration_type not in self.integration_classes:
            raise ValueError(f"Integration type {integration_type} not supported")

        integration_class = self.integration_classes[integration_type]
        integration = integration_class(user_id)

        if not await integration.authenticate():
            raise Exception(f"Authentication failed for {integration_type}")

        since = datetime.utcnow() - timedelta(days=30)
        raw_data = await integration.fetch_recent_data(since=since)
        
        files = await self._transform_to_files(integration, raw_data, integration_type)
        return files

    async def _transform_to_files(self, integration: Any, data: List[Dict], integration_type: str) -> List[Dict[str, Any]]:
        """
        Transforms fetched data into a standardized in-memory file format.
        """
        files = []
        # This loop now handles data that could be mixed (e.g., from Microsoft Graph)
        for item in data:
            item_type = item.get("type") # Helper field added in MicrosoftGraphIntegration

            # --- Email Handling (Gmail & Outlook) ---
            if integration_type in ["gmail"] or item_type == "email":
                email_content = f"Subject: {item.get('subject', '')}\nFrom: {item.get('from', '')}\nTo: {', '.join(item.get('to', []))}\nDate: {item.get('date', '')}\n\n{item.get('body', '')}"
                files.append({
                    "filename": f"email_{item.get('id', 'unknown')}.txt",
                    "content": email_content.encode('utf-8'),
                    "mimetype": "text/plain",
                    "metadata": {"source": item.get("source", integration_type), "type": "email", **item}
                })
                for attachment in item.get('attachments', []):
                    attachment_id = attachment.get('id') or attachment.get('attachmentId')
                    message_id = item.get('id')
                    filename = attachment.get('filename') or attachment.get('name')
                    if attachment_id and message_id and hasattr(integration, 'download_attachment'):
                        attachment_content = await integration.download_attachment(message_id=message_id, attachment_id=attachment_id)
                        if attachment_content:
                            files.append({
                                "filename": filename,
                                "content": attachment_content,
                                "mimetype": attachment.get('mimetype') or attachment.get('contentType'),
                                "metadata": {"source": f"{item.get('source', integration_type)}_attachment", "type": "attachment", "email_id": item['id'], **attachment}
                            })
            
            # --- Calendar Event Handling (Google & Outlook) ---
            elif integration_type == "google_calendar" or item_type == "calendar_event":
                event_content = f"Title: {item.get('title', '')}\nStart: {item.get('start', '')}\nEnd: {item.get('end', '')}\n\nDescription:\n{item.get('description', '')}"
                files.append({
                    "filename": f"event_{item.get('id', 'unknown')}.txt",
                    "content": event_content.encode('utf-8'),
                    "mimetype": "text/plain",
                    "metadata": {"source": item.get("source", integration_type), "type": "calendar_event", **item}
                })

            # --- Notion Page Handling ---
            elif integration_type == "notion":
                page_content = f"Title: {item.get('title', '')}\nURL: {item.get('url', '')}\nLast Edited: {item.get('last_edited_time', '')}\n\n{item.get('content', '')}"
                files.append({
                    "filename": f"notion_{item.get('id', 'unknown')}.txt",
                    "content": page_content.encode('utf-8'),
                    "mimetype": "text/plain",
                    "metadata": {"source": integration_type, "type": "page", **item}
                })

            # --- File Handling (Google Drive & OneDrive) ---
            elif integration_type in ["google_drive", "onedrive"]:
                file_id = item.get('id')
                if file_id and hasattr(integration, 'download_file'):
                    file_content = await integration.download_file(file_id)
                    if file_content:
                        files.append({
                            "filename": item.get('name', 'unknown_file'),
                            "content": file_content,
                            "mimetype": item.get('mimeType', 'application/octet-stream'),
                            "metadata": {"source": integration_type, "type": "file", **item}
                        })
        
        return files