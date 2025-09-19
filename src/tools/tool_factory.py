from typing import List, Dict, Any, Optional
from src.core.context import UserContext
from src.utils.logging import setup_logger
from langchain_core.tools import Tool
from langchain_google_community import GoogleSearchAPIWrapper
from langchain_community.tools import GooglePlacesTool

# Integration Clients
from src.integrations.notion.notion_client import NotionIntegration
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.integrations.email.gmail_client import GmailIntegration
from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.integrations.dropbox.dropbox_client import DropboxIntegration
from src.core.praxos_client import PraxosClient

# Tool Module Imports
from src.tools.google_calendar import create_calendar_tools
from src.tools.google_mail import create_gmail_tools
from src.tools.google_drive import create_drive_tools
from src.tools.microsoft_graph import create_outlook_tools
from src.tools.notion import create_notion_tools
from src.tools.praxos import create_praxos_memory_tool
from src.tools.communication import create_bot_communication_tools
from src.tools.scheduling import create_scheduling_tools
from src.tools.basic import create_basic_tools
from src.tools.web import create_web_tools
from src.tools.dropbox import create_dropbox_tools
from src.tools.playwright import create_playwright_tools
import src.tools.mock_tools as mock_tools

logger = setup_logger(__name__)

class AgentToolsFactory:
    """Factory for creating agent tools by orchestrating modular tool creators."""
    
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

    async def create_tools(self, user_context: UserContext, metadata: Optional[Dict] = None, tools_to_build: Optional[List[str]] = None) -> List:
        """Create tools based on agent configuration by instantiating integration clients."""
        tools = []
        user_id = user_context.user_id
        user_email = user_context.user_record.get('email')

        have_email_tool = False
        have_calendar_tool = False

        if not user_id:
            return []
        # --- Google Integrations ---
        if not tools_to_build or any('calendar' in tool_name for tool_name in tools_to_build):
            gcal_integration = GoogleCalendarIntegration(user_id)
            if await gcal_integration.authenticate():
                tools.extend(create_calendar_tools(gcal_integration))
                have_calendar_tool = True
        
        if not tools_to_build or any('email' in tool_name for tool_name in tools_to_build):
            gmail_integration = GmailIntegration(user_id)
            if await gmail_integration.authenticate():
                tools.extend(create_gmail_tools(gmail_integration))
                have_email_tool = True
        if not tools_to_build or any('drive' in tool_name for tool_name in tools_to_build):
            gdrive_integration = GoogleDriveIntegration(user_id)
            if await gdrive_integration.authenticate():
                tools.extend(create_drive_tools(gdrive_integration))
        
        # --- Microsoft Integration ---
        if not tools_to_build or any(tool_name in ['email', 'calendar', 'outlook'] for tool_name in tools_to_build):
            outlook_integration = MicrosoftGraphIntegration(user_id)
            if await outlook_integration.authenticate():
                tools.extend(create_outlook_tools(outlook_integration))
                have_email_tool = True
                have_calendar_tool = True

        # --- Notion Integration ---
        if not tools_to_build or any('notion' in tool_name for tool_name in tools_to_build):
            notion_integration = NotionIntegration(user_id)
            if await notion_integration.authenticate():
                tools.extend(create_notion_tools(notion_integration))

        # --- Dropbox Integration ---
        if not tools_to_build or any('dropbox' in tool_name for tool_name in tools_to_build):
            dropbox_integration = DropboxIntegration(user_id)
            if await dropbox_integration.authenticate():
                tools.extend(create_dropbox_tools(dropbox_integration))

        # --- Praxos & Other Core Tools ---
        from src.config.settings import settings
        if settings.OPERATING_MODE == "local":
            praxos_api_key = settings.PRAXOS_API_KEY
        else:
            praxos_api_key = user_context.user_record.get("praxos_api_key")

        if praxos_api_key:
            praxos_client = PraxosClient(f"env_for_{user_email}", api_key=praxos_api_key)
            tools.extend(create_praxos_memory_tool(praxos_client))
        else:
            logger.warning("Praxos API key not found, memory tools will be unavailable.")

        tools.extend(create_bot_communication_tools(metadata, user_id))
        try:
            tools.extend(create_scheduling_tools(user_id, metadata.get('source')))
        except Exception as e:
            logger.error(f"Error creating scheduling tools: {e}", exc_info=True)
        try:
            tools.extend(create_basic_tools())
        except Exception as e:
            logger.error(f"Error creating basic tools: {e}", exc_info=True)
        try:
            tools.extend(create_web_tools())
        except Exception as e:
            logger.error(f"Error creating web tools: {e}", exc_info=True)

        # --- Browser Tools ---
        try:
            tools.extend(create_playwright_tools())
        except Exception as e:
            logger.error(f"Error creating Playwright browser tools: {e}", exc_info=True)
        
        # --- External API Tools ---
        try:
            search = GoogleSearchAPIWrapper()
            tools.append(Tool(name="google_search", description="Search Google for recent results.", func=search.run))
        except Exception as e:
            logger.error(f"Error creating Google search tool: {e}", exc_info=True)

        try:
            tools.append(GooglePlacesTool())
        except Exception as e:
            logger.error(f"Error creating Google places tool: {e}", exc_info=True)

        # --- Mock Tools ---
        if not have_calendar_tool:
            tools.extend(mock_tools.create_calendar_tools())
        if not have_email_tool:
            tools.extend(mock_tools.create_email_tools())

        return tools
