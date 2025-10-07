from typing import List, Dict, Any, Optional
from src.core.context import UserContext
from src.utils.logging import setup_logger
from langchain_core.tools import Tool
from langchain_google_community import GoogleSearchAPIWrapper
from langchain_community.tools import GooglePlacesTool
import asyncio
# Integration Clients
from src.integrations.notion.notion_client import NotionIntegration
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.integrations.email.gmail_client import GmailIntegration
from src.integrations.gdrive.gdrive_client import GoogleDriveIntegration
from src.integrations.dropbox.dropbox_client import DropboxIntegration
from src.integrations.trello.trello_client import TrelloIntegration
from src.core.praxos_client import PraxosClient

# Tool Module Imports
from src.tools.google_calendar import create_calendar_tools
from src.tools.google_mail import create_gmail_tools
from src.tools.google_drive import create_drive_tools
from src.tools.microsoft_graph import create_outlook_tools
from src.tools.notion import create_notion_tools
from src.tools.trello import create_trello_tools
from src.tools.praxos import create_praxos_memory_tool
from src.tools.communication import create_bot_communication_tools
from src.tools.scheduling import create_scheduling_tools
from src.tools.basic import create_basic_tools
from src.tools.web import create_web_tools
from src.tools.dropbox import create_dropbox_tools
from src.tools.playwright import create_playwright_tools
from src.tools.preference_tools import create_preference_tools
from src.tools.integration_tools import create_integration_tools
from src.tools.database_tools import create_database_access_tools
from src.tools.google_lens import create_google_lens_tools
import src.tools.mock_tools as mock_tools

logger = setup_logger(__name__)

