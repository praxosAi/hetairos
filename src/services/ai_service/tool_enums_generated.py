"""
Auto-generated tool enum from YAML definitions.
DO NOT EDIT - Run: python scripts/generate_tool_artifacts.py --enum

Generated from: src/tools/definitions/
Tool count: 160
Version hash: 5f8de784e8de
"""

from enum import Enum

# This enum is auto-generated from src/tools/tool_database.yaml
# DO NOT EDIT MANUALLY - Run: python scripts/generate_tool_artifacts.py --enum

class ToolFunctionID(str, Enum):

    # Basic tools
    GET_CURRENT_TASK_PLAN_AND_STEP = "get_current_task_plan_and_step"
    GET_CURRENT_TIME = "get_current_time"

    # Communication tools
    CREATE_IOS_REMINDER = "create_ios_reminder"
    EXECUTE_IOS_SHORTCUT = "execute_ios_shortcut"
    REPLY_TO_USER_VIA_EMAIL = "reply_to_user_via_email"
    REPORT_BUG_TO_DEVELOPERS = "report_bug_to_developers"
    SEND_INTERMEDIATE_MESSAGE = "send_intermediate_message"
    SEND_NEW_EMAIL_AS_PRAXOS_BOT = "send_new_email_as_praxos_bot"
    SEND_TEXT_VIA_IOS = "send_text_via_ios"

    # Database tools
    FETCH_LATEST_MESSAGES = "fetch_latest_messages"
    GET_USER_INTEGRATION_RECORDS = "get_user_integration_records"

    # Discord tools
    GET_DISCORD_CHANNEL_HISTORY = "get_discord_channel_history"
    GET_DISCORD_USER_INFO = "get_discord_user_info"
    LIST_DISCORD_CHANNELS = "list_discord_channels"
    LIST_DISCORD_SERVERS = "list_discord_servers"
    SEND_DISCORD_DM = "send_discord_dm"
    SEND_DISCORD_MESSAGE = "send_discord_message"

    # Dropbox tools
    LIST_DROPBOX_ACCOUNTS = "list_dropbox_accounts"
    LIST_DROPBOX_FILES = "list_dropbox_files"
    READ_FILE_FROM_DROPBOX = "read_file_from_dropbox"
    SAVE_FILE_TO_DROPBOX = "save_file_to_dropbox"
    SEARCH_DROPBOX_FILES = "search_dropbox_files"

    # Example tools
    EXAMPLE_TOOL = "example_tool"

    # Gmail tools
    ADD_LABEL_TO_EMAIL = "add_label_to_email"
    ARCHIVE_EMAIL = "archive_email"
    CREATE_EMAIL_DRAFT = "create_email_draft"
    FIND_CONTACT_EMAIL = "find_contact_email"
    GET_EMAIL_CONTENT = "get_email_content"
    GET_EMAILS_FROM_SENDER = "get_emails_from_sender"
    LIST_GMAIL_LABELS = "list_gmail_labels"
    MARK_EMAIL_AS_READ = "mark_email_as_read"
    MARK_EMAIL_AS_UNREAD = "mark_email_as_unread"
    MOVE_EMAIL_TO_SPAM = "move_email_to_spam"
    MOVE_EMAIL_TO_TRASH = "move_email_to_trash"
    REMOVE_LABEL_FROM_EMAIL = "remove_label_from_email"
    REPLY_TO_EMAIL = "reply_to_email"
    SEARCH_GMAIL = "search_gmail"
    SEND_EMAIL = "send_email"
    STAR_EMAIL = "star_email"
    UNSTAR_EMAIL = "unstar_email"

    # Google_Calendar tools
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    GET_CALENDAR_EVENTS = "get_calendar_events"

    # Google_Docs tools
    APPEND_TEXT_TO_DOC = "append_text_to_doc"
    CREATE_GOOGLE_DOC = "create_google_doc"
    DELETE_DOC_CONTENT = "delete_doc_content"
    FORMAT_DOC_TEXT = "format_doc_text"
    GET_GOOGLE_DOC_CONTENT = "get_google_doc_content"
    INSERT_PARAGRAPH_IN_DOC = "insert_paragraph_in_doc"
    INSERT_TABLE_IN_DOC = "insert_table_in_doc"
    INSERT_TEXT_IN_DOC = "insert_text_in_doc"
    REPLACE_TEXT_IN_DOC = "replace_text_in_doc"
    SEARCH_GOOGLE_DOC = "search_google_doc"

    # Google_Drive tools
    CREATE_TEXT_FILE_IN_DRIVE = "create_text_file_in_drive"
    LIST_DRIVE_FILES = "list_drive_files"
    READ_FILE_CONTENT_BY_ID = "read_file_content_by_id"
    SAVE_FILE_TO_DRIVE = "save_file_to_drive"
    SEARCH_GOOGLE_DRIVE_FILES = "search_google_drive_files"

    # Google_Lens tools
    IDENTIFY_PRODUCT_IN_IMAGE = "identify_product_in_image"

    # Google_Places tools
    GOOGLE_PLACES_FIND_PLACE = "google_places_find_place"
    GOOGLE_PLACES_GET_DETAILS = "google_places_get_details"
    GOOGLE_PLACES_NEARBY_SEARCH = "google_places_nearby_search"
    GOOGLE_PLACES_TEXT_SEARCH = "google_places_text_search"

    # Google_Sheets tools
    ADD_SHEET_TAB = "add_sheet_tab"
    APPEND_SHEET_ROWS = "append_sheet_rows"
    CLEAR_SHEET_RANGE = "clear_sheet_range"
    CREATE_GOOGLE_SHEET = "create_google_sheet"
    DELETE_SHEET_ROWS = "delete_sheet_rows"
    DELETE_SHEET_TAB = "delete_sheet_tab"
    GET_SHEET_VALUES = "get_sheet_values"
    GET_SINGLE_CELL = "get_single_cell"
    GET_SPREADSHEET_INFO = "get_spreadsheet_info"
    INSERT_SHEET_COLUMNS = "insert_sheet_columns"
    INSERT_SHEET_ROWS = "insert_sheet_rows"
    SEARCH_GOOGLE_SHEET = "search_google_sheet"
    SET_SINGLE_CELL = "set_single_cell"
    UPDATE_SHEET_VALUES = "update_sheet_values"

    # Google_Slides tools
    ADD_SLIDE = "add_slide"
    CREATE_GOOGLE_PRESENTATION = "create_google_presentation"
    CREATE_TABLE_IN_SLIDE = "create_table_in_slide"
    DELETE_SLIDE = "delete_slide"
    DELETE_SLIDE_OBJECT = "delete_slide_object"
    FORMAT_SLIDE_TEXT = "format_slide_text"
    GET_PRESENTATION_INFO = "get_presentation_info"
    INSERT_IMAGE_IN_SLIDE = "insert_image_in_slide"
    INSERT_TEXT_IN_SLIDE = "insert_text_in_slide"
    SEARCH_GOOGLE_PRESENTATION = "search_google_presentation"

    # Integration tools
    GET_OAUTH_INITIATION_URL = "get_oauth_initiation_url"

    # Media_Bus tools
    GET_MEDIA_BY_ID = "get_media_by_id"
    GET_RECENT_IMAGES = "get_recent_images"
    LIST_AVAILABLE_MEDIA = "list_available_media"

    # Media_Generation tools
    GENERATE_AUDIO = "generate_audio"
    GENERATE_IMAGE = "generate_image"
    GENERATE_VIDEO = "generate_video"

    # Microsoft_Graph tools
    FETCH_OUTLOOK_CALENDAR_EVENTS = "fetch_outlook_calendar_events"
    FIND_OUTLOOK_CONTACT_EMAIL = "find_outlook_contact_email"
    GET_OUTLOOK_EMAILS_FROM_SENDER = "get_outlook_emails_from_sender"
    SEND_OUTLOOK_EMAIL = "send_outlook_email"

    # Notion tools
    APPEND_TO_NOTION_PAGE = "append_to_notion_page"
    CREATE_NOTION_DATABASE = "create_notion_database"
    CREATE_NOTION_DATABASE_ENTRY = "create_notion_database_entry"
    CREATE_NOTION_PAGE = "create_notion_page"
    GET_ALL_WORKSPACE_ENTRIES = "get_all_workspace_entries"
    GET_NOTION_PAGE_CONTENT = "get_notion_page_content"
    LIST_DATABASES = "list_databases"
    LIST_NOTION_PAGES = "list_notion_pages"
    LIST_NOTION_WORKSPACES = "list_notion_workspaces"
    QUERY_NOTION_DATABASE = "query_notion_database"
    SEARCH_NOTION_PAGES_BY_KEYWORD = "search_notion_pages_by_keyword"
    UPDATE_NOTION_PAGE_PROPERTIES = "update_notion_page_properties"

    # Praxos_Memory tools
    CHECK_CONNECTED_INTEGRATIONS = "check_connected_integrations"
    DELETE_FROM_KNOWLEDGE_GRAPH = "delete_from_knowledge_graph"
    ENRICH_PRAXOS_MEMORY_ENTRIES = "enrich_praxos_memory_entries"
    EXTRACT_ENTITIES_BY_TYPE = "extract_entities_by_type"
    EXTRACT_LITERALS_BY_TYPE = "extract_literals_by_type"
    GET_ENTITIES_BY_TYPE_NAME = "get_entities_by_type_name"
    QUERY_PRAXOS_MEMORY = "query_praxos_memory"
    QUERY_PRAXOS_MEMORY_INTELLIGENT_SEARCH = "query_praxos_memory_intelligent_search"
    SETUP_NEW_TRIGGER = "setup_new_trigger"
    STORE_NEW_ENTITY_IN_KNOWLEDGE_GRAPH = "store_new_entity_in_knowledge_graph"
    UPDATE_ENTITY_PROPERTIES_IN_KNOWLEDGE_GRAPH = "update_entity_properties_in_knowledge_graph"
    UPDATE_KNOWLEDGE_GRAPH_LITERAL = "update_knowledge_graph_literal"

    # Preference tools
    ADD_USER_PREFERENCE_ANNOTATION = "add_user_preference_annotation"
    DELETE_USER_PREFERENCE_ANNOTATIONS = "delete_user_preference_annotations"
    GET_USER_LOCATION = "get_user_location"
    GET_USER_LOCATION_HISTORY = "get_user_location_history"
    SET_ASSISTANT_NAME = "set_assistant_name"
    SET_LANGUAGE_RESPONSE = "set_language_response"
    SET_TIMEZONE = "set_timezone"

    # Scheduling tools
    CREATE_RECURRING_FUTURE_TASK = "create_recurring_future_task"
    GET_SCHEDULED_TASKS = "get_scheduled_tasks"
    SCHEDULE_TASK = "schedule_task"
    UPDATE_SCHEDULED_TASK = "update_scheduled_task"

    # Slack tools
    GET_SLACK_CHANNEL_HISTORY = "get_slack_channel_history"
    GET_SLACK_USER_INFO = "get_slack_user_info"
    LIST_SLACK_CHANNELS = "list_slack_channels"
    LIST_SLACK_WORKSPACES = "list_slack_workspaces"
    SEND_SLACK_DM = "send_slack_dm"
    SEND_SLACK_MESSAGE = "send_slack_message"

    # Trello tools
    ADD_TRELLO_COMMENT = "add_trello_comment"
    ASSIGN_MEMBER_TO_CARD = "assign_member_to_card"
    CREATE_TRELLO_BOARD = "create_trello_board"
    CREATE_TRELLO_CARD = "create_trello_card"
    CREATE_TRELLO_CHECKLIST = "create_trello_checklist"
    CREATE_TRELLO_LIST = "create_trello_list"
    GET_BOARD_MEMBERS = "get_board_members"
    GET_CARD_MEMBERS = "get_card_members"
    GET_TRELLO_BOARD_DETAILS = "get_trello_board_details"
    GET_TRELLO_CARD = "get_trello_card"
    LIST_TRELLO_ACCOUNTS = "list_trello_accounts"
    LIST_TRELLO_BOARDS = "list_trello_boards"
    LIST_TRELLO_CARDS = "list_trello_cards"
    LIST_TRELLO_ORGANIZATIONS = "list_trello_organizations"
    MOVE_TRELLO_CARD = "move_trello_card"
    SEARCH_TRELLO = "search_trello"
    SHARE_TRELLO_BOARD = "share_trello_board"
    UNASSIGN_MEMBER_FROM_CARD = "unassign_member_from_card"
    UPDATE_TRELLO_CARD = "update_trello_card"

    # Web tools
    BROWSE_WEBSITE_WITH_AI = "browse_website_with_ai"
    GOOGLE_SEARCH = "google_search"
    READ_WEBPAGE_CONTENT = "read_webpage_content"
