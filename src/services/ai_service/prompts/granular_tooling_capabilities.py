
### NOTE: WE ARE NOT USING THIS IN THIS FORM, INSTEAD USING A CACHED TOOL. THIS IMPROVES LATENCY. NOTE THAT EDITTING THIS DOES EXACTLY NOTHING, but you may cache it for yourself and change the cache name in the adjacent caches.py file.
### IMPORTANT UPDATE (Phase 1-3 Implementation):
### This file has been updated with new tools:
###  - Platform messaging tools (reply_to_user_on_whatsapp, reply_to_user_on_telegram, reply_to_user_on_imessage)
###  - Media generation tools (generate_image, generate_audio, generate_video)
###  - Media bus tools (list_available_media, get_media_by_id, get_recent_images)
###  - Location tools (get_user_location, get_user_location_history)
###  - Google Places tools suite (google_places_text_search, google_places_nearby_search, google_places_find_place, google_places_get_details)
###  - Location parameters added to reply tools (request_location, send_location_*)
### THE GOOGLE GEMINI CACHE MUST BE REGENERATED FOR THESE CHANGES TO TAKE EFFECT!
### After regeneration, update the cache ID in caches.py: PLANNING_CACHE_NAME

"""
Granular tooling capabilities with specific function IDs and descriptions.
Used by the granular planning agent to select precise tools needed for each task.
"""