class AgentToolsFactory:
    """Factory for creating agent tools by orchestrating modular tool creators."""
    
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

    async def create_tools(self, user_context: UserContext, metadata: Optional[Dict] = None, user_time_zone: str = 'America/New_York', request_id: str = None, minimal_tools: bool = False) -> List:
        """Create tools based on agent configuration by instantiating integration clients.

        Args:
            user_context: User context information
            metadata: Optional metadata dictionary
            user_time_zone: User's timezone
            llm: Optional LLM instance for AI-powered tools (e.g., browser automation)
        """
        tools = []

        user_id = user_context.user_id
        user_email = user_context.user_record.get('email')
        have_email_tool = False
        have_calendar_tool = False
        if not user_id:
            return []
        try:
            tools.extend(create_bot_communication_tools(metadata, user_id))
        except Exception as e:
            logger.error(f"Error creating bot communication tools: {e}", exc_info=True)
        try:
            tools.extend(create_scheduling_tools(user_id, metadata.get('source'), str(metadata.get('conversation_id'))))
        except Exception as e:
            logger.error(f"Error creating scheduling tools: {e}", exc_info=True)
        try:
            tools.extend(create_basic_tools(user_time_zone))
        except Exception as e:
            logger.error(f"Error creating basic tools: {e}", exc_info=True)
        try:
            tools.extend(create_preference_tools(user_id))
        except Exception as e:
            logger.error(f"Error creating preference tools: {e}", exc_info=True)
        try:
            tools.extend(create_integration_tools(user_id))
            logger.info("Integration tools created successfully.")
        except Exception as e:
            logger.error(f"Error creating integration tools: {e}", exc_info=True)
        try:
            tools.extend(create_database_access_tools(user_id))
        except Exception as e:
            logger.error(f"Error creating database access tools: {e}", exc_info=True)
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
        # if not have_calendar_tool:
        #     tools.extend(mock_tools.create_calendar_tools())
        # if not have_email_tool:
        #     tools.extend(mock_tools.create_email_tools())
        try:
            tools.extend(create_google_lens_tools())
            logger.info("Google Lens product recognition tools created successfully.")
        except Exception as e:
            logger.error(f"Error creating Google Lens tools: {e}", exc_info=True)
        if minimal_tools:
            return tools


        gcal_integration = GoogleCalendarIntegration(user_id)
        gmail_integration = GmailIntegration(user_id)
        gdrive_integration = GoogleDriveIntegration(user_id)
        outlook_integration = MicrosoftGraphIntegration(user_id)
        notion_integration = NotionIntegration(user_id)
        dropbox_integration = DropboxIntegration(user_id)
        trello_integration = TrelloIntegration(user_id)
        tasks = [gcal_integration.authenticate(), gmail_integration.authenticate(), gdrive_integration.authenticate(), outlook_integration.authenticate(), notion_integration.authenticate(), dropbox_integration.authenticate(), trello_integration.authenticate()]
        authenticated_integrations = await asyncio.gather(*tasks, return_exceptions=True)
        gcal_auth_result = authenticated_integrations[0]
        gmail_auth_result = authenticated_integrations[1]
        gdrive_auth_result = authenticated_integrations[2]
        outlook_auth_result = authenticated_integrations[3]
        notion_auth_result = authenticated_integrations[4]
        dropbox_auth_result = authenticated_integrations[5]
        trello_auth_result = authenticated_integrations[6]

        if gcal_auth_result is True:
            try:
                tools.extend(create_calendar_tools(gcal_integration))
                have_calendar_tool = True
            except Exception as e:
                logger.error(f"Error creating calendar tools: {e}", exc_info=True)
        if gmail_auth_result is True:
            try:
                tools.extend(create_gmail_tools(gmail_integration))
                have_email_tool = True
            except Exception as e:
                logger.error(f"Error creating email tools: {e}", exc_info=True)
        if gdrive_auth_result is True:
            try:
                tools.extend(create_drive_tools(gdrive_integration))
            except Exception as e:
                logger.error(f"Error creating drive tools: {e}", exc_info=True)

        # --- Microsoft Integration ---
        if outlook_auth_result is True:
            try:
                tools.extend(create_outlook_tools(outlook_integration))
                have_email_tool = True
                have_calendar_tool = True
            except Exception as e:
                logger.error(f"Error creating Outlook tools: {e}", exc_info=True)

        # --- Notion Integration ---
        if notion_auth_result is True:
            try:
                tools.extend(create_notion_tools(notion_integration))
            except Exception as e:
                logger.error(f"Error creating Notion tools: {e}", exc_info=True)

        # --- Dropbox Integration ---
        if dropbox_auth_result is True:
            try:
                tools.extend(create_dropbox_tools(dropbox_integration))
            except Exception as e:
                logger.error(f"Error creating Dropbox tools: {e}", exc_info=True)

        # --- Trello Integration ---
        if trello_auth_result is True:
            try:
                tools.extend(create_trello_tools(trello_integration))
                logger.info("Trello tools created successfully.")
            except Exception as e:
                logger.error(f"Error creating Trello tools: {e}", exc_info=True)

        # --- Praxos & Other Core Tools ---
        from src.config.settings import settings
        if settings.OPERATING_MODE == "local":
            praxos_api_key = settings.PRAXOS_API_KEY
        else:
            praxos_api_key = user_context.user_record.get("praxos_api_key")

        if praxos_api_key:
            praxos_client = PraxosClient(f"env_for_{user_email}", api_key=praxos_api_key)
            tools.extend(create_praxos_memory_tool(praxos_client, user_id, str(metadata.get('conversation_id'))))
        else:
            logger.warning("Praxos API key not found, memory tools will be unavailable.")
        

        ## web tools

        try:
            tools.extend(create_web_tools(request_id=request_id))
        except Exception as e:
            logger.error(f"Error creating web tools: {e}", exc_info=True)


        

        # --- Browser Tools ---
        # PLAYWRIGHT DEPRECATED
        # try:
        #     tools.extend(create_playwright_tools())
        # except Exception as e:
        #     logger.error(f"Error creating Playwright browser tools: {e}", exc_info=True)

        # --- Google Lens Tools (Product/Brand Recognition via SerpAPI) ---

        
        # --- External API Tools ---




        return tools
