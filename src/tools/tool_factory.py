from typing import List, Dict, Any, Optional
from src.core.context import UserContext
from src.services.conversation_manager import ConversationManager
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
from src.tools.communication import create_bot_communication_tools, create_platform_messaging_tools
from src.tools.media_generation import create_media_generation_tools
from src.tools.media_bus_tools import create_media_bus_tools
from src.tools.scheduling import create_scheduling_tools
from src.tools.basic import create_basic_tools
from src.tools.web import create_web_tools
from src.tools.dropbox import create_dropbox_tools
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

    async def create_tools(
        self,
        user_context: UserContext,
        metadata: Optional[Dict] = None,
        user_time_zone: str = 'America/New_York',
        request_id: str = None,
        minimal_tools: bool = False,
        required_tool_ids: Optional[List[str]] = None,
        conversation_manager: ConversationManager = None
    ) -> List:
        """Create tools based on agent configuration by instantiating integration clients.

        Args:
            user_context: User context information
            metadata: Optional metadata dictionary
            user_time_zone: User's timezone
            request_id: Request ID for tracing
            minimal_tools: Legacy parameter - load only core tools (deprecated, use required_tool_ids instead)
            required_tool_ids: List of specific tool function IDs to load. If None, loads all tools.
        """
        tools = []

        user_id = user_context.user_id
        user_email = user_context.user_record.get('email')
        have_email_tool = False
        have_calendar_tool = False
        if not user_id:
            return []

        # Helper function to check if a tool is required
        def is_tool_required(tool_name: str) -> bool:
            if required_tool_ids is None:
                return True  # No filtering, load all tools
            return tool_name in required_tool_ids

        # Helper to check if ANY tool from a category is required
        def needs_category(tool_names: List[str]) -> bool:
            if required_tool_ids is None:
                return True
            return any(tool_name in required_tool_ids for tool_name in tool_names)

        # Get source from metadata for platform messaging tools
        source = metadata.get('source', 'websocket') if metadata else 'websocket'
        conversation_id = str(metadata.get('conversation_id', '')) if metadata else ''

        # Platform Messaging Tools - Create based on planning + source
        # Per implementation plan: Always include source, plus any requested by planner
        try:
            # Find platform messaging tools requested by planner
            requested_platform_tools = []
            if required_tool_ids:
                requested_platform_tools = [
                    tid for tid in required_tool_ids
                    if tid.startswith('reply_to_user_on_')
                ]

            # Extract platform names from tool IDs
            requested_platforms = [
                tid.replace('reply_to_user_on_', '')
                for tid in requested_platform_tools
            ]

            # Always ensure source platform is included
            if source not in requested_platforms:
                requested_platforms.insert(0, source)
            requested_platforms = list(set([p.lower() for p in requested_platforms]))
            logger.info(f"Creating platform messaging tools for: {requested_platforms}")

            # Create a tool for each requested platform
            for platform in requested_platforms:
                try:
                    platform_tool = create_platform_messaging_tools(
                        source=platform,  # Use the requested platform as "source" for tool creation
                        user_id=user_id,
                        metadata=metadata,
                        available_platforms=None,
                        conversation_manager=conversation_manager
                    )
                    tools.extend(platform_tool)
                except Exception as e:
                    logger.warning(f"Could not create tool for platform '{platform}': {e}")
                    # Continue - user might not have access to this platform

            logger.info(f"Added {len([t for t in tools if 'reply_to_user_on_' in getattr(t, 'name', '')])} platform messaging tools")
        except Exception as e:
            logger.error(f"Error creating platform messaging tools: {e}", exc_info=True)

        # Legacy Communication tools (intermediate messages, email, etc.)
        if needs_category(['send_intermediate_message', 'reply_to_user_via_email', 'send_new_email_as_praxos_bot', 'report_bug_to_developers']):
            try:
                tools.extend(create_bot_communication_tools(metadata, user_id))
            except Exception as e:
                logger.error(f"Error creating bot communication tools: {e}", exc_info=True)

        # Media Generation Tools - Conditionally included based on planning
        # Per implementation plan: Planning decides if these are needed
        if needs_category(['generate_image', 'generate_audio', 'generate_video']):
            try:
                if conversation_id:  # Need conversation_id for blob storage organization
                    media_tools = create_media_generation_tools(
                        user_id=user_id,
                        source=source,
                        conversation_id=conversation_id
                    )
                    tools.extend(media_tools)
                    logger.info(f"Added media generation tools for user={user_id}")
                else:
                    logger.warning("Conversation ID not available, skipping media generation tools")
            except Exception as e:
                logger.error(f"Error creating media generation tools: {e}", exc_info=True)

        # Media Bus Tools - ALWAYS included (per implementation plan)
        # Allows agent to reference and build on media
        if conversation_id:  # Only add if we have a conversation context
            try:
                media_bus_tools = create_media_bus_tools(
                    conversation_id=conversation_id,
                    user_id=user_id
                )
                tools.extend(media_bus_tools)
                logger.info(f"Added media bus tools for conversation={conversation_id}")
            except Exception as e:
                logger.error(f"Error creating media bus tools: {e}", exc_info=True)
        else:
            logger.debug("Conversation ID not available, skipping media bus tools")

        # Scheduling tools
        if needs_category(['schedule_task', 'create_recurring_future_task', 'get_scheduled_tasks', 'cancel_scheduled_task', 'update_scheduled_task']):
            try:
                tools.extend(create_scheduling_tools(user_id, metadata.get('source'), str(metadata.get('conversation_id'))))
            except Exception as e:
                logger.error(f"Error creating scheduling tools: {e}", exc_info=True)

        # Basic tools, always include
        if True:
            try:
                tools.extend(create_basic_tools(user_time_zone))
            except Exception as e:
                logger.error(f"Error creating basic tools: {e}", exc_info=True)

        # Preference tools: this should always be included, as these are essential for user customization
        if True or needs_category(['add_user_preference_annotation', 'set_assistant_name', 'set_timezone', 'set_language_response', 'delete_user_preference_annotations']):
            try:
                tools.extend(create_preference_tools(user_id))
            except Exception as e:
                logger.error(f"Error creating preference tools: {e}", exc_info=True)

        # Integration tools
        if needs_category(['get_oauth_initiation_url']):
            try:
                tools.extend(create_integration_tools(user_id))
                logger.info("Integration tools created successfully.")
            except Exception as e:
                logger.error(f"Error creating integration tools: {e}", exc_info=True)

        # Database tools
        if needs_category(['fetch_latest_messages', 'get_user_integration_records']):
            try:
                tools.extend(create_database_access_tools(user_id))
            except Exception as e:
                logger.error(f"Error creating database access tools: {e}", exc_info=True)

        # Google Search
        if is_tool_required('google_search'):
            try:
                search = GoogleSearchAPIWrapper()
                tools.append(Tool(name="google_search", description="Search Google for recent results.", func=search.run))
            except Exception as e:
                logger.error(f"Error creating Google search tool: {e}", exc_info=True)

        # Google Places
        if is_tool_required('GooglePlacesTool'):
            try:
                tools.append(GooglePlacesTool())
            except Exception as e:
                logger.error(f"Error creating Google places tool: {e}", exc_info=True)

        # Google Lens
        if is_tool_required('identify_product_in_image'):
            try:
                tools.extend(create_google_lens_tools())
                logger.info("Google Lens product recognition tools created successfully.")
            except Exception as e:
                logger.error(f"Error creating Google Lens tools: {e}", exc_info=True)

        # Web tools: if google search or places is needed, also load web browsing
        if needs_category(['read_webpage_content', 'browse_website_with_ai','google_search','GooglePlacesTool']):
            try:
                tools.extend(create_web_tools(request_id, user_id, metadata))
                logger.info("Web tools created successfully.")
            except Exception as e:
                logger.error(f"Error creating web tools: {e}", exc_info=True)



        # Legacy minimal_tools mode - return early if set
        if minimal_tools:
            return tools

        # Determine which integrations need authentication based on required tools
        needs_gmail = needs_category(['send_email', 'get_emails_from_sender', 'find_contact_email', 'search_gmail'])
        needs_gcal = needs_category(['get_calendar_events', 'create_calendar_event'])
        needs_gdrive = needs_category(['search_google_drive_files', 'save_file_to_drive', 'create_text_file_in_drive', 'read_file_content_by_id', 'list_drive_files'])
        needs_outlook = needs_category(['send_outlook_email', 'fetch_outlook_calendar_events', 'get_outlook_emails_from_sender', 'find_outlook_contact_email'])
        needs_notion = needs_category(['list_databases', 'list_notion_pages', 'query_notion_database', 'get_all_workspace_entries', 'search_notion_pages_by_keyword', 'create_notion_page', 'create_notion_database_entry', 'create_notion_database', 'append_to_notion_page', 'update_notion_page_properties', 'get_notion_page_content'])
        needs_dropbox = needs_category(['save_file_to_dropbox', 'read_file_from_dropbox','list_dropbox_files','search_dropbox_files'])
        needs_trello = needs_category(['list_trello_accounts','list_trello_organizations','list_trello_boards','get_trello_board_details','create_trello_board','share_trello_board','create_trello_list','list_trello_cards','get_trello_card','create_trello_card','update_trello_card','move_trello_card','add_trello_comment','create_trello_checklist','get_board_members','get_card_members','assign_member_to_card','unassign_member_from_card','search_trello']) 
         # If no specific tools requested, authenticate all (backward compatibility)
        if required_tool_ids is None:
            needs_gmail = needs_gcal = needs_gdrive = needs_outlook = needs_notion = needs_dropbox = needs_trello = True

        # Only authenticate integrations that are actually needed
        auth_tasks = []
        integration_map = {}

        if needs_gcal:
            gcal_integration = GoogleCalendarIntegration(user_id)
            auth_tasks.append(gcal_integration.authenticate())
            integration_map['gcal'] = (len(auth_tasks) - 1, gcal_integration)

        if needs_gmail:
            gmail_integration = GmailIntegration(user_id)
            auth_tasks.append(gmail_integration.authenticate())
            integration_map['gmail'] = (len(auth_tasks) - 1, gmail_integration)

        if needs_gdrive:
            gdrive_integration = GoogleDriveIntegration(user_id)
            auth_tasks.append(gdrive_integration.authenticate())
            integration_map['gdrive'] = (len(auth_tasks) - 1, gdrive_integration)

        if needs_outlook:
            outlook_integration = MicrosoftGraphIntegration(user_id)
            auth_tasks.append(outlook_integration.authenticate())
            integration_map['outlook'] = (len(auth_tasks) - 1, outlook_integration)

        if needs_notion:
            notion_integration = NotionIntegration(user_id)
            auth_tasks.append(notion_integration.authenticate())
            integration_map['notion'] = (len(auth_tasks) - 1, notion_integration)

        if needs_dropbox:
            dropbox_integration = DropboxIntegration(user_id)
            auth_tasks.append(dropbox_integration.authenticate())
            integration_map['dropbox'] = (len(auth_tasks) - 1, dropbox_integration)

        if needs_trello:
            trello_integration = TrelloIntegration(user_id)
            auth_tasks.append(trello_integration.authenticate())
            integration_map['trello'] = (len(auth_tasks) - 1, trello_integration)

        logger.info(f"Authenticating {len(auth_tasks)} integrations based on required tools")

        # Authenticate only the needed integrations
        if auth_tasks:
            authenticated_integrations = await asyncio.gather(*auth_tasks, return_exceptions=True)
        else:
            authenticated_integrations = []

        # Load tools for authenticated integrations
        if 'gcal' in integration_map:
            idx, gcal_integration = integration_map['gcal']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_calendar_tools(gcal_integration,user_time_zone))
                    have_calendar_tool = True
                    logger.info("Google Calendar tools loaded")
                except Exception as e:
                    logger.error(f"Error creating calendar tools: {e}", exc_info=True)

        if 'gmail' in integration_map:
            idx, gmail_integration = integration_map['gmail']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_gmail_tools(gmail_integration))
                    have_email_tool = True
                    logger.info("Gmail tools loaded")
                except Exception as e:
                    logger.error(f"Error creating email tools: {e}", exc_info=True)

        if 'gdrive' in integration_map:
            idx, gdrive_integration = integration_map['gdrive']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_drive_tools(gdrive_integration))
                    logger.info("Google Drive tools loaded")
                except Exception as e:
                    logger.error(f"Error creating drive tools: {e}", exc_info=True)

        if 'outlook' in integration_map:
            idx, outlook_integration = integration_map['outlook']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_outlook_tools(outlook_integration))
                    have_email_tool = True
                    have_calendar_tool = True
                    logger.info("Outlook tools loaded")
                except Exception as e:
                    logger.error(f"Error creating Outlook tools: {e}", exc_info=True)

        if 'notion' in integration_map:
            idx, notion_integration = integration_map['notion']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_notion_tools(notion_integration))
                    logger.info("Notion tools loaded")
                except Exception as e:
                    logger.error(f"Error creating Notion tools: {e}", exc_info=True)

        if 'dropbox' in integration_map:
            idx, dropbox_integration = integration_map['dropbox']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_dropbox_tools(dropbox_integration))
                    logger.info("Dropbox tools loaded")
                except Exception as e:
                    logger.error(f"Error creating Dropbox tools: {e}", exc_info=True)

        if 'trello' in integration_map:
            idx, trello_integration = integration_map['trello']
            if authenticated_integrations[idx] is True:
                try:
                    tools.extend(create_trello_tools(trello_integration))
                    logger.info("Trello tools loaded")
                except Exception as e:
                    logger.error(f"Error creating Trello tools: {e}", exc_info=True)

        # --- Praxos Memory Tools ---
        if needs_category(['query_praxos_memory', 'query_praxos_memory_intelligent_search', 'enrich_praxos_memory_entries', 'setup_new_trigger','consult_praxos_long_term_memory']):
            from src.config.settings import settings
            if settings.OPERATING_MODE == "local":
                praxos_api_key = settings.PRAXOS_API_KEY
            else:
                praxos_api_key = user_context.user_record.get("praxos_api_key")

            if praxos_api_key:
                praxos_client = PraxosClient(f"env_for_{user_email}", api_key=praxos_api_key)
                tools.extend(create_praxos_memory_tool(praxos_client, user_id, str(metadata.get('conversation_id'))))
                logger.info("Praxos memory tools loaded")
            else:
                logger.warning("Praxos API key not found, memory tools will be unavailable.")

        # --- Google Lens Tools (Product/Brand Recognition via SerpAPI) ---

        
        # --- External API Tools ---




        return tools