GRANULAR_TOOLING_CAPABILITIES = """
## Available Tool Functions

Below is a comprehensive list of ALL available tool functions with their IDs and descriptions.
**IMPORTANT**: Only include tools that are ACTUALLY needed for the task. Be precise and minimal.


**IMPORTANT**: we do not consider capabilities such as "Transcribing the contents" of an image, 'Translating the contents' of an email, 'transcribing an audio file', or 'summarizing a document' as separate tools. These are capabilities that are part of the core AI functionality, and do not require a separate tool. The tools listed here are for external integrations, or for specific actions that require a distinct function call. Such capabilities can be handled by the AI directly, without needing to invoke a separate tool.

**IMPORTANT - MEDIA GENERATION**: Generating videos, images, or audio IS now available as explicit tool functionality. When the user requests media generation, you MUST include the appropriate generation tools (generate_image, generate_audio, generate_video) in your planning. The agent will use these tools to create media and send it to the user.

**IMPORTANT - MESSAGING**: The agent now has direct messaging tools for each platform (reply_to_user_on_whatsapp, reply_to_user_on_telegram, etc.). These tools are ALWAYS available for the source platform and allow the agent to send messages directly during execution. The agent MUST use these tools to communicate responses to the user.

---

### Platform Messaging Tools

**reply_to_user_on_whatsapp**
- Send WhatsApp messages to the user with optional media attachments
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users on WhatsApp
- Can send multiple messages during execution
- Supports text-only or text with media (images, audio, video, documents) or a location pin
- Supports requesting location from user, via an interactive button
**reply_to_user_on_telegram**
- Send Telegram messages to the user with optional media attachments
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users on Telegram
- Can send multiple messages during execution
- Supports text-only or text with media or a location pin
- Supports requesting location from user, via an interactive button

**reply_to_user_on_imessage**
- Send iMessages to the user with optional media attachments
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users via iMessage
- Can send multiple messages during execution
- Supports text-only or text with media or a location pin
- Supports requesting location from user, via sending a text message prompt.

**reply_to_user_on_discord**
- Send Discord messages to the user with optional media attachments
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users on Discord
- Can send multiple messages during execution
- Supports text-only or text with media

**reply_to_user_on_slack**
- Send Slack messages to the user with optional media attachments
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users on Slack
- Can send multiple messages during execution
- Supports text-only or text with media

**reply_to_user_on_websocket**
- Send messages to the user via websocket connection
- Args: message (str), media_urls (optional list), media_types (optional list)
- Use this for responses to users connected via websocket
- Can send multiple messages during execution
- Supports text-only or text with media

**NOTE**: These platform messaging tools are always available. The system will automatically filter out tools for platforms the user cannot access. Always include the appropriate platform tool for the user's source channel in your required_tools list.

---

### Media Generation Tools

**generate_image**
- Generates images from text descriptions using Gemini 2.5 Flash, or edits existing images/variations
- Args: prompt (detailed description), media_ids (optional, when the user wants to edit/modify an existing image or use it as a base for variations)
- Use when: User requests image creation or visual content
- Returns: URL, file_name, file_type, media_id
- Generated image is automatically added to media bus
- Example: "Generate an image of a sunset over mountains"
- Tips: Be specific about style, colors, composition, mood

**generate_audio**
- Generates audio/speech from text using Gemini 2.5 Flash TTS
- Args: text (content to convert), voice (optional, reserved for future)
- Use when: User requests audio/voice output or TTS
- Returns: URL, file_name, file_type, media_id
- Audio format automatically adapted for platform (CAF for iMessage, OGG for others)
- Generated audio is automatically added to media bus

**generate_video**
- Generates videos from text descriptions using Veo 3.1. can use existing images as an input base.
- Args: prompt (detailed scene description), media_ids (optional, when the user wants to use existing images as a base for the video)
- Use when: User requests video generation
- WARNING: SLOW operation (1-2 minutes)
- ALWAYS use send_intermediate_message BEFORE calling this tool
- Returns: URL, file_name, file_type, media_id
- Generated video is automatically added to media bus
- Example: "Generate a video of a time-lapse flower blooming"

**MEDIA WORKFLOW**:
1. Use generate_image/audio/video to create media
2. Get URL from tool result
3. Use reply_to_user_on_platform with media_urls and media_types to send to user
4. Media is also added to media bus for future reference

---

### Media Bus Tools (ALWAYS AVAILABLE)

**list_available_media**
- Lists media generated or received during current conversation
- Args: media_type (optional: image/audio/video/document), limit (default 10)
- Use when: Need to see what media exists in conversation
- Returns: Formatted list with IDs, descriptions, file names, URLs
- Helps agent reference previous media

**get_media_by_id**
- Retrieves specific media by ID and loads into conversation context
- Args: media_id (from list_available_media)
- Use when: Need to reference or analyze previously generated media
- For images: Loads into visual context so agent can "see" it
- For audio/video: Provides description
- Returns: URL, file_name, file_type, description for sending to user
- IMPORTANT: This allows agent to see media and create variations

**get_recent_images**
- Quick access to recently generated/uploaded images
- Args: limit (default 5)
- Use when: Need to reference recent images without full list
- Returns: Image IDs, descriptions, URLs
- Useful for creating variations or referencing previous generations

**NOTE**: Media bus tools are ALWAYS included automatically. Do not explicitly list them in required_tools.

---

### Communication Tools

**send_intermediate_message**
- Sends status updates to users during long-running operations (30+ seconds)
- Use for: Web browsing, media generation, long searches
- DO NOT use for simple tasks that complete quickly
- DO NOT use this if the only task is to send a message. the output will be automatically sent at the end of execution. Thus, this is only for long-running tasks where you want to keep the user informed while you work, not for simply sending a message to the user.
- Example: "I'm browsing that website now, this will take about 30 seconds..."
- DO NOT USE IF the task is to simply send the user to the message right now, without any other long-running task. in that case, we will simply provide the message as the final response.

**reply_to_user_via_email**
- Replies to a user's email using the Praxos bot
- Use when: User sent an email and you need to reply to it
- The system handles the reply-to address automatically

**send_new_email_as_praxos_bot**
- Sends a new email as the Praxos assistant (not a reply)
- Args: recipients (list), subject, body
- Use when: User requests sending an email to someone

**report_bug_to_developers**
- Reports bugs or issues to the development team
- Use when: Encountering errors, unexpected behavior, or system issues
- Args: bug_description, additional_context (optional)

---

### Scheduling & Automation Tools

**schedule_task**
- Schedules a one-time future task
- Args: time_to_do (datetime), command_to_perform, delivery_platform
- Use for: "Remind me at 3pm", "Send email tomorrow at 9am"
- Supports: whatsapp, telegram, email, imessage delivery

**create_recurring_future_task**
- Schedules recurring tasks with cron expressions
- Args: cron_expression, cron_description, command_to_perform, start_time, delivery_platform, end_time (optional)
- Use for: "Every Monday at 9am", "Daily at 6pm"
- Examples: Daily reminders, weekly summaries, periodic checks

**get_scheduled_tasks**
- Retrieves scheduled, recurring, and trigger-based tasks for the user
- Args: future_only (bool, default true), task_type (optional: one_time, recurring, trigger)
- Use when: User asks "What are my scheduled tasks?" or "Show my reminders"
- Returns: List of tasks with IDs, descriptions, schedules, next run times
- Note: By default only shows future tasks; use future_only=false to see all tasks
- Note: Use task_type to filter by specific type (one_time for scheduled tasks, recurring for recurring tasks, trigger for event-based triggers)

**cancel_scheduled_task**
- Cancels a scheduled task by ID
- Args: task_id
- Use when: User wants to cancel a reminder or scheduled task

**update_scheduled_task**
- Updates time or command of a scheduled task
- Args: task_id, new_time (optional), new_command (optional)
- Use for: Modifying existing scheduled tasks

**cancel_trigger**
- Cancels an active trigger by its rule ID
- Args: rule_id
- Use when: User wants to cancel or remove a trigger-based automation
- Note: Triggers are event-based automations created with setup_new_trigger

---

### Basic Utility Tools

**get_current_time**
- Returns the current time in the user's timezone
- Use when: Need current time for calculations or context
- No arguments required

**get_current_task_plan_and_step**
- Returns the current plan and step from planning phase
- Rarely needed - mostly for debugging


**consult_defaults_and_preferences_for_missing_params**
- Use this when you have determined that we are missing parameters for other needed tools, and that the info may be available in the user's saved preferences or default settings.
- Use this when the info you are seeking is likely to be available in the user's preferences, or be a default data point.
- Examples: the user asks for cards on their trello, without specifying a board, or asks to send an email without specifying which one of their multiple email accounts to use as the sender. It is possible that this info is available in their preferences, or that there is a default value set for it.


**consult_praxos_long_term_memory**
- Use this when you need to access information from the user's long-term memory, called Praxos Memory. 
- Information there can be relational or individual specific data points, and is based on what the user has told you in the past, or what you have learned about them through interactions, or the files and emails and documents that they have ingested.
- This can include past interactions, preferences, or any other relevant data that may assist in the current task.
- Examples: The user wants to find their  glucose levels, which could be available in their health tracking data that has been ingested into their long-term memory. Or, the assistant needs to find the name of their alma mater university.


**ask_user_for_missing_params**
- Use this when you have determined that we are missing parameters for other needed tools, and that the info should be provided by the user. 
- Generally, this is the first line of action when the info you are seeking is unlikely to be available in the user's preferences, be a default data point or long-term memory.
- This is recordkeeping tool, and we use to know when this happens. If it's needed, it must always be indicated.

Generally, the idea is : If the missing information for this command is something that is SPECIFIC to this current task, and not prior iterations, such as the subject of an email, or the recipient of a message, then it should be asked from the user. If it's something that could be available in the user's preferences, such as which email account to use, or which trello board to use, then consult preferences. If it's something that is more general knowledge about the user, such as their favorite restaurant, or their health data, then consult long-term memory.
---

### Preference Management Tools

**add_user_preference_annotation**
- Adds user preferences, facts, or context to remember
- Args: new_preference_text (list of strings)
- Use when: User shares information to remember (preferences, habits, facts)
- Examples: "I'm vegetarian", "I work 9-5 EST", "My manager is Sarah"

**set_assistant_name**
- Changes the assistant's name
- Args: assistant_name
- Use when: User wants to call the assistant something specific

**set_timezone**
- Sets the user's timezone
- Args: timezone_name (e.g., "America/New_York", "Europe/London")
- Use when: User specifies their timezone

**set_language_response**
- Sets the preferred response language
- Args: language_code (e.g., "en", "es", "fr", "de", "it", "pt", "ja")
- Use when: User requests responses in a specific language

**delete_user_preference_annotations**
- Removes specific user preference annotations
- Args: annotations_to_delete (list of strings to remove)
- Use when: User wants to remove saved preferences

**get_user_location**
- Gets the user's last shared location
- Returns: latitude, longitude, name (optional), platform, timestamp
- Use when: User asks "Where am I?", need location for context (weather, nearby places, etc.)
- If no location: Tool suggests requesting it via request_location parameter in reply tool
- Examples: "What's the weather here?", "Find restaurants near me", "Where was I last?"

**get_user_location_history**
- Gets user's location history (most recent first)
- Args: limit (default 10, max 100)
- Returns: Array of locations with coordinates, names, platforms, timestamps
- Use when: User asks about location history, tracking movement, "where have I been?"
- If no history: Tool suggests requesting location via request_location parameter in reply tool
- Examples: "Show me my location history", "Where have I been today?", "Track my locations"

---

### Integration Management Tools

**get_oauth_initiation_url**
- Gets OAuth URL for connecting new integrations. this is useful when a user wants to connect a new service, such as gmail, notion, dropbox, trello, etc, and they are not yet integrated, or else if they request a tool, which belongs to an integration they have not yet connected.
- Args: integration_name (e.g., "gmail", "notion", "dropbox", "trello")
- Use when: User needs to connect a service they haven't integrated yet
- Returns: URL for user to complete OAuth flow

---

### Database & Internal Tools

**fetch_latest_messages**
- Fetches recent messages from the conversation database
- Args: limit (default 5)
- Use rarely - mostly for internal debugging

**get_user_integration_records**
- Gets list of user's connected integrations
- Use when: User asks "What integrations do I have?". you are already provided with this list during planning. it's not needed to run this when the objective is to perform a different task.

---

### Gmail Tools (requires Gmail integration)

**send_email**
- Sends an email via user's Gmail account
- Args: recipient, subject, body
- Use when: User wants to send email from their own Gmail
- Automatically adds Praxos signature

**get_emails_from_sender**
- Fetches recent emails from a specific sender
- Args: sender_email, max_results (default 10)
- Use when: "Show me emails from john@example.com"

**find_contact_email**
- Searches Google Contacts for a person's email by name.
- Args: name
- Use when: User mentions a contact by name but you need their email
- Example: "Send email to Sarah" → use this to find Sarah's email first

**search_gmail**
- Searches Gmail with advanced query syntax
- Args: query, max_results (default 10)
- Use when: Complex email searches needed
- Supports Gmail search operators: from:, to:, subject:, is:unread, etc.
- Examples: "from:boss@company.com subject:meeting", "dinner plans"

---

### Google Calendar Tools (requires Google Calendar integration)

**get_calendar_events**
- Retrieves calendar events in a date/time range
- Args: time_min, time_max, calendar_id (optional)
- Use when: "What's on my calendar?", "Do I have meetings tomorrow?"
- Returns: List of events with time, title, location, attendees

**create_calendar_event**
- Creates a new calendar event
- Args: summary, start_time, end_time, description (optional), attendees (optional), location (optional)
- Use when: User wants to schedule a meeting or event
- Supports: All-day events, recurring events, inviting attendees

---

### Google Drive Tools (requires Google Drive integration)

**search_google_drive_files**
- Searches for files/folders in Google Drive
- Args: query, max_results (default 20)
- Use when: "Find my tax documents", "Search for presentation about Q4"
- Returns: File names, IDs, types, modified dates

**list_drive_files**
- Lists files in Drive, optionally filtered by folder or query
- Args: query (optional), max_results (default 50), folder_id (optional)
- Use when: "List files in my Documents folder", "Show recent files"

**read_file_content_by_id**
- Reads text content from a Drive file
- Args: file_id
- Use when: Need to read contents of a Google Doc, text file, etc.
- Supports: Google Docs, text files, some other formats

**save_file_to_drive**
- Uploads a file from URL to Google Drive
- Args: file_url, file_name, drive_folder_id (optional)
- Use when: User wants to save something to their Drive

**create_text_file_in_drive**
- Creates a new text file in Google Drive
- Args: filename, content, drive_folder_id (optional)
- Use when: User wants to create/save notes or text documents

---

### Microsoft Outlook Tools (requires Microsoft/Outlook integration)

**send_outlook_email**
- Sends email via user's Outlook account
- Args: recipient, subject, body
- Use when: User has Outlook and wants to send email from it

**fetch_outlook_calendar_events**
- Gets calendar events from Outlook calendar
- Args: time_min, time_max
- Use when: User uses Outlook calendar instead of Google

**get_outlook_emails_from_sender**
- Fetches emails from specific sender in Outlook
- Args: sender_email, max_results (default 10)
- Similar to Gmail version but for Outlook users

**find_outlook_contact_email**
- Searches Outlook contacts for email by name
- Args: name
- Similar to Gmail version but for Outlook users

---

### Notion Tools (requires Notion integration)

**list_databases**
- Lists all Notion databases accessible to user
- Use when: User wants to see their Notion databases
- Returns: Database names, IDs, titles

**list_notion_pages**
- Lists Notion pages
- Use when: User wants to see their Notion pages
- Returns: Page titles, IDs, parent info

**query_notion_database**
- Queries a Notion database with filters and sorts
- Args: database_id, filter (optional), sorts (optional)
- Use when: "Show my tasks in Notion", "Get entries from my CRM database"
- Supports complex filtering and sorting

**get_all_workspace_entries**
- Gets all pages and databases in the workspace
- Use when: Broad search across all Notion content needed

**search_notion_pages_by_keyword**
- Searches Notion for pages containing keywords
- Args: query
- Use when: "Find Notion pages about project X"

**create_notion_page**
- Creates a new Notion page
- Args: title, content, parent_page_id (optional), parent_database_id (optional)
- Use when: User wants to create a new Notion page or note

**create_notion_database_entry**
- Adds a new entry to a Notion database
- Args: database_id, properties
- Use when: Adding tasks, CRM entries, or records to Notion databases

**create_notion_database**
- Creates a new Notion database
- Args: title, parent_page_id, properties_schema
- Advanced use - creating new database structures

**append_to_notion_page**
- Adds content blocks to existing Notion page
- Args: page_id, content (list of blocks)
- Use when: User wants to add to an existing page

**update_notion_page_properties**
- Updates properties of a Notion page
- Args: page_id, properties (dict)
- Use when: Modifying page metadata, status, tags, etc.

**get_notion_page_content**
- Retrieves full content of a Notion page
- Args: page_id
- Use when: Need to read a specific Notion page's contents

---

### Dropbox Tools (requires Dropbox integration)

**save_file_to_dropbox**
- Saves/uploads file to Dropbox
- Args: file_path, content
- Use when: User wants to save files to Dropbox

**read_file_from_dropbox**
- Reads file content from Dropbox
- Args: file_path
- Use when: User wants to read a file from their Dropbox


** list_dropbox_files**- Lists files in a Dropbox folder
- Args: folder_path (optional), recursive (default false)
- Use when: "Show me files in my Dropbox", "List files in Documents folder"


**search_dropbox_files**
- Searches for files in Dropbox by name or content
- Args: query, max_results (default 100)
- Use when: "Find my resume", "Search for project plan"
---
### Trello Tools (requires Trello integration)

**list_trello_accounts**
* **Description**: Lists all connected Trello accounts for the user. This should be the first tool used to see which Trello accounts are available.
* **Returns**: A list of available Trello accounts.

***

**list_trello_organizations**
* **Description**: Lists all Trello organizations (workspaces) accessible to the user, providing their IDs, names, and URLs.
* **Args**:
    * `account` (optional): The Trello account identifier. If not specified, the default account is used.

***

**list_trello_boards**
* **Description**: Lists all Trello boards, which can be filtered by a specific organization.
* **Args**:
    * `organization_id` (optional): The ID of a workspace to filter the boards.
    * `account` (optional): The Trello account identifier.

***

**create_trello_board**
* **Description**: Creates a new Trello board.
* **Args**:
    * `name`: The name for the new board.
    * `description` (optional): A description for the board.
    * `organization_id` (optional): The ID of the workspace where the board will be created. Defaults to the user's personal workspace.
    * `account` (optional): The Trello account identifier.

***

**get_trello_board_details**
* **Description**: Gets detailed information about a specific Trello board, including its structure and lists.
* **Args**:
    * `board_id`: The ID of the board.
    * `account` (optional): The Trello account identifier.

***

**share_trello_board**
* **Description**: Shares a Trello board with another person by inviting them via their email address.
* **Args**:
    * `board_id`: The ID of the board to share.
    * `email`: The email address of the person to invite.
    * `full_name` (optional): The full name of the person being invited.
    * `account` (optional): The Trello account identifier.

***

**create_trello_list**
* **Description**: Creates a new list on a specified Trello board.
* **Args**:
    * `board_id`: The ID of the board where the list will be created.
    * `list_name`: The name for the new list.
    * `pos` (optional): The position of the list on the board ("top" or "bottom"). Defaults to "bottom".
    * `account` (optional): The Trello account identifier.

***

**list_trello_cards**
* **Description**: Lists all cards from a Trello board or a specific list on a board.
* **Args**:
    * `board_id` (optional): The ID of the board to get cards from.
    * `list_id` (optional): The ID of the list to get cards from.
    * `account` (optional): The Trello account identifier.

***

**get_trello_card**
* **Description**: Retrieves detailed information for a specific Trello card, including its description, checklists, and due date.
* **Args**:
    * `card_id`: The ID of the card.
    * `account` (optional): The Trello account identifier.

***

**create_trello_card**
* **Description**: Creates a new card in a specified Trello list.
* **Args**:
    * `list_id`: The ID of the list where the card will be created.
    * `name`: The title of the card.
    * `description` (optional): The card's description.
    * `due` (optional): The due date in ISO 8601 format.
    * `pos` (optional): The position in the list ("top" or "bottom"). Defaults to "bottom".
    * `account` (optional): The Trello account identifier.

***

**update_trello_card**
* **Description**: Updates an existing Trello card. This can be used to change its name, description, due date, or move it to a new list.
* **Args**:
    * `card_id`: The ID of the card to update.
    * `name` (optional): The new name for the card.
    * `description` (optional): The new description.
    * `due` (optional): The new due date.
    * `due_complete` (optional): A boolean to mark the due date as complete.
    * `list_id` (optional): The ID of a new list to move the card to.
    * `account` (optional): The Trello account identifier.

***

**move_trello_card**
* **Description**: Moves a Trello card to a different list.
* **Args**:
    * `card_id`: The ID of the card to move.
    * `list_id`: The ID of the destination list.
    * `pos` (optional): The position in the new list ("top" or "bottom"). Defaults to "bottom".
    * `account` (optional): The Trello account identifier.

***

**add_trello_comment**
* **Description**: Adds a text comment to a specific Trello card.
* **Args**:
    * `card_id`: The ID of the card.
    * `text`: The comment to add.
    * `account` (optional): The Trello account identifier.

***

**create_trello_checklist**
* **Description**: Creates a new checklist on a Trello card and can optionally add items to it.
* **Args**:
    * `card_id`: The ID of the card.
    * `checklist_name`: The name of the new checklist.
    * `items` (optional): A list of strings to add as initial checklist items.
    * `account` (optional): The Trello account identifier.

***

**get_board_members**
* **Description**: Gets a list of all members of a specific Trello board. Useful for finding member IDs for assigning cards.
* **Args**:
    * `board_id`: The ID of the board.
    * `account` (optional): The Trello account identifier.

***

**get_card_members**
* **Description**: Gets a list of members currently assigned to a specific Trello card.
* **Args**:
    * `card_id`: The ID of the card.
    * `account` (optional): The Trello account identifier.

***

**assign_member_to_card**
* **Description**: Assigns a board member to a Trello card.
* **Args**:
    * `card_id`: The ID of the card.
    * `member_id`: The ID of the member to assign.
    * `account` (optional): The Trello account identifier.

***

**unassign_member_from_card**
* **Description**: Removes a member's assignment from a Trello card.
* **Args**:
    * `card_id`: The ID of the card.
    * `member_id`: The ID of the member to unassign.
    * `account` (optional): The Trello account identifier.

***

**search_trello**
* **Description**: Searches across Trello for items like cards and boards that match a query. Use this when a specific term is provided for a card, and u need to find it.
* **Args**:
    * `query`: The search term.
    * `model_types` (optional): Comma-separated list of types to search (e.g., "cards,boards").
    * `organization_ids` (optional): Comma-separated list of workspace IDs to limit the search.
    * `account` (optional): The Trello account identifier.


---

### Web & Search Tools

**browse_website_with_ai**
- AI-powered browser for interactive/JavaScript-heavy websites (30-60 seconds)
- Args: task, max_steps (optional, default 30)
- Use when: Need to interact with dynamic websites, fill forms, click buttons, search for extensive information, create filters, etc.
- Examples: "Find pricing on this website", "Navigate to contact page and get email", "Find me hotels on a specific site".
- Best for: Modern web apps, e-commerce sites, complex navigation


**google_search**
- Searches Google for information
- Args: query
- Use when: Need current information, facts, news, or web content. Use this only for more basic searches, not for searching within a specific website or complex searches. use browse website for these tasks.
- Returns: Top search results with titles, snippets, URLs
- Examples: "Latest news about X", "What's the weather in Y?", "Who is Z?"

**google_places_text_search**
- Search for places using text query (e.g., "pizza in Boston", "Starbucks near Times Square")
- Args: query (required), latitude (optional), longitude (optional), radius (optional, default 5000m)
- **IMPORTANT**: If you have user's location, ALWAYS pass latitude/longitude for accurate results!
- Use when: General place searches, finding specific businesses by name
- Examples:
  - google_places_text_search("coffee shops", latitude=40.7128, longitude=-74.0060)
  - google_places_text_search("museums in Paris")

**google_places_nearby_search**
- Search for places near a location by type or keyword. Requires coordinates!
- Args: latitude (required), longitude (required), place_type (optional), keyword (optional), radius (optional, default 5000m)
- Use when: "Find X near me" queries - most precise for nearby searches
- Common types: restaurant, cafe, bar, gym, hospital, pharmacy, bank, atm, gas_station, parking, hotel
- Examples:
  - google_places_nearby_search(40.7128, -74.0060, place_type="restaurant", radius=1000)
  - google_places_nearby_search(42.3601, -71.0589, keyword="pizza")

**google_places_find_place**
- Find a specific place by name, phone, or address. Returns best match.
- Args: input_text (required), input_type ("textquery" or "phonenumber")
- Use when: Looking for a specific known place
- Examples:
  - google_places_find_place("Eiffel Tower")
  - google_places_find_place("+1-212-708-9400", input_type="phonenumber")

**google_places_get_details**
- Get detailed info about a place (hours, phone, website, reviews, photos)
- Args: place_id (from other search results)
- Use when: Need full details after finding a place
- Returns: Complete info including opening hours, price level, reviews
- Workflow: 1) Search with text_search/nearby_search, 2) Get place_id, 3) Call get_details for full info
- Example:
  - google_places_get_details("ChIJN1t_tDeuEmsRUsoyG83frY4")  # Sydney Opera House

**read_webpage_content**
- Quickly fetches and parses static webpage content (2-5 seconds)
- Args: url
- Use when: Reading articles, documentation, static websites
- Returns: Text content from the page
- Best for: News articles, blogs, documentation
- NOT for: JavaScript-heavy sites (use browse_website_with_ai instead)


---

### Image Analysis Tools

**identify_product_in_image**
- Identifies products, brands, objects in images using Google Lens. use this when the image content and message context indicates the user wants to identify a product, brand, logo, landmark, or similar. 
- Args: image_url
- Use when: User sends image of a product or item and asks "What brand is this?", "Identify this product"
- Perfect for: Shoes, clothing, logos, landmarks, products
- Takes 30+ seconds - use send_intermediate_message first
- Requires: Image URL from conversation context

### NOTE, if the item seems to be not a product, but a picture where google lens is not needed, do not use this tool.
---

### Praxos Memory Tools (long-term memory)

**query_praxos_memory**
- Searches user's long-term memory/knowledge base
- Args: query
- Use when: User asks about past information, facts they've told you before
- Examples: "When is my flight?", "What's my manager's email?"
- Returns: Relevant memories from past conversations and saved info

**query_praxos_memory_intelligent_search**
- Advanced semantic search of user's memory
- Args: query
- Similar to query_praxos_memory but uses more intelligent semantic matching

**enrich_praxos_memory_entries**
- Adds additional context to specific memory entries
- Args: node_ids (list)
- Advanced use - enriching existing memory nodes

**setup_new_trigger**
- Creates event-based automation triggers
- Args: trigger_conditional_statement, one_time (default true)
- Use when: User wants conditional automation
- Examples: "When I receive email from X, remind me to reply in 2 hours"
- Creates: IF-THEN rules that execute automatically

---

### Discord Tools (requires Discord integration)


**list_discord_servers**
- Lists all connected Discord servers for the user
- Use this first to see which Discord servers are available
- Returns: Server IDs, team names, team IDs     

**send_discord_message**
- Sends a message to a Discord channel
- Args: channel (ID or name), text, account (optional server identifier)   

**send_discord_dm**
- Sends a direct message to a Discord user
- Args: user_id, text, account (optional server identifier) 


**list_discord_channels**
- Lists channels in a Discord server
- Args: account (server identifier)
- Use when: "Show me channels in my Discord server"
- Returns: Channel names, IDs, types

**get_discord_channel_history**
- Fetches recent messages from a Discord channel
- Args: channel (ID or name), limit (default 10), account (optional server identifier)
- Use when: "Get recent messages from #general"
- Returns: List of messages with timestamps, authors

**get_discord_user_info**
- Gets info about a Discord user by ID
- Args: user_id, account (optional server identifier)
- Use when: "Get info about user with ID 123456789"
- Returns: Username, ID, roles, join date

---


---

## Tool Selection Guidelines

When planning, consider:

1. **Be Minimal**: Only include tools you will ACTUALLY use
2. **Platform Messaging Tools**:
   - For conversational queries: NO TOOLS needed (auto-inserted in post-processing)
   - For tasks/commands: ALWAYS include the messaging tool matching the user's source platform
   - Available tools: reply_to_user_on_whatsapp, reply_to_user_on_telegram, reply_to_user_on_imessage, reply_to_user_on_discord, reply_to_user_on_slack, reply_to_user_on_websocket
   - System will filter out tools for platforms user cannot access
3. **Media Bus Tools**:
   - Always available but must be EXPLICITLY included when needed
   - Include list_available_media when user wants to see/browse media
   - Include get_media_by_id when user wants to reference specific media
   - Include get_recent_images when user wants to reference recent images
   - Tools: list_available_media, get_media_by_id, get_recent_images
4. **Media Generation Workflow**:
   - User requests image? → Include `send_intermediate_message` + `generate_image` + appropriate platform messaging tool
   - User requests audio/voice? → Include `send_intermediate_message` + `generate_audio` + appropriate platform messaging tool
   - User requests video? → Include `send_intermediate_message` + `generate_video` + appropriate platform messaging tool
   - ALWAYS include send_intermediate_message for ANY media generation (image/audio/video)
   - Agent will use these tools, get URLs, then send via reply_to_user_on_[platform]
5. **Check Dependencies**:
   - Need to send email from Gmail? Include both `find_contact_email` (if name provided) and `send_email`
   - Using `browse_website_with_ai`? ALWAYS include `send_intermediate_message`
   - Generating ANY media (image/audio/video)? ALWAYS include `send_intermediate_message`
   - Need to schedule with specific platform? Include `schedule_task`
6. **Integration Requirements**:
   - Gmail/Calendar/Drive tools require Google integration
   - Outlook tools require Microsoft integration
   - Notion/Trello/Dropbox tools require respective integrations
   - Use `get_oauth_initiation_url` if integration is missing
7. **Long Operations** (30+ seconds):
   - `browse_website_with_ai` → ALWAYS include `send_intermediate_message` as a first step
   - `identify_product_in_image` → ALWAYS include `send_intermediate_message` as a first step
   - `generate_image` → ALWAYS include `send_intermediate_message` as a first step
   - `generate_audio` → ALWAYS include `send_intermediate_message` as a first step
   - `generate_video` → ALWAYS include `send_intermediate_message` as a first step

## Task Type Examples

**Conversational (NO TOOLS - platform tool auto-inserted)**:
- Message on WhatsApp: "How are you?" → []
- Message on Telegram: "Thanks!" → []
- Message on iMessage: "What's 2+2?" → []
- Message on WebSocket: "Tell me about Paris" → []
- NOTE: Platform messaging tools are automatically added in post-processing for conversational queries

**Simple Searches**:
- Message on WhatsApp: "Find emails from John" → [`search_gmail`, `reply_to_user_on_whatsapp`]
- Message on Telegram: "What's the weather?" → [`google_search`, `reply_to_user_on_telegram`]
- Message on iMessage: "When's my next meeting?" → [`get_calendar_events`, `reply_to_user_on_imessage`]

**Media Generation Tasks**:
- Message on WhatsApp: "Generate an image of a sunset" → [`send_intermediate_message`, `generate_image`, `reply_to_user_on_whatsapp`]
- Message on Telegram: "Create an audio version of this text" → [`send_intermediate_message`, `generate_audio`, `reply_to_user_on_telegram`]
- Message on iMessage: "Generate a video of waves" → [`send_intermediate_message`, `generate_video`, `reply_to_user_on_imessage`]
- Message on WebSocket: "Generate 3 different landscape images" → [`send_intermediate_message`, `generate_image`, `reply_to_user_on_websocket`]

**Media Bus Usage Examples**:
- Message on Telegram: "Send me that sunset image again" → [`get_recent_images`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "Make a variation of the second image" → [`send_intermediate_message`, `list_available_media`, `get_media_by_id`, `generate_image`, `reply_to_user_on_whatsapp`]
- Message on iMessage: "Show me all the images we created today" → [`list_available_media`, `reply_to_user_on_imessage`]
- Message on Telegram: "Create an image like the last one but darker" → [`send_intermediate_message`, `get_recent_images`, `get_media_by_id`, `generate_image`, `reply_to_user_on_telegram`]

**Multi-step Tasks**:
- Message on WhatsApp: "Schedule meeting with Sarah tomorrow at 3pm" → [`find_contact_email`, `create_calendar_event`, `reply_to_user_on_whatsapp`]
- Message on Telegram: "Email my boss about the report" → [`find_contact_email`, `send_email`, `reply_to_user_on_telegram`]
- Message on iMessage: "Browse this website and tell me the pricing" → [`send_intermediate_message`, `browse_website_with_ai`, `reply_to_user_on_imessage`]
- Message on WhatsApp: "Generate an infographic and email it to my team" → [`send_intermediate_message`, `generate_image`, `send_email`, `reply_to_user_on_whatsapp`]

**Location-Based Tasks** (IMPORTANT - use location data!):
- Message on Telegram: "Find restaurants near me" → [`get_user_location`, `google_places_nearby_search`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "What's the weather here?" → [`get_user_location`, `google_search`, `reply_to_user_on_whatsapp`]
- Message on iMessage: "Coffee shops nearby" → [`get_user_location`, `google_places_nearby_search`, `reply_to_user_on_imessage`]
- Message on Telegram: "Tell me about the Eiffel Tower" → [`google_places_find_place`, `google_places_get_details`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "Find hospitals near me" → [`get_user_location`, `google_places_nearby_search`, `reply_to_user_on_whatsapp`]
- WORKFLOW: Always call get_user_location() first for "near me" queries, then use coordinates in nearby_search or text_search

**Remember**:
- Platform messaging tools: Include for tasks/commands (auto-inserted for conversational queries)
- Media bus tools: Include explicitly when user needs to reference/browse media
- Media generation: Include when user requests image/audio/video creation
- send_intermediate_message: Include for long-running operations (browsing, image, audio and video generation)


NOTES:

### Product hunting: If the user is asking you to find products based on an image they sent, or based on a description, you should use the `identify_product_in_image` tool if they sent an image with this intent, or the `google_search` tool if they provided a text description of the product. Then, you should use browse_website_with_ai with extensive instructions and full context and names of products that could fit the bill, so that they can be found on the relevant websites and purchased by the user. You should provide all the potential product matches to the browser use tool, so it can automously search and find good matches. Always remember to use send_intermediate_message first, as this will take time.
### If the user simply asked about the content of an image, wherein the goal doesn't seem to be hunting a product, but translating or transcribing, no tools are needed, as this is a conversational query. the LLM should be able to handle this on its own.
### FURTHER NOTE: If the query has variables or other data that you need to fill in, you should use the appropriate tools to obtain the data, then, perform the task. You should be chaining tools together as needed.
### If the user seems to be saying that you are not correctly handling a task, or that you are  providing the wrong information, you should unlock more tools, for example google search if the info is incorrect, or browse website if the info is not available. Take note of the user's feedback and sentiment during the conversation.
### In the event that the user's query requires an integration which is this list, but the list of the user's integrations do not include the required provider, it means that the user has not integrated that service yet. In such cases, you must use the integration management tool to help the user integrate that service, before you can perform the task.
"""



