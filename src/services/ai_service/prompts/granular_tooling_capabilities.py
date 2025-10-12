
### NOTE: WE ARE NOT USING THIS IN THIS FORM, INSTEAD USING A CACHED TOOL. THIS IMPROVES LATENCY. NOTE THAT EDITTING THIS DOES EXACTLY NOTHING, but you may cache it for yourself and change the cache name in the adjacent caches.py file. 
"""
Granular tooling capabilities with specific function IDs and descriptions.
Used by the granular planning agent to select precise tools needed for each task.
"""

GRANULAR_TOOLING_CAPABILITIES = """
## Available Tool Functions

Below is a comprehensive list of ALL available tool functions with their IDs and descriptions.
**IMPORTANT**: Only include tools that are ACTUALLY needed for the task. Be precise and minimal.

---

### Communication Tools

**send_intermediate_message**
- Sends status updates to users during long-running operations (30+ seconds)
- Use for: Web browsing, media generation, long searches
- Example: "I'm browsing that website now, this will take about 30 seconds..."
- DO NOT use for simple tasks that complete quickly

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

**consult_praxos_long_term_memory**
- Use this when you need to access information from the user's long-term memory, called Praxos Memory. 
- Information there can be relational or factual, and is based on what the user has told you in the past, or what you have learned about them through interactions, or the files and emails and documents that they have ingested.
- This can include past interactions, preferences, or any other relevant data that may assist in the current task.

**ask_user_for_missing_params**
- Use this when you have determined that we are missing parameters for other needed tools, and that the info should be provided by the user. 
- Generally, this is the first line of action when the info you are seeking is unlikely to be available in the user's preferences, be a default data point or long-term memory.
- This is recordkeeping tool, and we use to know when this happens. If it's needed, it must always be indicated.


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
- Gets OAuth URL for connecting new integrations
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
- Use when: User asks "What integrations do I have?" or needs integration status

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
- Searches Google Contacts for a person's email by name
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

**list_trello_organizations**
- Lists user's Trello workspaces/organizations
- Use when: Need to see available Trello workspaces
- Returns: Organization names, IDs

**list_trello_boards**
- Lists Trello boards, optionally filtered by organization
- Args: organization_id (optional)
- Use when: "Show my Trello boards", "What Trello boards do I have?"

**get_trello_board_details**
- Gets detailed info about a specific Trello board
- Args: board_id
- Use when: Need board structure, lists, members, etc.
- Returns: Board name, lists, cards, members

**list_trello_cards**
- Lists cards from a Trello board or list
- Args: board_id, list_id (optional)
- Use when: "Show me cards on my Work board"

**create_trello_card**
- Creates a new Trello card
- Args: board_id, list_id, name, description (optional), due_date (optional)
- Use when: User wants to add tasks or items to Trello

**update_trello_card**
- Updates an existing Trello card
- Args: card_id, name (optional), description (optional), due_date (optional), list_id (optional)
- Use when: Moving cards, updating descriptions, changing due dates

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
"""
