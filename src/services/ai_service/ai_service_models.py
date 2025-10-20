from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

# Enum for all available tool function IDs
class ToolFunctionID(str, Enum):
    # Communication tools
    SEND_INTERMEDIATE_MESSAGE = "send_intermediate_message"
    REPLY_TO_USER_VIA_EMAIL = "reply_to_user_via_email"
    SEND_NEW_EMAIL_AS_PRAXOS_BOT = "send_new_email_as_praxos_bot"
    REPORT_BUG_TO_DEVELOPERS = "report_bug_to_developers"

    # Platform messaging tools (dynamically generated per platform)
    REPLY_TO_USER_ON_WHATSAPP = "reply_to_user_on_whatsapp"
    REPLY_TO_USER_ON_TELEGRAM = "reply_to_user_on_telegram"
    REPLY_TO_USER_ON_IMESSAGE = "reply_to_user_on_imessage"
    REPLY_TO_USER_ON_DISCORD = "reply_to_user_on_discord"
    REPLY_TO_USER_ON_SLACK = "reply_to_user_on_slack"
    REPLY_TO_USER_ON_WEBSOCKET = "reply_to_user_on_websocket"

    # Media generation tools
    GENERATE_IMAGE = "generate_image"
    GENERATE_AUDIO = "generate_audio"
    GENERATE_VIDEO = "generate_video"

    # Media bus tools
    LIST_AVAILABLE_MEDIA = "list_available_media"
    GET_MEDIA_BY_ID = "get_media_by_id"
    GET_RECENT_IMAGES = "get_recent_images"

    # Scheduling tools
    SCHEDULE_TASK = "schedule_task"
    CREATE_RECURRING_FUTURE_TASK = "create_recurring_future_task"
    GET_SCHEDULED_TASKS = "get_scheduled_tasks"
    CANCEL_SCHEDULED_TASK = "cancel_scheduled_task"
    UPDATE_SCHEDULED_TASK = "update_scheduled_task"

    # Basic tools
    GET_CURRENT_TIME = "get_current_time"
    GET_CURRENT_TASK_PLAN_AND_STEP = "get_current_task_plan_and_step"
    ASK_USER_FOR_MISSING_PARAMS = "ask_user_for_missing_params"
    CONSULT_DEFAULTS_AND_PREFERENCES_FOR_MISSING_PARAMS = "consult_defaults_and_preferences_for_missing_params"
    CONSULT_PRAXOS_LONG_TERM_MEMORY = "consult_praxos_long_term_memory"
    # Preference tools
    ADD_USER_PREFERENCE_ANNOTATION = "add_user_preference_annotation"
    SET_ASSISTANT_NAME = "set_assistant_name"
    SET_TIMEZONE = "set_timezone"
    SET_LANGUAGE_RESPONSE = "set_language_response"
    DELETE_USER_PREFERENCE_ANNOTATIONS = "delete_user_preference_annotations"

    # Integration tools
    GET_OAUTH_INITIATION_URL = "get_oauth_initiation_url"

    # Database tools
    FETCH_LATEST_MESSAGES = "fetch_latest_messages"
    GET_USER_INTEGRATION_RECORDS = "get_user_integration_records"

    # Gmail tools
    SEND_EMAIL = "send_email"
    GET_EMAILS_FROM_SENDER = "get_emails_from_sender"
    FIND_CONTACT_EMAIL = "find_contact_email"
    SEARCH_GMAIL = "search_gmail"

    # Google Calendar tools
    GET_CALENDAR_EVENTS = "get_calendar_events"
    CREATE_CALENDAR_EVENT = "create_calendar_event"

    # Google Drive tools
    SEARCH_GOOGLE_DRIVE_FILES = "search_google_drive_files"
    SAVE_FILE_TO_DRIVE = "save_file_to_drive"
    CREATE_TEXT_FILE_IN_DRIVE = "create_text_file_in_drive"
    READ_FILE_CONTENT_BY_ID = "read_file_content_by_id"
    LIST_DRIVE_FILES = "list_drive_files"

    # Microsoft Outlook tools
    SEND_OUTLOOK_EMAIL = "send_outlook_email"
    FETCH_OUTLOOK_CALENDAR_EVENTS = "fetch_outlook_calendar_events"
    GET_OUTLOOK_EMAILS_FROM_SENDER = "get_outlook_emails_from_sender"
    FIND_OUTLOOK_CONTACT_EMAIL = "find_outlook_contact_email"

    # Notion tools
    LIST_DATABASES = "list_databases"
    LIST_NOTION_PAGES = "list_notion_pages"
    QUERY_NOTION_DATABASE = "query_notion_database"
    GET_ALL_WORKSPACE_ENTRIES = "get_all_workspace_entries"
    SEARCH_NOTION_PAGES_BY_KEYWORD = "search_notion_pages_by_keyword"
    CREATE_NOTION_PAGE = "create_notion_page"
    CREATE_NOTION_DATABASE_ENTRY = "create_notion_database_entry"
    CREATE_NOTION_DATABASE = "create_notion_database"
    APPEND_TO_NOTION_PAGE = "append_to_notion_page"
    UPDATE_NOTION_PAGE_PROPERTIES = "update_notion_page_properties"
    GET_NOTION_PAGE_CONTENT = "get_notion_page_content"

    # Dropbox tools
    SAVE_FILE_TO_DROPBOX = "save_file_to_dropbox"
    READ_FILE_FROM_DROPBOX = "read_file_from_dropbox"
    LIST_DROPBOX_FILES = "list_dropbox_files"
    SEARCH_DROPBOX_FILES = "search_dropbox_files"
    # Trello tools
    LIST_TRELLO_ORGANIZATIONS = "list_trello_organizations"
    LIST_TRELLO_BOARDS = "list_trello_boards"
    GET_TRELLO_BOARD_DETAILS = "get_trello_board_details"
    LIST_TRELLO_CARDS = "list_trello_cards"
    CREATE_TRELLO_CARD = "create_trello_card"
    UPDATE_TRELLO_CARD = "update_trello_card"
    MOVE_TRELLO_CARD = "move_trello_card"
    ADD_TRELLO_COMMENT = "add_trello_comment"  # Corrected from add_comment_to_trello_card
    SEARCH_TRELLO = "search_trello"

    # Newly added to complete the list
    LIST_TRELLO_ACCOUNTS = "list_trello_accounts"
    GET_TRELLO_CARD = "get_trello_card"
    CREATE_TRELLO_BOARD = "create_trello_board"
    SHARE_TRELLO_BOARD = "share_trello_board"
    CREATE_TRELLO_LIST = "create_trello_list"
    CREATE_TRELLO_CHECKLIST = "create_trello_checklist"
    GET_BOARD_MEMBERS = "get_board_members"
    GET_CARD_MEMBERS = "get_card_members"
    ASSIGN_MEMBER_TO_CARD = "assign_member_to_card"
    UNASSIGN_MEMBER_FROM_CARD = "unassign_member_from_card"

    # Web tools
    READ_WEBPAGE_CONTENT = "read_webpage_content"
    BROWSE_WEBSITE_WITH_AI = "browse_website_with_ai"

    # Search tools
    GOOGLE_SEARCH = "google_search"
    GOOGLE_PLACES = "GooglePlacesTool"  # This uses a different tool format

    # Google Lens tools
    IDENTIFY_PRODUCT_IN_IMAGE = "identify_product_in_image"

    # Praxos memory tools
    QUERY_PRAXOS_MEMORY = "query_praxos_memory"
    QUERY_PRAXOS_MEMORY_INTELLIGENT_SEARCH = "query_praxos_memory_intelligent_search"
    ENRICH_PRAXOS_MEMORY_ENTRIES = "enrich_praxos_memory_entries"
    SETUP_NEW_TRIGGER = "setup_new_trigger"

class BooleanResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the boolean response.")
    response: bool = Field(..., description="A boolean response indicating true or false.")


class StringResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the string response.")
    response: str = Field(..., description="A string response.")

class PlanningResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the planning response.")
    query_type: str = Field(..., description="The type of query: namely, 'command' or 'conversational'.",enum=['command', 'conversational'])
    tooling_need: bool = Field(..., description="Indicates whether external tools are needed to achieve the goal.")
    plan: str = Field(..., description="A detailed plan outlining the steps to achieve the goal, IF it's a command and tooling is needed.")
    steps: List[str] = Field(..., description="A list of actionable steps derived from the plan. Each step should be concise and clear. Not needed if it's a conversational query without tooling.")

class GranularPlanningResponse(BaseModel):
    """Enhanced planning response with specific tool function IDs."""
    reason: str = Field(..., description="A short reason for the planning decision.")
    query_type: str = Field(..., description="The type of query: 'command' or 'conversational'.", enum=['command', 'conversational'])
    tooling_need: bool = Field(False, description="Indicates whether external tools are needed.")
    required_tools: List[ToolFunctionID] = Field(
        default_factory=list,
        description="Specific tool function IDs required for this task. Only include tools that are ACTUALLY needed. Be precise and minimal."
    )
    missing_data_for_tools: Optional[bool] = Field(False, description="Indicates if any required data for the tools is missing.")
    plan: Optional[str] = Field(None, description="A detailed plan outlining the steps, if needed.")
    steps: Optional[List[str]] = Field(default_factory=list, description="Actionable steps for the task.")