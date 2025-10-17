
### NOTE: WE ARE NOT USING THIS IN THIS FORM, INSTEAD USING A CACHED TOOL. THIS IMPROVES LATENCY. NOTE THAT EDITTING THIS DOES EXACTLY NOTHING, but you may cache it for yourself and change the cache name in the adjacent caches.py file. 
"""
Granular tooling capabilities with specific function IDs and descriptions.
Used by the granular planning agent to select precise tools needed for each task.
"""

GRANULAR_TOOLING_CAPABILITIES = """
## Available Tool Functions

Below is a comprehensive list of ALL available tool functions with their IDs and descriptions.
**IMPORTANT**: Only include tools that are ACTUALLY needed for the task. Be precise and minimal.


**IMPORTANT**: we do not consider capabilities such as "Transcribing the contents" of an image, 'Translating the contents' of an email, 'transcribing an audio file', or 'summarizing a document' as separate tools. These are capabilities that are part of the core AI functionality, and do not require a separate tool. The tools listed here are for external integrations, or for specific actions that require a distinct function call. Such capabilities can be handled by the AI directly, without needing to invoke a separate tool.
**IMPORTANT**: Generating a video, image or audio is not a tool functionality. the model simply has to return the correct result. if this is requested, you do not need to select a tool. the system will handle it automatically. 
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
- Retrieves all scheduled tasks for the user
- Use when: User asks "What are my scheduled tasks?" or "Show my reminders"
- Returns: List of tasks with IDs, descriptions, schedules, next run times

**cancel_scheduled_task**
- Cancels a scheduled task by ID
- Args: task_id
- Use when: User wants to cancel a reminder or scheduled task

**update_scheduled_task**
- Updates time or command of a scheduled task
- Args: task_id, new_time (optional), new_command (optional)
- Use for: Modifying existing scheduled tasks

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

---

### Integration Management Tools

**get_oauth_initiation_url**
- Gets OAuth URL for connecting new integrations. this is useful when a user wants to connect a new service, such as gmail, notion, dropbox, trello, etc, and they are not yet integrated.
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
- IMPORTANT: Always use send_intermediate_message first to notify user this will take time
- Best for: Modern web apps, e-commerce sites, complex navigation


**google_search**
- Searches Google for information
- Args: query
- Use when: Need current information, facts, news, or web content. Use this only for more basic searches, not for searching within a specific website or complex searches. use browse website for these tasks.
- Returns: Top search results with titles, snippets, URLs
- Examples: "Latest news about X", "What's the weather in Y?", "Who is Z?"

**GooglePlacesTool**
- Searches for places, businesses, locations via Google Places API
- Use when: Finding restaurants, addresses, business info
- Examples: "Find coffee shops near me", "What's the address of X restaurant?"

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
- Identifies products, brands, objects in images using Google Lens
- Args: image_url
- Use when: User sends image and asks "What brand is this?", "Identify this product"
- Perfect for: Shoes, clothing, logos, landmarks, products
- Takes 30+ seconds - use send_intermediate_message first
- Requires: Image URL from conversation context

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
2. **Check Dependencies**:
   - Need to send email from Gmail? Include both `find_contact_email` (if name provided) and `send_email`
   - Using `browse_website_with_ai`? Also include `send_intermediate_message`
   - Need to schedule with specific platform? Include `schedule_task`
3. **Integration Requirements**:
   - Gmail/Calendar/Drive tools require Google integration
   - Outlook tools require Microsoft integration
   - Notion/Trello/Dropbox tools require respective integrations
   - Use `get_oauth_initiation_url` if integration is missing
4. **Long Operations** (30+ seconds):
   - `browse_website_with_ai` → ALWAYS include `send_intermediate_message`
   - `identify_product_in_image` → ALWAYS include `send_intermediate_message`

## Task Type Examples

**Conversational (NO TOOLS)**:
- "How are you?"
- "Thanks!"
- "What's 2+2?"
- "Tell me about Paris"

**Simple Searches (1-2 tools)**:
- "Find emails from John" → [`search_gmail`]
- "What's the weather?" → [`google_search`]
- "When's my next meeting?" → [`get_calendar_events`]

**Multi-step Tasks (multiple tools)**:
- "Schedule meeting with Sarah tomorrow at 3pm" → [`find_contact_email`, `create_calendar_event`]
- "Email my boss about the report" → [`find_contact_email`, `send_email`]
- "Browse this website and email me the pricing" → [`send_intermediate_message`, `browse_website_with_ai`, `send_email`]

**Remember**: Only include tools that are NECESSARY. Don't include tools "just in case."


NOTES:

### Product hunting: If the user is asking you to find products based on an image they sent, or based on a description, you should use the `identify_product_in_image` tool if they sent an image, or the `google_search` tool if they provided a text description of the product. Then, you should use browse_website_with_ai with extensive instructions and full context and names of products that could fit the bill, so that they can be found on the relevant websites and purchased by the user. You should provide all the potential product matches to the browser use tool, so it can automously search and find good matches. Always remember to use send_intermediate_message first, as this will take time.
### FURTHER NOTE: If the query has variables or other data that you need to fill in, you should use the appropriate tools to obtain the data, then, perform the task. You should be chaining tools together as needed.
### If the user seems to be saying that you are not correctly handling a task, or that you are  providing the wrong information, you should unlock more tools, for example google search if the info is incorrect, or browse website if the info is not available. Take note of the user's feedback and sentiment during the conversation.
"""



