
### NOTE: WE ARE NOT USING THIS IN THIS FORM, INSTEAD USING A CACHED TOOL. THIS IMPROVES LATENCY. NOTE THAT EDITTING THIS DOES EXACTLY NOTHING, but you may cache it for yourself and change the cache name in the adjacent caches.py file.
"""
Granular tooling capabilities with specific function IDs and descriptions.
Used by the granular planning agent to select precise tools needed for each task.
"""

# Import auto-generated tool documentation
# To regenerate: python scripts/generate_tool_artifacts.py --docs
from src.services.ai_service.prompts.tool_docs_generated import TOOL_DOCUMENTATION

# Combine generated docs with manual guidelines
GRANULAR_TOOLING_CAPABILITIES = TOOL_DOCUMENTATION + """

---

### Basic Tools

**get_current_task_plan_and_step**
- Returns the current plan and step from planning phase
- Args: plan (str)
  - `plan`: The plan string to return
- Returns: Current plan with step statuses
- Use when: Rarely needed - mostly for debugging
- Use when: Returns plan with step markers (DONE, IN PROGRESS, NOT STARTED)

**get_current_time**
- Returns the current time in the user's timezone
- Returns: Current date and time in user's timezone
- Use when: Need current time for calculations or context
- Use when: No arguments required
- Note: Always included automatically
- Note: Returns time in user's configured timezone

---

### Communication Tools
(requires ios integration)

**create_ios_reminder**
- Create a reminder on the user's iOS device
- Args: title (str), due_date (str), optional, notes (str), optional
  - `title`: The reminder title/text
  - `due_date`: Optional due date in ISO format (e.g., "2025-11-05T14:00:00")
  - `notes`: Optional additional notes for the reminder
- Returns: Success confirmation or error message
- Use when: When user wants to create a reminder on their iOS device
- Use when: When setting up tasks with due dates
- Use when: When adding quick reminders through voice or text
- Example: create_ios_reminder("Call dentist", "2025-11-05T14:00:00", "Schedule cleaning appointment")
- Example: create_ios_reminder("Buy groceries")

**execute_ios_shortcut**
- Execute a named iOS Shortcut on the user's device
- Args: shortcut_name (str), input_text (str), optional
  - `shortcut_name`: Name of the Shortcut to execute
  - `input_text`: Optional input text to pass to the Shortcut
- Returns: Success confirmation or error message
- Use when: When user wants to trigger a custom iOS Shortcut
- Use when: When automating iOS device actions through Shortcuts
- Use when: When executing predefined workflows on iOS
- Example: execute_ios_shortcut("Log Water Intake", "500ml")
- Example: execute_ios_shortcut("Turn On Smart Lights")

**reply_to_user_via_email**
- Sends an email reply using the Praxos bot
- Args: body (str)
  - `body`: The email body content
- Returns: Success confirmation
- Use when: When replying to a user's email
- Use when: When sending a response via email to the user's query
- Example: reply_to_user_via_email("Thank you for your email. I have processed your request.")

**report_bug_to_developers**
- Reports a bug to the Praxos development team via email
- Args: bug_description (str), additional_context (str), optional
  - `bug_description`: Detailed description of the bug, including what happened and what was expected
  - `additional_context`: Optional additional context like error messages, stack traces, or reproduction steps
- Returns: Success confirmation with list of developer emails notified
- Use when: When encountering errors that need developer attention
- Use when: When experiencing unexpected behavior
- Use when: When tools fail in unexpected ways
- Use when: When you need to escalate an issue to developers
- Example: report_bug_to_developers("Email sending failed with timeout error", "User tried to send email to john@example.com. Error: Connection timeout after 30s")

**send_intermediate_message**
- Sends an intermediate message to the user during long-running operations
- Args: message (str)
  - `message`: The status update message to send
- Returns: Success confirmation
- Use when: When browsing web and the operation will take time
- Use when: When generating media (images, audio, video)
- Use when: When performing search operations that require waiting
- Use when: When you need to inform the user you're working on their request
- Example: send_intermediate_message("I'm browsing that website now, this will take about 30 seconds...")
- Example: send_intermediate_message("Generating your image, this may take a minute...")
- Example: send_intermediate_message("Searching the web for that information...")

**send_new_email_as_praxos_bot**
- Sends a new email using the Praxos bot
- Args: recipients (list), subject (str), body (str)
  - `recipients`: List of recipient email addresses
  - `subject`: Email subject line
  - `body`: Email body content
- Returns: Success confirmation
- Use when: When sending a new email on behalf of the user
- Use when: When the user requests to send an email to specific recipients
- Example: send_new_email_as_praxos_bot(["user@example.com"], "Meeting Reminder", "Your meeting is scheduled for tomorrow at 2pm")

**send_text_via_ios**
- Send a text message via iOS Shortcuts
- Args: message (str), target_phone (str)
  - `message`: The text message to send
  - `target_phone`: Phone number to send the message to (format: +1234567890)
- Returns: Success confirmation or error message
- Use when: When user wants to send a text message via their iOS device
- Use when: When automating text message sending through iOS Shortcuts
- Example: send_text_via_ios("Meeting moved to 3pm", "+19292717338")

---

### Database Tools

**fetch_latest_messages**
- Fetches recent messages from the conversation database
- Args: limit (int), optional, default 5
  - `limit`: Number of messages to fetch
- Returns: List of recent messages
- Use when: Rarely needed - mostly for internal debugging
- Use when: Do not use for long-term memory
- Use when: Use if confused about most recent messages
- Note: For long-term memory use praxos_memory tools instead

**get_user_integration_records**
- Gets list of user's connected integrations
- Returns: List of active integrations
- Use when: User asks "What integrations do I have?"
- Use when: You are already provided with this list during planning
- Use when: Not needed when objective is to perform a different task

---

### Discord Tools
(requires discord integration)

**get_discord_channel_history**
- Get message history from a Discord channel
- Args: channel (str), limit (int), optional, default 50, account (str), optional
  - `channel`: Channel ID (e.g., "C1234567890")
  - `limit`: Maximum number of messages to fetch (max 1000)
  - `account`: Discord server identifier. If not specified and user has only one server, that server will be used.
- Returns: JSON object with list of messages and count
- Use when: Read past messages in a Discord channel
- Use when: Review conversation history
- Use when: Search for information in previous discussions
- Use when: Monitor channel activity

**get_discord_user_info**
- Get information about a Discord user
- Args: user_id (str), account (str), optional
  - `user_id`: Discord user ID (e.g., "U1234567890")
  - `account`: Discord server identifier. If not specified and user has only one server, that server will be used.
- Returns: JSON object with user information including profile details
- Use when: Get details about a Discord user
- Use when: Look up user profiles and information
- Use when: Find contact information for team members
- Use when: Verify user identities

**list_discord_channels**
- List all channels in the Discord server
- Args: types (str), optional, default public_channel,private_channel, account (str), optional
  - `types`: Comma-separated channel types - "public_channel", "private_channel", "im", "mpim"
  - `account`: Discord server identifier. If not specified and user has only one server, that server will be used.
- Returns: JSON object with list of channels and count
- Use when: Discover available channels in a Discord server
- Use when: Get channel IDs for sending messages
- Use when: Browse server structure and available communication channels

**list_discord_servers**
- Lists all connected Discord servers for the user
- Returns: JSON object containing list of servers with server_id, team_name, and team_id
- Use when: Use this first to see which Discord servers are available
- Use when: Check which Discord servers the user is connected to
- Use when: Get server IDs for use in other Discord tools

**send_discord_dm**
- Send a direct message to a Discord user
- Args: user_id (str), text (str), account (str), optional
  - `user_id`: Discord user ID (e.g., "U1234567890")
  - `text`: Message text to send
  - `account`: Discord server identifier. If not specified and user has only one server, that server will be used.
- Returns: JSON object with success message and message_ts
- Use when: Send private messages to Discord users
- Use when: Send direct notifications to specific team members
- Use when: Have private conversations with Discord users

**send_discord_message**
- Send a message to a Discord channel
- Args: channel (str), text (str), account (str), optional
  - `channel`: Channel ID or channel name (e.g., "#general" or "C1234567890")
  - `text`: Message text to send
  - `account`: Discord server identifier. If not specified and user has only one server, that server will be used.
- Returns: JSON object with success message, message_ts, and channel information
- Use when: Send messages to Discord channels
- Use when: Post notifications to specific channels
- Use when: Communicate with team members in Discord channels

---

### Dropbox Tools
(requires dropbox integration)

**list_dropbox_accounts**
- Lists all connected Dropbox accounts for the user
- Returns: JSON object with list of connected Dropbox accounts
- Use when: Use this first to see which Dropbox accounts are available
- Use when: Check which Dropbox accounts the user has connected
- Use when: Determine which account identifier to use for other operations

**list_dropbox_files**
- Lists files and folders in a Dropbox directory
- Args: folder_path (str), optional, default , recursive (bool), optional, default False, account (str), optional
  - `folder_path`: Path to the folder (empty string for root folder)
  - `recursive`: If True, lists all files recursively in subfolders
  - `account`: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
- Returns: JSON object with list of files, count, and folder path
- Use when: Browse Dropbox folder contents
- Use when: List all files in a directory
- Use when: Recursively scan folder structures in Dropbox
- Use when: Discover available files before reading or processing

**read_file_from_dropbox**
- Reads the content of a file from Dropbox
- Args: file_path (str), account (str), optional
  - `file_path`: Path to the file in Dropbox
  - `account`: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
- Returns: Text content of the file from Dropbox
- Use when: Read documents stored in Dropbox
- Use when: Access file content from Dropbox storage
- Use when: Retrieve text files for processing or analysis

**save_file_to_dropbox**
- Saves text content to a file in Dropbox
- Args: file_path (str), content (str), account (str), optional
  - `file_path`: Path where to save the file in Dropbox (e.g., "/Documents/notes.txt")
  - `content`: Text content to save
  - `account`: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
- Returns: Success message confirming file was saved to Dropbox
- Use when: Save notes or documents to Dropbox
- Use when: Create new files in Dropbox storage
- Use when: Upload text content to specific Dropbox paths

**search_dropbox_files**
- Searches for files in Dropbox by filename or content
- Args: query (str), max_results (int), optional, default 100, account (str), optional
  - `query`: Search query (searches in filenames and file content)
  - `max_results`: Maximum number of results to return (max 1000)
  - `account`: Optional Dropbox account email/identifier. If not specified and user has only one Dropbox account, that account will be used.
- Returns: JSON object with search results, count, and query
- Use when: Find files by name across entire Dropbox account
- Use when: Search file content for specific keywords
- Use when: Locate documents without knowing exact path
- Use when: Discover files matching search criteria

---

### Example Tools
(requires optional_integration_name integration)

**example_tool**
- Short one-line description of what this tool does
- Args: arg_name (str), optional_arg (int), optional, default 10, enum_arg (str), optional
  - `arg_name`: What this argument is for
  - `optional_arg`: An optional argument
  - `enum_arg`: An argument with specific valid values
    - Valid values: option1, option2, option3
- Returns: Description of what the tool returns
- Use when: When user needs to do X
- Use when: For tasks involving Y
- Use when: When Z condition is met
- Example: example_tool("input")
- Example: example_tool("input", optional_arg=20)
- Note: Important note about usage
- Note: Limitation or caveat
- Note: Best practice tip

---

### Gmail Tools
(requires gmail integration)

**add_label_to_email**
- Adds a label/folder to an email
- Args: message_id (str), label_name (str), account (str), optional
  - `message_id`: ID of the email
  - `label_name`: Name of the label to add
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of label added
- Use when: User wants to organize email with labels
- Use when: Apply folder/category to email
- Note: Creates the label if it doesn't exist

**archive_email**
- Archives an email (removes from inbox, keeps in All Mail)
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to archive
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of archive
- Use when: User wants to archive an email to clean up inbox

**create_email_draft**
- Creates a draft email in Gmail without sending it
- Args: recipient (str), subject (str), body (str), account (str), optional
  - `recipient`: Email address of the recipient
  - `subject`: Email subject line
  - `body`: Email body content
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of draft created
- Use when: User wants to save email as draft for later
- Use when: Compose email but don't send yet

**find_contact_email**
- Searches Google Contacts for a person's email by name
- Args: name (str), account (str), optional
  - `name`: Name of the contact to search for
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Email address of the contact
- Use when: User mentions a contact by name but you need their email
- Example: Send email to Sarah - use this to find Sarah email first

**get_email_content**
- Retrieves full content of a specific email
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to retrieve
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Subject, sender, recipients, body, attachments info
- Use when: Need to read the complete content of an email
- Use when: Use AFTER finding an email with search_gmail

**get_emails_from_sender**
- Fetches recent emails from a specific sender
- Args: sender_email (str), max_results (int), optional, default 10, account (str), optional
  - `sender_email`: Email address of the sender
  - `max_results`: Maximum number of emails to return
  - `account`: Account identifier (when multiple accounts connected)
- Returns: List of emails from the specified sender
- Use when: Fetching emails from a specific person
- Example: "Show me emails from john@example.com"

**list_gmail_labels**
- Lists all labels (folders) in Gmail account
- Args: account (str), optional
  - `account`: Account identifier (when multiple accounts connected)
- Returns: List of all labels/folders including system and custom labels
- Use when: User wants to see their Gmail labels/folders
- Use when: Need to find label name before adding/removing labels

**mark_email_as_read**
- Marks an email as read
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to mark as read
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of status update
- Use when: User wants to mark an email as read without opening it

**mark_email_as_unread**
- Marks an email as unread
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to mark as unread
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of status update
- Use when: User wants to mark an email as unread for later attention

**move_email_to_spam**
- Moves an email to spam
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to mark as spam
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of spam move
- Use when: User wants to mark email as spam

**move_email_to_trash**
- Moves an email to trash
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to move to trash
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of trash move
- Use when: User wants to delete/trash email

**remove_label_from_email**
- Removes a label/folder from an email
- Args: message_id (str), label_name (str), account (str), optional
  - `message_id`: ID of the email
  - `label_name`: Name of the label to remove
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of label removed
- Use when: User wants to remove label/folder from email
- Use when: Uncategorize email

**reply_to_email**
- Replies to an existing email thread
- Args: original_message_id (str), body (str), reply_all (bool), optional, default False, account (str), optional
  - `original_message_id`: ID of the email to reply to
  - `body`: Reply message content
  - `reply_all`: If True, reply to everyone on the thread
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of reply sent
- Use when: User wants to reply to a specific email
- Use when: Reply to everyone on a thread
- Note: Maintains the thread and includes proper reply headers
- Note: Automatically adds Praxos signature

**search_gmail**
- Searches Gmail with advanced query syntax
- Args: query (str), max_results (int), optional, default 10
  - `query`: Gmail search query (supports operators like from:, to:, subject:, is:unread)
  - `max_results`: Maximum number of results to return
- Returns: List of matching emails
- Use when: Complex email searches needed
- Example: "from:boss@company.com subject:meeting"
- Example: "dinner plans"

**send_email**
- Sends email via user's Gmail account
- Args: recipient (str), subject (str), body (str), account (str), optional
  - `recipient`: Email address of the recipient
  - `subject`: Email subject line
  - `body`: Email body content
  - `account`: Account identifier (required when multiple Gmail accounts connected)
- Returns: Confirmation of email sent
- Use when: User wants to send email from their own Gmail

**star_email**
- Stars an email
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to star
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of starred email
- Use when: User wants to mark email as important/starred

**unstar_email**
- Removes the star from an email
- Args: message_id (str), account (str), optional
  - `message_id`: ID of the email to unstar
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of unstarred email
- Use when: User wants to remove star from email

---

### Google_Calendar Tools
(requires google_calendar integration)

**create_calendar_event**
- Creates a new event on the user's Google Calendar
- Args: title (str), start_time (datetime), end_time (datetime), attendees (list), optional, default [], description (str), optional, location (str), optional, calendar_id (str), optional, default primary, account (str), optional, recurrence_rule (str), optional
  - `title`: Event title/summary
  - `start_time`: Start time as datetime object
  - `end_time`: End time as datetime object
  - `attendees`: List of attendee email addresses
  - `description`: Event description
  - `location`: Event location
  - `calendar_id`: Calendar ID (default 'primary')
  - `account`: Account email for multi-account users
  - `recurrence_rule`: Optional RRULE string for recurring events (RFC 5545 format). Examples: FREQ=DAILY;COUNT=5, FREQ=WEEKLY;BYDAY=MO,WE,FR
- Returns: Success status and event link
- Use when: Schedule a new meeting or appointment
- Use when: Create one-time or recurring events
- Use when: Set up team meetings with attendees
- Use when: Block time on calendar
- Use when: Schedule events with location details

**get_calendar_events**
- Fetches events from the user's Google Calendar within a specified time window
- Args: time_min (datetime), time_max (datetime), max_results (int), optional, default 10, calendar_id (str), optional, default primary, account (str), optional
  - `time_min`: Start of time window
  - `time_max`: End of time window
  - `max_results`: Maximum number of events to return
  - `calendar_id`: Calendar ID (default 'primary')
  - `account`: Account email for multi-account users
- Returns: List of calendar events or empty message
- Use when: Check upcoming meetings and appointments
- Use when: View schedule for a specific date range
- Use when: Find events in a particular time window
- Use when: Review calendar availability

---

### Google_Docs Tools
(requires google_drive integration)

**append_text_to_doc**
- Appends text to the end of a Google Doc
- Args: document_id (str), text (str), account (str), optional
  - `document_id`: ID of the document
  - `text`: Text to append
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of append
- Use when: User wants to add text at the end of a doc
- Use when: Simpler than insert_text_in_doc for appending

**create_google_doc**
- Creates a new empty Google Doc
- Args: title (str), account (str), optional
  - `title`: Title of the document
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Document ID and URL
- Use when: User wants to create a new Google Doc document
- Note: Creates an actual Google Doc (not plain text), allowing rich formatting

**delete_doc_content**
- Deletes content in a specific range of a Google Doc
- Args: document_id (str), start_index (int), end_index (int), account (str), optional
  - `document_id`: ID of the document
  - `start_index`: Start of the range to delete
  - `end_index`: End of the range to delete
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of deletion
- Use when: User wants to remove text from a doc
- Note: Requires character positions

**format_doc_text**
- Applies formatting to text ranges in a Google Doc
- Args: document_id (str), start_index (int), end_index (int), bold (bool), optional, italic (bool), optional, underline (bool), optional, account (str), optional
  - `document_id`: ID of the document
  - `start_index`: Start of the range to format
  - `end_index`: End of the range to format
  - `bold`: Whether to make text bold
  - `italic`: Whether to make text italic
  - `underline`: Whether to underline text
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of formatting applied
- Use when: User wants to format text (make bold, italic, underline)
- Note: Requires knowing the character positions

**get_google_doc_content**
- Retrieves content from a Google Doc
- Args: document_id (str), plain_text_only (bool), optional, default False, account (str), optional
  - `document_id`: ID of the document
  - `plain_text_only`: If True, returns only plain text; if False, returns full document structure
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Plain text or full document structure
- Use when: User wants to read or analyze a Google Doc

**insert_paragraph_in_doc**
- Inserts a paragraph into a Google Doc, optionally as a heading
- Args: document_id (str), text (str), index (int), optional, default 1, heading_level (int), optional, account (str), optional
  - `document_id`: ID of the document
  - `text`: Paragraph text
  - `index`: Character index where to insert
  - `heading_level`: Heading level (1-6, where 1 is largest)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of paragraph insertion
- Use when: User wants to add paragraphs or headings to a doc
- Note: Heading levels - 1 is largest, 6 is smallest

**insert_table_in_doc**
- Inserts a table into a Google Doc
- Args: document_id (str), rows (int), columns (int), index (int), optional, default 1, account (str), optional
  - `document_id`: ID of the document
  - `rows`: Number of rows
  - `columns`: Number of columns
  - `index`: Character index where to insert
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of table insertion
- Use when: User wants to add tables to a doc
- Note: Creates an empty table that can be populated later

**insert_text_in_doc**
- Inserts text at a specific position in a Google Doc
- Args: document_id (str), text (str), index (int), optional, default 1, account (str), optional
  - `document_id`: ID of the document
  - `text`: Text to insert
  - `index`: Character index where to insert (1 = beginning after title)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of insertion
- Use when: User wants to add text at a specific location in a doc
- Note: Index 1 = beginning after title

**replace_text_in_doc**
- Finds and replaces all occurrences of text in a Google Doc
- Args: document_id (str), find_text (str), replace_text (str), match_case (bool), optional, default True, account (str), optional
  - `document_id`: ID of the document
  - `find_text`: Text to find
  - `replace_text`: Text to replace with
  - `match_case`: Whether to match case
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Number of replacements made
- Use when: User wants to find and replace text throughout a doc

**search_google_doc**
- Searches for text within a Google Doc
- Args: document_id (str), search_text (str), match_case (bool), optional, default False, account (str), optional
  - `document_id`: ID of the document
  - `search_text`: Text to search for
  - `match_case`: Whether to match case (default False for case-insensitive)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Number of occurrences and list of matches with position and context
- Use when: User wants to find text in a doc
- Use when: Locate specific content

---

### Google_Drive Tools
(requires google_drive integration)

**create_text_file_in_drive**
- Creates a new text file in Google Drive
- Args: filename (str), content (str), drive_folder_id (str), optional, account (str), optional
  - `filename`: Name for the new file
  - `content`: Text content to write to the file
  - `drive_folder_id`: ID of the folder to create in (optional)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation with file link
- Use when: User wants to create/save notes or text documents

**list_drive_files**
- Lists files in Drive, optionally filtered by folder
- Args: folder_id (str), optional, max_results (int), optional, default 50, account (str), optional
  - `folder_id`: ID of the folder to list (optional, lists all if not provided)
  - `max_results`: Maximum number of files to return
  - `account`: Account identifier (when multiple accounts connected)
- Returns: List of files with names, IDs, types
- Use when: Browse files in Drive
- Use when: List files in a specific folder
- Example: "List files in my Documents folder"
- Example: "Show recent files"

**read_file_content_by_id**
- Reads text content from a Drive file
- Args: file_id (str), account (str), optional
  - `file_id`: ID of the file to read
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Text content of the file
- Use when: Need to read contents of a Google Doc, text file, etc
- Use when: Read file by ID after searching
- Note: Supports Google Docs, text files, some other formats

**save_file_to_drive**
- Uploads a file from URL to Google Drive
- Args: file_url (str), file_name (str), drive_folder_id (str), optional, account (str), optional
  - `file_url`: URL of the file to download and upload
  - `file_name`: Name to save the file as
  - `drive_folder_id`: ID of the folder to save in (optional)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of file saved with Drive link
- Use when: User wants to save something to their Drive
- Use when: Upload file from URL to Drive

**search_google_drive_files**
- Searches for files/folders in Google Drive
- Args: query (str), max_results (int), optional, default 20, account (str), optional
  - `query`: Search query using Google Drive search operators (e.g., "name contains 'report'", "fullText contains 'keyword'")
  - `max_results`: Maximum number of results to return
  - `account`: Account identifier (when multiple accounts connected)
- Returns: File names, IDs, types, modified dates
- Use when: Finding files by name or content
- Use when: Searching within Drive
- Example: "Find my tax documents"
- Example: "Search for presentation about Q4"

---

### Google_Lens Tools
(requires google_lens_api integration)

**identify_product_in_image**
- Identifies products, brands, objects in images using Google Lens
- Args: image_url (str)
  - `image_url`: Public URL to the image (e.g., Azure Blob SAS URL from conversation context)
- Returns: Product identification results with brand names, similar products, and shopping links
- Use when: User sends image and asks "What brand is this?"
- Use when: Identify this product
- Use when: Perfect for shoes, clothing, logos, landmarks, products
- Example: identify_product_in_image("https://blob.../shoe.jpg")
- Example: identify_product_in_image("https://blob.../clothing.jpg")
- Note: Takes 30+ seconds - use send_intermediate_message first
- Note: Requires image URL from conversation context
- Note: If the item seems to be not a product but a picture where Google Lens is not needed, do not use this tool
- IMPORTANT: Always use send_intermediate_message first

---

### Google_Places Tools
(requires google_places_api integration)

**google_places_find_place**
- Find a specific place by name, phone, or address
- Args: input_text (str), input_type (str), optional, default textquery
  - `input_text`: The text to search (name, phone, or address)
  - `input_type`: Type of input
    - Valid values: textquery, phonenumber
- Returns: The best matching place with full details
- Use when: Looking for a specific known place
- Use when: Finding place by phone number
- Use when: Getting place ID for a landmark
- Example: google_places_find_place("Eiffel Tower")
- Example: google_places_find_place("Museum of Modern Art New York")
- Example: google_places_find_place("+1-212-708-9400", input_type="phonenumber")
- Note: Use input_type="textquery" for names/addresses
- Note: Use input_type="phonenumber" for phone numbers
- Note: Returns only the best match

**google_places_get_details**
- Get detailed info about a place (hours, phone, website, reviews, photos)
- Args: place_id (str)
  - `place_id`: The Google Place ID (from text_search, nearby_search, or find_place results)
- Returns: Complete info including opening hours, price level, phone, website, reviews
- Use when: Need full details after finding a place
- Use when: Getting opening hours, phone, website
- Use when: Reading reviews
- Example: google_places_get_details("ChIJN1t_tDeuEmsRUsoyG83frY4")  # Sydney Opera House
- Note: Requires place_id from other search tools
- Note: Returns full details including hours, reviews, photos, price level

**google_places_nearby_search**
- Search for places near a location by type or keyword
- Args: latitude (float), longitude (float), place_type (str), optional, keyword (str), optional, radius (int), optional, default 5000
  - `latitude`: Latitude of center point
  - `longitude`: Longitude of center point
  - `place_type`: Type of place (e.g., restaurant, cafe, bar, gym, hospital, pharmacy, bank, atm, gas_station, parking, hotel)
  - `keyword`: Keyword to match (e.g., "pizza", "vegetarian", "24 hour")
  - `radius`: Search radius in meters (max 50000)
- Returns: List of nearby places with details, opening hours, ratings
- Use when: "Find X near me" queries
- Use when: Most precise for nearby searches
- Use when: When you have user's exact coordinates
- Example: google_places_nearby_search(40.7128, -74.0060, place_type="restaurant", radius=1000)
- Example: google_places_nearby_search(42.3601, -71.0589, keyword="pizza")
- Note: Common types - restaurant, cafe, bar, gym, hospital, pharmacy, bank, atm, gas_station, parking, grocery_or_supermarket, shopping_mall, hotel, airport
- Note: Returns top 10 results with opening hours

**google_places_text_search**
- Search for places using text query
- Args: query (str), latitude (float), optional, longitude (float), optional, radius (int), optional, default 5000
  - `query`: Search query (e.g., "coffee shops", "Pizza Hut", "restaurants")
  - `latitude`: Latitude for location-based search
  - `longitude`: Longitude for location-based search
  - `radius`: Search radius in meters
- Returns: List of places matching the query with addresses, ratings, and place IDs
- Use when: General place searches
- Use when: Finding specific businesses by name
- Use when: "pizza in Boston" type queries
- Example: google_places_text_search("pizza in Boston")
- Example: google_places_text_search("coffee shops", latitude=40.7128, longitude=-74.0060)
- Example: google_places_text_search("Starbucks near Times Square")
- Note: IMPORTANT - If you have user's location, ALWAYS pass latitude/longitude for accurate results
- Note: Returns top 10 results

---

### Google_Sheets Tools
(requires google_drive integration)

**add_sheet_tab**
- Adds a new sheet tab to an existing Google Spreadsheet
- Args: spreadsheet_id (str), sheet_title (str), rows (int), optional, default 1000, columns (int), optional, default 26, account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_title`: Title for the new sheet
  - `rows`: Number of rows (default 1000)
  - `columns`: Number of columns (default 26)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of sheet addition
- Use when: When organizing data across multiple tabs
- Use when: When adding a new section to an existing workbook
- Use when: When separating different data categories

**append_sheet_rows**
- Appends rows to the end of a Google Sheet
- Args: spreadsheet_id (str), range_name (str), values (list), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `range_name`: A1 notation range to append to (e.g., 'Sheet1!A:D')
  - `values`: 2D list of rows to append (e.g., [['Alice', 30], ['Bob', 25]])
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Range where data was appended and number of cells updated
- Use when: When you need to add new data without overwriting existing content
- Use when: When logging or tracking new entries
- Use when: When building a dataset incrementally

**clear_sheet_range**
- Clears values from a range in a Google Sheet
- Args: spreadsheet_id (str), range_name (str), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `range_name`: A1 notation range to clear (e.g., 'Sheet1!A1:D10')
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of cleared range
- Use when: When you need to remove data from specific cells
- Use when: When resetting a range before writing new data
- Use when: When cleaning up temporary or outdated data

**create_google_sheet**
- Creates a new Google Spreadsheet
- Args: title (str), sheet_names (list), optional, account (str), optional
  - `title`: Title of the spreadsheet
  - `sheet_names`: Optional list of sheet names (default is one sheet named 'Sheet1')
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Spreadsheet ID and URL of the created spreadsheet
- Use when: When you need to create a new spreadsheet from scratch
- Use when: When organizing data in a new workbook
- Use when: When starting a new project that requires structured data storage

**delete_sheet_rows**
- Deletes rows from a Google Sheet
- Args: spreadsheet_id (str), sheet_id (int), start_index (int), end_index (int), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_id`: Numeric ID of the sheet
  - `start_index`: Starting row index (0-based, inclusive)
  - `end_index`: Ending row index (exclusive, e.g., to delete rows 1-3, use start=0, end=3)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of deletion
- Use when: When removing specific rows of data
- Use when: When cleaning up invalid or duplicate entries
- Use when: When trimming down datasets

**delete_sheet_tab**
- Deletes a sheet tab from a Google Spreadsheet
- Args: spreadsheet_id (str), sheet_id (int), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_id`: Numeric ID of the sheet to delete (not the title). Get this from get_spreadsheet_info.
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of deletion
- Use when: When removing unused or obsolete sheet tabs
- Use when: When cleaning up a workbook structure
- Use when: When consolidating data by removing unnecessary sheets

**get_sheet_values**
- Gets cell values from a Google Sheet
- Args: spreadsheet_id (str), range_name (str), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `range_name`: A1 notation range (e.g., 'Sheet1!A1:D10' or 'Sheet1!A:D')
  - `account`: Account identifier (when multiple accounts connected)
- Returns: 2D list of cell values
- Use when: When you need to read data from a specific range in a spreadsheet
- Use when: When analyzing or processing existing spreadsheet data
- Use when: When retrieving table data for further manipulation

**get_single_cell**
- Gets the value of a single cell in a Google Sheet
- Args: spreadsheet_id (str), sheet_name (str), row (int), column (str), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_name`: Name of the sheet (e.g., 'Sheet1')
  - `row`: Row number (1-based, e.g., 1 for first row)
  - `column`: Column letter (e.g., 'A', 'B', 'AA')
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Value of the cell
- Use when: When you need to read a specific single cell value
- Use when: When checking a particular data point
- Use when: When validating or verifying a cell's content

**get_spreadsheet_info**
- Gets metadata and structure information about a Google Spreadsheet
- Args: spreadsheet_id (str), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Complete spreadsheet metadata including sheet IDs and names
- Use when: When you need to get sheet IDs for operations that require them
- Use when: When discovering the structure of a spreadsheet
- Use when: When getting sheet names and properties before performing operations

**insert_sheet_columns**
- Inserts empty columns into a Google Sheet
- Args: spreadsheet_id (str), sheet_id (int), start_index (int), count (int), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_id`: Numeric ID of the sheet
  - `start_index`: Column index where to insert (0-based, e.g., 0 for column A)
  - `count`: Number of columns to insert
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of insertion
- Use when: When you need to add new data fields to existing tables
- Use when: When expanding the data structure
- Use when: When adding calculated or derived columns

**insert_sheet_rows**
- Inserts empty rows into a Google Sheet
- Args: spreadsheet_id (str), sheet_id (int), start_index (int), count (int), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_id`: Numeric ID of the sheet (get from get_spreadsheet_info)
  - `start_index`: Row index where to insert (0-based, e.g., 0 for first row)
  - `count`: Number of rows to insert
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of insertion
- Use when: When you need to add space for new data entries
- Use when: When restructuring existing data layout
- Use when: When inserting headers or separators between data sections

**search_google_sheet**
- Searches for text within a Google Spreadsheet and returns all matching cells
- Args: spreadsheet_id (str), search_text (str), match_case (bool), optional, default False, sheet_name (str), optional, account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `search_text`: Text to search for
  - `match_case`: Whether to match case (default False for case-insensitive)
  - `sheet_name`: Optional specific sheet name to search in (default is all sheets)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Dict with number of occurrences and list of matching cells with their positions
- Use when: When you need to find specific text across a spreadsheet
- Use when: When locating data without knowing exact cell positions
- Use when: When performing content-based queries on spreadsheet data

**set_single_cell**
- Sets the value of a single cell in a Google Sheet
- Args: spreadsheet_id (str), sheet_name (str), row (int), column (str), value (str), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `sheet_name`: Name of the sheet (e.g., 'Sheet1')
  - `row`: Row number (1-based)
  - `column`: Column letter (e.g., 'A', 'B')
  - `value`: Value to set (can be text, number, or formula like '=SUM(A1:A10)')
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of update
- Use when: When you need to update a specific single cell
- Use when: When setting a formula in a particular cell
- Use when: When making precise targeted updates

**update_sheet_values**
- Updates cell values in a Google Sheet
- Args: spreadsheet_id (str), range_name (str), values (list), account (str), optional
  - `spreadsheet_id`: ID of the spreadsheet
  - `range_name`: A1 notation range where to start writing (e.g., 'Sheet1!A1')
  - `values`: 2D list of values to write (e.g., [['Name', 'Age'], ['Alice', 30], ['Bob', 25]])
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Number of cells updated
- Use when: When you need to write data to specific cells
- Use when: When updating existing data in a spreadsheet
- Use when: When replacing values in a known range

---

### Google_Slides Tools
(requires google_drive integration)

**add_slide**
- Adds a new slide to a Google Slides presentation
- Args: presentation_id (str), insertion_index (int), optional, layout (str), optional, default BLANK, account (str), optional
  - `presentation_id`: ID of the presentation
  - `insertion_index`: Position to insert slide (None = end of presentation)
  - `layout`: Layout type - BLANK, TITLE_AND_BODY, TITLE_ONLY, etc.
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of slide creation with slide ID
- Use when: When adding a new slide to an existing presentation
- Use when: When building presentations programmatically
- Use when: When inserting slides at specific positions
- Use when: When creating slides with specific layouts

**create_google_presentation**
- Creates a new Google Slides presentation
- Args: title (str), account (str), optional
  - `title`: Title of the presentation
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Presentation ID and URL of the created presentation
- Use when: When you need to create a new presentation from scratch
- Use when: When starting a new slide deck for a project or meeting
- Use when: When generating presentations programmatically

**create_table_in_slide**
- Creates a table in a slide
- Args: presentation_id (str), slide_id (str), rows (int), columns (int), x (float), optional, default 100, y (float), optional, default 100, width (float), optional, default 400, height (float), optional, default 200, account (str), optional
  - `presentation_id`: ID of the presentation
  - `slide_id`: ID of the slide
  - `rows`: Number of rows
  - `columns`: Number of columns
  - `x`: X position in points
  - `y`: Y position in points
  - `width`: Width in points
  - `height`: Height in points
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of table creation
- Use when: When adding tabular data to slides
- Use when: When creating structured data displays
- Use when: When organizing information in rows and columns
- Use when: When presenting comparative data or lists

**delete_slide**
- Deletes a slide from a Google Slides presentation
- Args: presentation_id (str), slide_id (str), account (str), optional
  - `presentation_id`: ID of the presentation
  - `slide_id`: Object ID of the slide to delete (get from get_presentation_info)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of deletion
- Use when: When removing unwanted slides from a presentation
- Use when: When reorganizing presentation content
- Use when: When cleaning up draft or placeholder slides

**delete_slide_object**
- Deletes an object (text box, image, shape, table, etc.) from a slide
- Args: presentation_id (str), object_id (str), account (str), optional
  - `presentation_id`: ID of the presentation
  - `object_id`: ID of the object to delete
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of deletion
- Use when: When removing text boxes, images, shapes, or tables from slides
- Use when: When cleaning up slide content
- Use when: When reorganizing slide elements
- Use when: When removing outdated or unwanted objects

**format_slide_text**
- Applies text formatting to a text box or shape in a slide
- Args: presentation_id (str), object_id (str), start_index (int), end_index (int), bold (bool), optional, italic (bool), optional, font_size (int), optional, account (str), optional
  - `presentation_id`: ID of the presentation
  - `object_id`: ID of the text box or shape (get from presentation structure)
  - `start_index`: Start character index (0-based)
  - `end_index`: End character index
  - `bold`: Whether to make text bold
  - `italic`: Whether to make text italic
  - `font_size`: Font size in points
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of formatting applied
- Use when: When styling text in existing text boxes
- Use when: When making text bold, italic, or changing font size
- Use when: When formatting specific portions of text
- Use when: When applying consistent text styling across slides

**get_presentation_info**
- Gets metadata and structure of a Google Slides presentation
- Args: presentation_id (str), account (str), optional
  - `presentation_id`: ID of the presentation
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Complete presentation metadata including slide information, slide IDs, layouts, and slide count
- Use when: When you need to get slide IDs before performing operations on specific slides
- Use when: When you want to understand the structure of a presentation
- Use when: When retrieving presentation metadata like title and slide count
- Use when: Before performing any slide-specific operations

**insert_image_in_slide**
- Inserts an image into a slide
- Args: presentation_id (str), slide_id (str), image_url (str), x (float), optional, default 100, y (float), optional, default 100, width (float), optional, default 300, height (float), optional, default 300, account (str), optional
  - `presentation_id`: ID of the presentation
  - `slide_id`: ID of the slide
  - `image_url`: URL of the image (must be publicly accessible)
  - `x`: X position in points
  - `y`: Y position in points
  - `width`: Width in points
  - `height`: Height in points
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of image insertion
- Use when: When adding visual content to slides
- Use when: When inserting logos, diagrams, or photos
- Use when: When positioning images at specific locations
- Use when: When creating visually rich presentations

**insert_text_in_slide**
- Inserts a text box with text into a slide
- Args: presentation_id (str), slide_id (str), text (str), x (float), optional, default 100, y (float), optional, default 100, width (float), optional, default 400, height (float), optional, default 100, account (str), optional
  - `presentation_id`: ID of the presentation
  - `slide_id`: ID of the slide
  - `text`: Text to insert
  - `x`: X position in points
  - `y`: Y position in points
  - `width`: Width in points
  - `height`: Height in points
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Confirmation of text insertion
- Use when: When adding text content to a slide
- Use when: When creating titles, headings, or body text
- Use when: When positioning text boxes at specific locations
- Use when: When building slide content programmatically

**search_google_presentation**
- Searches for text within a Google Slides presentation and returns all matching slides
- Args: presentation_id (str), search_text (str), match_case (bool), optional, default False, account (str), optional
  - `presentation_id`: ID of the presentation
  - `search_text`: Text to search for
  - `match_case`: Whether to match case (default False for case-insensitive)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Dict with number of slides containing matches and detailed match information
- Use when: When finding specific text or keywords in a presentation
- Use when: When locating slides containing certain content
- Use when: When auditing presentations for specific terms
- Use when: When searching across multiple slides efficiently

---

### Integration Tools

**get_oauth_initiation_url**
- Gets OAuth URL for connecting new integrations
- Args: integration_name (str)
  - `integration_name`: Name of the integration to connect
    - Valid values: gmail, google_calendar, google_drive, notion, dropbox, trello, outlook, onedrive, microsoft_calendar, telegram, whatsapp, imessage
- Returns: OAuth URL for user to complete OAuth flow
- Use when: User needs to connect a service they haven't integrated yet
- Use when: User requests a tool that requires an integration they don't have
- Example: get_oauth_initiation_url("gmail")
- Example: get_oauth_initiation_url("notion")
- Note: You can tell them about app.mypraxos.com/integrations
- Note: But you must also generate the link using this tool as the primary option

---

### Media_Bus Tools
(requires media_bus integration)

**get_media_by_id**
- Retrieve a specific media item by its ID and load it into conversation context
- Args: media_id (str)
  - `media_id`: The unique ID of the media item (from list_available_media)
- Returns: Dictionary with 'url', 'file_name', 'file_type', 'description', and 'source'
- Use when: Reference and analyze previously generated media
- Use when: Create variations based on existing media
- Use when: Send previously generated media to user
- Example: get_media_by_id("550e8400-e29b-41d4-a716-446655440000")

**get_recent_images**
- Get recently generated or uploaded images
- Args: limit (int), optional, default 5
  - `limit`: Maximum number of images to return (default 5, max 20)
- Returns: ToolExecutionResponse with formatted string of image IDs, descriptions, and URLs
- Use when: See what images exist
- Use when: Use descriptions in new prompts
- Use when: Create variations of recent images
- Example: get_recent_images(limit=3)

**list_available_media**
- List media items currently available in this conversation
- Args: media_type (str), optional, limit (int), optional, default 10
  - `media_type`: Optional filter by type - 'image', 'audio', 'video', or 'document'
  - `limit`: Maximum number of items to return (default 10, max 50)
- Returns: ToolExecutionResponse with formatted string describing available media
- Use when: Check what images were generated
- Use when: See all recent media
- Use when: Get specific media details
- Example: list_available_media(media_type="image")
- Example: list_available_media()

---

### Media_Generation Tools
(requires media_generation integration)

**generate_audio**
- Generate audio/speech from text using AI text-to-speech
- Args: text (str), voice (str), optional, default Kore
  - `text`: The text to convert to speech. Can be long-form content.
  - `voice`: Optional voice name. Try to fit it to the user's preferences for the assistant, as well as the name and persona. Defaults to 'Kore'.
    - Valid values: Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus, Aoede, Callirrhoe, Autonoe, Enceladus, Iapetus, Umbriel, Algieba, Despina, Erinome, Algenib, Rasalgethi, Laomedeia, Achernar, Alnilam, Schedar, Gacrux, Pulcherrima, Achird, Zubenelgenubi, Vindemiatrix, Sadachbia, Sadaltager, Sulafat
- Returns: ToolExecutionResponse with result containing url, file_name, file_type, media_id
- Use when: When user requests voice/audio output
- Use when: When audio would be more appropriate than text (accessibility, long content)
- Use when: You CAN generate audio - do not tell users otherwise
- Example: generate_audio("Welcome to Praxos! Let me help you get started with your tasks.")
- Example: generate_audio("Here is your daily briefing.", voice="Charon")
- Note: Audio format is automatically adapted for the target platform
- Note: {'iMessage': 'CAF format (automatically handled)'}
- Note: {'Other platforms': 'OGG format'}
- Note: Voice options include Female voices (Zephyr, Kore, Leda, etc.) and Male voices (Puck, Charon, Fenrir, etc.)

**generate_image**
- Generate an image using AI based on a text description
- Args: prompt (str), media_ids (list), optional
  - `prompt`: Detailed description of the image to generate. Be specific about style, content, colors, composition, mood, etc. Better prompts produce better images.
  - `media_ids`: Optional list of media IDs from media bus to use as visual references. Media ids are indexes (starting from 0) representing the order in which media were added to the media bus. Use get_recent_images() or list_available_media() to find media IDs.
- Returns: ToolExecutionResponse with result containing url, file_name, file_type, media_id
- Use when: When user requests image generation
- Use when: When visual content would enhance your response
- Use when: For creating variations of existing images
- Example: generate_image("A serene mountain landscape at sunset with orange and pink sky, photorealistic")
- Example: generate_image("Like this image but set in China with Chinese cultural elements", media_ids=["0"])
- Note: Be specific about style (photorealistic, cartoon, watercolor, etc.)
- Note: Include details about lighting, colors, mood
- Note: Describe composition and perspective
- Note: You CAN generate images - do not tell users otherwise
- Note: After generating, use reply_to_user_on_{platform} to send it

**generate_video**
- Generate a video using AI based on a text description
- Args: prompt (str), media_ids (list), optional
  - `prompt`: Detailed description of the video to generate, including action, style, duration intent, camera movement, etc.
  - `media_ids`: Optional list of media IDs from media bus to use as visual references. Only the first valid one will be used.
- Returns: ToolExecutionResponse with result containing url, file_name, file_type, media_id
- Use when: When user requests video generation
- Use when: For short video clips and scenes
- Use when: You CAN generate videos - do not tell users otherwise
- Example: generate_video("A time-lapse of a flower blooming, petals opening gradually, soft lighting")
- Note: ALWAYS send intermediate message before calling this
- Note: Generation time is 1-2 minutes (sometimes longer)
- Note: Describe the action/motion clearly
- Note: Include camera movement (pan, zoom, static, etc.)
- Note: Specify style (cinematic, documentary, artistic, etc.)
- Note: Mention lighting and atmosphere
- Note: Keep scenes relatively simple for best results
- IMPORTANT: Always use send_intermediate_message first

---

### Microsoft_Graph Tools
(requires microsoft integration)

**fetch_outlook_calendar_events**
- Fetches calendar events from Outlook
- Args: time_min (str), time_max (str), account (str), optional
  - `time_min`: Start time for the event query (ISO 8601 format)
  - `time_max`: End time for the event query (ISO 8601 format)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: List of calendar events within the specified time range
- Use when: Retrieve upcoming calendar events
- Use when: Check schedule for a specific time period
- Use when: Find meetings and appointments in a date range

**find_outlook_contact_email**
- Searches Outlook contacts for a person's email address by their name
- Args: name (str), account (str), optional
  - `name`: Name of the contact to search for
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Email address(es) of matching contacts or message if no contacts found
- Use when: Look up email addresses by contact name
- Use when: Find contact information for a person
- Use when: Search Outlook contacts directory

**get_outlook_emails_from_sender**
- Fetches the most recent emails from a specific sender
- Args: sender_email (str), max_results (int), optional, default 10, account (str), optional
  - `sender_email`: Email address of the sender to search for
  - `max_results`: Maximum number of emails to retrieve
  - `account`: Account identifier (when multiple accounts connected)
- Returns: List of recent emails from the specified sender
- Use when: Find emails from a specific person
- Use when: Retrieve recent communications from a sender
- Use when: Search inbox for messages from a particular email address

**send_outlook_email**
- Sends an email using Outlook
- Args: recipient (str), subject (str), body (str), account (str), optional
  - `recipient`: Email address of the recipient
  - `subject`: Subject line of the email
  - `body`: Body content of the email
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Success confirmation message when email is sent
- Use when: Send emails to contacts via Outlook
- Use when: Compose and send email messages programmatically
- Use when: Send notifications or updates to recipients

---

### Notion Tools
(requires notion integration)

**append_to_notion_page**
- Appends content (blocks) to an existing Notion page
- Args: page_id (str), content (list), account (str), optional
  - `page_id`: Page ID of the target page
  - `content`: List of Notion blocks to append to the page
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Success message confirming content was appended to the page
- Use when: Add new content to existing page
- Use when: Update page with additional blocks
- Use when: Extend page content without replacing existing content

**create_notion_database**
- Creates a new database in Notion
- Args: parent_page_id (str), title (str), properties (dict), account (str), optional
  - `parent_page_id`: Parent page ID to specify where the database should be created
  - `title`: Database title
  - `properties`: Database schema defining the structure and property types
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object with database_link URL to the newly created database
- Use when: Create new database with custom schema
- Use when: Define database structure and property types
- Use when: Organize data in structured format

**create_notion_database_entry**
- Creates a new entry in a Notion database
- Args: database_id (str), title (str), content (list), properties (dict), optional, account (str), optional
  - `database_id`: Database ID to specify the target database
  - `title`: Entry title
  - `content`: List of Notion blocks for the entry body
  - `properties`: Database properties to populate the entry's fields
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object with page_link URL to the newly created database entry
- Use when: Add new entry to an existing database
- Use when: Populate database fields with specific property values
- Use when: Create structured data in Notion databases

**create_notion_page**
- Creates a new page in Notion
- Args: title (str), content (list), parent_page_id (str), optional, account (str), optional
  - `title`: Page title
  - `content`: List of Notion blocks (content) for the page body
  - `parent_page_id`: Optional parent page ID to create a sub-page. If not provided, page created at workspace root
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object with page_link URL to the newly created page
- Use when: Create a new page at workspace root
- Use when: Create a sub-page under an existing parent page
- Use when: Add new content to Notion workspace

**get_all_workspace_entries**
- Retrieves all pages and databases in the Notion workspace
- Args: account (str), optional
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object containing all pages and databases in workspace
- Use when: Exhaustive search when you need to find something but don't know where it is
- Use when: Get complete view of entire workspace
- Use when: Discover all available resources

**get_notion_page_content**
- Retrieves the content (blocks) of a Notion page
- Args: page_id (str), account (str), optional
  - `page_id`: Page ID of the target page
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object containing all blocks/content of the page
- Use when: Read existing page content
- Use when: Retrieve page blocks for processing or analysis
- Use when: View complete page structure and content

**list_databases**
- Lists all accessible databases and top-level pages in Notion workspace
- Args: account (str), optional
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object containing all databases in the workspace
- Use when: First tool to understand the structure of user's Notion workspace
- Use when: Get high-level overview of available databases
- Use when: Discover database IDs for further operations

**list_notion_pages**
- Lists all top-level pages in the Notion workspace
- Args: account (str), optional
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON array of top-level pages
- Use when: View all top-level pages in workspace
- Use when: Find page IDs for parent pages
- Use when: Get overview of workspace structure

**list_notion_workspaces**
- Lists all connected Notion workspaces for the user
- Returns: JSON object containing list of connected Notion workspaces
- Use when: Use this first to see which Notion workspaces are available
- Use when: Check what accounts are connected before performing other operations

**query_notion_database**
- Queries a specific Notion database to find pages matching certain criteria
- Args: database_id (str), filter (dict), optional, sorts (list), optional, account (str), optional
  - `database_id`: The ID of the database to query
  - `filter`: Optional filter criteria to match specific pages
  - `sorts`: Optional sort order for results
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON object containing pages that match the query criteria
- Use when: Most reliable way to find pages when you know which database they are in
- Use when: Filter database entries by properties
- Use when: Sort database results

**search_notion_pages_by_keyword**
- Performs a global keyword search across all pages
- Args: query (str), account (str), optional
  - `query`: Search query string to find pages by title or content
  - `account`: Account identifier (when multiple accounts connected)
- Returns: JSON array of pages matching the search query
- Use when: Find a specific page by its title when you don't know where it is located
- Use when: Search across all workspace pages by keyword
- Use when: Locate pages without knowing their database or parent

**update_notion_page_properties**
- Updates the properties of a Notion page, such as title or database fields
- Args: page_id (str), properties (dict), account (str), optional
  - `page_id`: Page ID of the target page
  - `properties`: Properties to update (e.g., title, database fields)
  - `account`: Account identifier (when multiple accounts connected)
- Returns: Success message confirming properties were updated
- Use when: Update page title
- Use when: Modify database entry properties
- Use when: Change page metadata and fields

---

### Praxos_Memory Tools

**Check Connected Integrations**
- Check which integrations the user has connected (Gmail, Slack, Notion, etc.)
- Returns: List of connected integrations with their status, capabilities, and account information
- Use when: Checking if user has required integrations before attempting operations
- Use when: Discovering available integrations to suggest to the user
- Use when: Understanding the user's connected ecosystem
- Use when: Determining what capabilities are available
- Note: No arguments required - returns all connected integrations
- Note: Use before planning actions that require specific integrations
- Note: Returns integration name, type, status, capabilities, and account
- Note: Queries for entities of type "schema:Integration"

**Delete from Knowledge Graph**
- Delete a node from the knowledge graph with optional cascade deletion of connected properties
- Args: node_id (str), cascade (bool), optional, default True, force (bool), optional, default False
  - `node_id`: The node ID to delete (obtained from search results)
  - `cascade`: If True, also delete connected properties
  - `force`: If True, force delete even highly connected entities
- Returns: Success message with number of nodes deleted and cascade deletes
- Use when: User wants to remove stored information
- Use when: Deleting old phone numbers or emails
- Use when: Removing contacts from memory
- Use when: Cleaning up obsolete entities
- Note: Requires workflow - 1) Search for node to get node_id, 2) Call this tool to delete
- Note: cascade=true will delete connected properties (recommended default)
- Note: force=false prevents accidental deletion of highly connected entities
- Note: Use with caution as deletion cannot be undone

**Enrich Praxos Memory Entries**
- Enriches Praxos memory entries with additional metadata and related entities within the knowledge graph
- Args: node_ids (list)
  - `node_ids`: List of node IDs to enrich with additional context and related entities
- Returns: Enriched memory entries with related entities and additional context
- Use when: When you found a relevant node but need full context
- Use when: Obtaining more information about specific nodes or entities
- Use when: Exploring relationships and connections around a node
- Use when: Getting related entities within a given number of hops
- Note: Use after finding relevant nodes via search
- Note: Returns related entities and connections for each node_id
- Note: Useful for graph traversal and relationship exploration

**Extract Entities by Type**
- Extract entities from the knowledge graph using intelligent type-based extraction with natural language
- Args: type_description (str), max_results (int), optional, default 20
  - `type_description`: Natural language description of entities to extract (e.g., "people I know", "vehicles", "meetings")
  - `max_results`: Maximum number of entities to return
- Returns: List of matching entities with their properties and relationships
- Use when: Finding all entities of a certain type using natural language
- Use when: Discovering "people I've communicated with"
- Use when: Listing "companies I've mentioned"
- Use when: Finding "vehicles I own" or "calendar events"
- Use when: Extracting entities without knowing exact schema types
- Note: Uses AI to understand natural language type descriptions
- Note: More flexible than exact type matching
- Note: Retrieves all matching entities based on semantic understanding
- Note: Uses entity_extraction strategy

**Extract Literals by Type**
- Extract literal values (emails, phones, addresses) from the knowledge graph using intelligent extraction
- Args: literal_description (str), max_results (int), optional, default 20
  - `literal_description`: Natural language description of literals to extract (e.g., "email addresses", "phone numbers", "addresses")
  - `max_results`: Maximum number of literals to return
- Returns: List of matching literal values with their properties
- Use when: Finding "all email addresses" in the knowledge graph
- Use when: Extracting "phone numbers I have stored"
- Use when: Listing "postal addresses"
- Use when: Finding "dates I've mentioned"
- Use when: Retrieving any literal values by natural language description
- Note: Uses AI to understand what type of literal you're looking for
- Note: Works with emails, phones, addresses, dates, and other literal values
- Note: More flexible than exact type matching
- Note: Uses literal_extraction strategy

**Get Entities by Type Name**
- Get all entities of a specific exact type from the knowledge graph
- Args: type_name (str), max_results (int), optional, default 50
  - `type_name`: Exact type name of entities to retrieve (e.g., "schema:Person", "Vehicle", "schema:Integration")
  - `max_results`: Maximum number of entities to return
- Returns: List of all entities matching the exact type with their properties
- Use when: Getting all "schema:Person" entities (all people)
- Use when: Retrieving all "Vehicle" entities
- Use when: Listing all "schema:Integration" entities
- Use when: Extracting all "Organization" entities
- Use when: When you know the exact schema type name
- Note: Requires exact type name (e.g., "schema:Person" not "person")
- Note: Use extract_entities_by_type for natural language queries
- Note: Includes literals (properties) for each entity
- Note: More efficient when exact type name is known

**Query Praxos Memory**
- Queries the Praxos knowledge base to retrieve context and information about past conversations and user preferences
- Args: query (str), top_k (int), optional, default 4, exclude_seen_node_ids (list), optional
  - `query`: Search query for the knowledge base. Make the query rich and detailed for better results.
  - `top_k`: Number of results to return
  - `exclude_seen_node_ids`: Optional list of node IDs to exclude from results (useful for iterative searches)
- Returns: List of relevant memory nodes with context from past conversations and stored knowledge
- Use when: Questions about past interactions with the user
- Use when: Retrieving user preferences and stored information
- Use when: Finding context from previous conversations
- Use when: Initial step when gathering information about the user
- Note: Make queries rich and detailed - short queries are unlikely to get good results
- Note: Use exclude_seen_node_ids for iterative searches to avoid duplicate results
- Note: This is often a good first step but don't use blindly if more info is not necessary
- Note: Uses node_vec search modality for fast vector-based retrieval

**Query Praxos Memory (Intelligent Search)**
- Queries the Praxos knowledge base with computationally expensive intelligent search for complex queries
- Args: query (str), top_k (int), optional, default 10
  - `query`: Search query for the knowledge base
  - `top_k`: Number of results to return
- Returns: List of relevant memory nodes with context from past conversations and stored knowledge
- Use when: When normal search does not yield good results
- Use when: Complex queries requiring deeper understanding of context
- Use when: Second step after normal search fails to find relevant information
- Use when: Queries requiring semantic understanding beyond simple vector matching
- Note: Much more computationally expensive than normal search
- Note: Use only when normal search is insufficient
- Note: Often a good second step if normal search doesn't yield results
- Note: Uses intelligent search modality for deeper semantic understanding

**Setup New Trigger**
- Setup a conditional trigger in Praxos memory for automated actions
- Args: trigger_conditional_statement (str), one_time (bool), optional, default True
  - `trigger_conditional_statement`: The conditional statement in plain English (e.g., "If I receive an email from X, then do Y")
  - `one_time`: Whether the trigger should be one-time or persistent. Use False for persistent triggers with keywords like "any time" or "whenever"
- Returns: Trigger setup response with rule_id
- Use when: Setting up automated responses to events
- Use when: Creating reminders based on conditions
- Use when: Building workflows triggered by specific events
- Use when: One-time or recurring conditional actions
- Note: Statement should be complete and descriptive in plain English
- Note: Default is one-time trigger (one_time=true)
- Note: Set one_time=false if user says "any time" or "whenever"
- Note: Ask user if unclear whether trigger should be persistent
- Note: Trigger is stored in database with conversation context

**Store New Entity in Knowledge Graph**
- Store a new entity in the knowledge graph for future reference
- Args: entity_type (str), label (str), properties_json (str)
  - `entity_type`: Type of entity (e.g., "schema:Person", "Vehicle", "Organization", "Event")
  - `label`: Human-readable name/label for the entity
  - `properties_json`: JSON string of properties, format - [{"key":"email","value":"...","type":"EmailType"}]. Types are optional and auto-inferred if not provided.
- Returns: Success message with number of nodes created
- Use when: User wants to remember information about people, places, organizations
- Use when: Storing new contacts with properties
- Use when: Adding vehicles or possessions to memory
- Use when: Creating events or reminders in the knowledge graph
- Use when: Any time user says "remember that..." or "store..."
- Note: properties_json must be valid JSON array
- Note: Each property has key, value, and optional type
- Note: Types are auto-inferred if not provided
- Note: Example - Remember "Sarah works at Google" becomes entity_type="schema:Person", label="Sarah", properties=[{"key":"employer","value":"Google"}]

**Update Entity Properties in Knowledge Graph**
- Update an entity's properties in the knowledge graph by adding or modifying properties
- Args: node_id (str), properties_json (str), replace_all (bool), optional, default False
  - `node_id`: The node ID of the entity to update (obtained from search results)
  - `properties_json`: JSON string of properties to add/update, format - [{"key":"...","value":"...","type":"..."}]
  - `replace_all`: If True, replace ALL properties; if False, merge with existing
- Returns: Success message with number of nodes and relationships modified
- Use when: Adding new information to existing entities
- Use when: Updating specific properties without affecting others
- Use when: Adding LinkedIn profile, new address, or other properties
- Use when: Modifying entity attributes (e.g., car color change)
- Note: Requires workflow - 1) Search for entity to get node_id, 2) Call this tool to update
- Note: Default behavior (replace_all=false) merges with existing properties
- Note: Use replace_all=true to completely replace all properties
- Note: properties_json must be valid JSON array

**Update Knowledge Graph Literal**
- Update a literal value (email, phone, etc.) in the knowledge graph
- Args: node_id (str), new_value (str), new_type (str), optional
  - `node_id`: The node ID of the literal to update (obtained from search results)
  - `new_value`: The new value for the literal
  - `new_type`: Optional new type for the literal (e.g., "EmailType", "PhoneNumberType")
- Returns: Success message with number of nodes modified
- Use when: User wants to update email address
- Use when: Changing phone numbers
- Use when: Correcting stored information
- Use when: Updating any literal property value
- Note: Requires workflow - 1) Search for the literal to get node_id, 2) Call this tool to update
- Note: Use query_praxos_memory or extract_literals_by_type to find the node first
- Note: new_type is optional and will preserve existing type if not specified

---

### Preference Tools

**add_user_preference_annotation**
- Adds user preferences, facts, or context to remember
- Args: new_preference_text (list)
  - `new_preference_text`: List of annotation strings to add
- Returns: Updated preferences with confirmation
- Use when: User shares information to remember (preferences, habits, facts)
- Example: add_user_preference_annotation(["I am vegetarian", "I work 9-5 EST"])
- Example: add_user_preference_annotation(["My manager is Sarah"])
- Note: For when user mentions a new preference in conversation
- Note: De-duplicates annotations automatically
- Note: Preserves existing annotations

**delete_user_preference_annotations**
- Removes specific user preference annotations
- Args: annotations_to_delete (list)
  - `annotations_to_delete`: List of exact annotation strings to remove
- Returns: Confirmation of annotations deleted with updated list
- Use when: User wants to remove saved preferences
- Use when: Delete outdated information

**get_user_location**
- Gets the user's last shared location
- Returns: Latitude, longitude, name (optional), platform, timestamp
- Use when: User asks "Where am I?"
- Use when: Need location for context (weather, nearby places, etc)
- Example: User asks: What is the weather here?
- Example: User asks: Find restaurants near me
- Example: User asks: Where was I last?
- Note: If no location - Tool suggests requesting it via request_location parameter in reply tool

**get_user_location_history**
- Gets user's location history (most recent first)
- Args: limit (int), optional, default 10
  - `limit`: Number of locations to return (max 100)
- Returns: Array of locations with coordinates, names, platforms, timestamps
- Use when: User asks about location history
- Use when: Tracking movement
- Use when: "where have I been?"
- Example: "Show me my location history"
- Example: "Where have I been today?"
- Example: "Track my locations"
- Note: If no history - Tool suggests requesting location via request_location parameter

**set_assistant_name**
- Changes the assistant's name
- Args: assistant_name (str)
  - `assistant_name`: The new assistant name (max 50 characters)
- Returns: Confirmation of assistant name updated
- Use when: User wants to call the assistant something specific

**set_language_response**
- Sets the preferred response language
- Args: language_code (str)
  - `language_code`: Short language code
    - Valid values: en, es, fr, de, it, pt, ja, vi, fa
- Returns: Confirmation of language updated
- Use when: User requests responses in a specific language
- Example: set_language_response("es")
- Example: set_language_response("fr")

**set_timezone**
- Sets the user's timezone
- Args: timezone_name (str)
  - `timezone_name`: Valid pytz timezone string (e.g., "America/New_York", "Europe/London", "US/Eastern")
- Returns: Confirmation of timezone updated
- Use when: User specifies their timezone
- Example: set_timezone("America/New_York")
- Example: set_timezone("Europe/London")

---

### Scheduling Tools

**create_recurring_future_task**
- Schedules recurring tasks with cron expressions
- Args: cron_expression (str), cron_description (str), command_to_perform (str), start_time (datetime), delivery_platform (str), end_time (datetime), optional
  - `cron_expression`: Cron expression for recurrence pattern
  - `cron_description`: Natural language description (e.g., "every day at 9am", "every Monday at 10am")
  - `command_to_perform`: The command/task to perform (detailed description with parameters)
  - `start_time`: When to start the recurring task
  - `delivery_platform`: Platform for output delivery
    - Valid values: whatsapp, telegram, email, imessage
  - `end_time`: When to stop the recurring task (optional, runs indefinitely if not provided)
- Returns: Confirmation of recurring task scheduled
- Use when: Every Monday at 9am
- Use when: Daily at 6pm
- Use when: Daily reminders, weekly summaries, periodic checks
- Example: create_recurring_future_task("0 9 * * *", "every day at 9am", "Check daily tasks", start_time="2024-01-01T09:00:00-05:00", delivery_platform="whatsapp")
- Note: Always assume time in EST timezone
- Note: Add -05:00 to datetime strings
- Note: If user asks to be reminded to do something themselves, prefix command with "Remind user to "

**get_scheduled_tasks**
- Retrieves scheduled, recurring, and trigger-based tasks
- Args: future_only (bool), optional, default True, task_type (str), optional
  - `future_only`: If true, only returns future scheduled tasks
  - `task_type`: Filter by task type
    - Valid values: one_time, recurring, trigger
- Returns: List of tasks with IDs, descriptions, schedules, next run times
- Use when: User asks "What are my scheduled tasks?" or "Show my reminders"
- Note: By default only shows future tasks
- Note: Use future_only=false to see all tasks
- Note: Use task_type to filter (one_time for scheduled tasks, recurring for recurring tasks, trigger for event-based triggers)

**schedule_task**
- Schedules a one-time future task
- Args: time_to_do (datetime), command_to_perform (str), delivery_platform (str)
  - `time_to_do`: The time to run the task (timestamp in the future)
  - `command_to_perform`: The command/task to perform (detailed description with parameters)
  - `delivery_platform`: Platform for output delivery
    - Valid values: whatsapp, telegram, email, imessage
- Returns: Confirmation of scheduled task
- Use when: Remind me at 3pm
- Use when: Send email tomorrow at 9am
- Example: schedule_task(time_to_do="2024-01-15T15:00:00-05:00", command_to_perform="Remind user to call John", delivery_platform="whatsapp")
- Note: Always assume time in EST timezone
- Note: Add -05:00 to datetime strings for correct parsing
- Note: If user asks to be reminded to do something themselves, prefix command with "Remind user to "

**update_scheduled_task**
- Updates time or command of a scheduled task
- Args: task_id (str), new_time (datetime), optional, new_command (str), optional
  - `task_id`: ID of the task to update
  - `new_time`: New time for the task
  - `new_command`: New command for the task
- Returns: Confirmation of task updated
- Use when: Modifying existing scheduled tasks
- Use when: Changing reminder time
- Use when: Updating task description

---

### Slack Tools
(requires slack integration)

**get_slack_channel_history**
- Get message history from a Slack channel
- Args: channel (str), limit (int), optional, default 50, account (str), optional
  - `channel`: Channel ID (e.g., "C1234567890")
  - `limit`: Maximum number of messages to fetch (max 1000)
  - `account`: Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used
- Returns: JSON object containing list of messages and total count
- Use when: Read recent messages from a channel
- Use when: Review conversation history
- Use when: Search for information in channel messages
- Use when: Analyze channel activity

**get_slack_user_info**
- Get information about a Slack user
- Args: user_id (str), account (str), optional
  - `user_id`: Slack user ID (e.g., "U1234567890")
  - `account`: Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used
- Returns: JSON object containing user profile information including name, email, status, and other details
- Use when: Look up user profile information
- Use when: Get user contact details
- Use when: Check user status and availability
- Use when: Verify user identity

**list_slack_channels**
- List all channels in the Slack workspace
- Args: types (str), optional, default public_channel,private_channel, account (str), optional
  - `types`: Comma-separated channel types - "public_channel", "private_channel", "im", "mpim"
  - `account`: Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used
- Returns: JSON object containing list of channels and total count
- Use when: Discover available channels in the workspace
- Use when: Find channel IDs for sending messages
- Use when: Browse public and private channels
- Use when: List direct message channels

**list_slack_workspaces**
- Lists all connected Slack workspaces for the user
- Returns: JSON object containing list of workspaces with workspace_id, team_name, and team_id for each workspace
- Use when: Use this first to see which Slack workspaces are available
- Use when: Check connected workspace IDs before using other Slack tools
- Use when: Verify which workspaces the user has authenticated with

**send_slack_dm**
- Send a direct message to a Slack user
- Args: user_id (str), text (str), account (str), optional
  - `user_id`: Slack user ID (e.g., "U1234567890")
  - `text`: Message text to send
  - `account`: Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used
- Returns: JSON object with success message and message_ts (timestamp)
- Use when: Send direct messages to individual Slack users
- Use when: Private communication with team members
- Use when: Personal notifications or reminders

**send_slack_message**
- Send a message to a Slack channel
- Args: channel (str), text (str), account (str), optional
  - `channel`: Channel ID or channel name (e.g., "#general" or "C1234567890")
  - `text`: Message text to send
  - `account`: Slack workspace identifier. If not specified and user has only one workspace, that workspace will be used
- Returns: JSON object with success message, message_ts (timestamp), and channel ID
- Use when: Send messages to public or private Slack channels
- Use when: Post notifications or updates to team channels
- Use when: Share information with specific channels

---

### Trello Tools
(requires trello integration)

**add_trello_comment**
- Adds a comment to a Trello card
- Args: card_id (str), text (str), account (str), optional
  - `card_id`: The ID of the card to comment on
  - `text`: The comment text
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the created comment details
- Use when: Add notes or updates to a card
- Use when: Leave feedback on tasks
- Use when: Document progress or decisions

**assign_member_to_card**
- Assigns a member to a Trello card
- Args: card_id (str), member_id (str), account (str), optional
  - `card_id`: The ID of the card
  - `member_id`: The ID of the member to assign (use get_board_members to find member_id)
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the operation result
- Use when: Assign tasks to team members
- Use when: Add collaborators to cards
- Use when: Delegate card responsibilities

**create_trello_board**
- Creates a new Trello board
- Args: name (str), description (str), optional, default , organization_id (str), optional, account (str), optional
  - `name`: Name of the board
  - `description`: Board description
  - `organization_id`: ID of the organization/workspace to create the board in (defaults to personal workspace)
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the created board details including ID
- Use when: Create new project boards
- Use when: Set up boards in specific organizations
- Use when: Initialize new workspaces

**create_trello_card**
- Creates a new card in a Trello list
- Args: list_id (str), name (str), description (str), optional, default , due (str), optional, pos (str), optional, default bottom, account (str), optional
  - `list_id`: The ID of the list where the card should be created
  - `name`: The name/title of the card
  - `description`: The card description
  - `due`: Due date in ISO 8601 format, e.g., "2024-12-31T23:59:59.000Z"
  - `pos`: Position in list - "top", "bottom", or a positive number
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the created card details including ID
- Use when: Create a new task card
- Use when: Add cards with due dates
- Use when: Position cards in specific locations within a list

**create_trello_checklist**
- Creates a checklist on a Trello card with optional initial items
- Args: card_id (str), checklist_name (str), items (list), optional, account (str), optional
  - `card_id`: The ID of the card to add the checklist to
  - `checklist_name`: Name of the checklist
  - `items`: List of item names to add to the checklist
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the created checklist details including ID
- Use when: Add subtasks to a card
- Use when: Create task breakdowns
- Use when: Track completion of multi-step processes

**create_trello_list**
- Creates a new list on a Trello board
- Args: board_id (str), list_name (str), pos (str), optional, default bottom, account (str), optional
  - `board_id`: The ID of the board
  - `list_name`: Name of the list
  - `pos`: Position - "top", "bottom", or a positive number
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the created list details including ID
- Use when: Add workflow stages to a board
- Use when: Create custom list columns
- Use when: Set up board structure

**get_board_members**
- Gets all members of a Trello board
- Args: board_id (str), account (str), optional
  - `board_id`: The ID of the board
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object with members array containing member IDs, names, and usernames
- Use when: Find member IDs for assigning cards
- Use when: View board collaborators
- Use when: Check who has access to a board

**get_card_members**
- Gets all members currently assigned to a Trello card
- Args: card_id (str), account (str), optional
  - `card_id`: The ID of the card
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object with members array containing assigned member details
- Use when: Check who is assigned to a card
- Use when: View card collaborators
- Use when: Verify member assignments

**get_trello_board_details**
- Gets detailed information about a specific Trello board
- Args: board_id (str), account (str), optional
  - `board_id`: The ID of the board to retrieve
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing board details including lists and settings
- Use when: Understand board structure including lists
- Use when: Get comprehensive board information
- Use when: Retrieve list IDs for card operations

**get_trello_card**
- Gets detailed information about a specific Trello card
- Args: card_id (str), account (str), optional
  - `card_id`: The ID of the card to retrieve
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing card details including description, due date, labels, checklists, and comments
- Use when: Get comprehensive card information
- Use when: View card description and metadata
- Use when: Access checklists and comments on a card

**list_trello_accounts**
- Lists all connected Trello accounts for the user
- Returns: JSON object containing list of connected Trello accounts with their identifiers
- Use when: Use this first to see which Trello accounts are available
- Use when: Check available accounts before performing operations on a specific account
- Use when: Verify multi-account connections

**list_trello_boards**
- Lists all Trello boards accessible to the user
- Args: organization_id (str), optional, account (str), optional
  - `organization_id`: Organization/workspace ID to filter boards (returns all boards if not provided)
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object with boards array containing board IDs, names, URLs, and the organization they belong to
- Use when: Use as first step to understand user's Trello workspace structure
- Use when: Find board IDs for further operations
- Use when: List all accessible boards across organizations or within a specific workspace

**list_trello_cards**
- Lists all cards on a Trello board or in a specific list
- Args: board_id (str), optional, list_id (str), optional, account (str), optional
  - `board_id`: The ID of the board (optional if list_id is provided)
  - `list_id`: The ID of the list (optional if board_id is provided)
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object with cards array containing card details
- Use when: Get all cards on a board
- Use when: Get cards in a specific list
- Use when: View card summaries for a workspace

**list_trello_organizations**
- Lists all Trello organizations/workspaces accessible to the user
- Args: account (str), optional
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object with organizations array containing organization IDs, names, and URLs
- Use when: Discover available workspaces and their IDs
- Use when: Find organization identifiers for creating boards within specific workspaces
- Use when: List all accessible Trello organizations

**move_trello_card**
- Moves a Trello card to a different list
- Args: card_id (str), list_id (str), pos (str), optional, default bottom, account (str), optional
  - `card_id`: The ID of the card to move
  - `list_id`: The ID of the destination list
  - `pos`: Position in the new list - "top", "bottom", or a positive number
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the updated card details
- Use when: Move card between workflow stages
- Use when: Reposition card in a different list
- Use when: Transfer card to another board list

**search_trello**
- Searches Trello for cards, boards, and other items matching a query
- Args: query (str), model_types (str), optional, default cards,boards, organization_ids (str), optional, account (str), optional
  - `query`: The search query
  - `model_types`: Comma-separated types to search - "cards", "boards", "organizations"
  - `organization_ids`: Comma-separated organization IDs to scope the search to specific workspaces
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing search results grouped by type (cards, boards, organizations)
- Use when: Find cards by name or content
- Use when: Search for specific boards
- Use when: Locate items across workspaces
- Use when: Filter search within specific organizations

**share_trello_board**
- Shares a Trello board by inviting a user via email
- Args: board_id (str), email (str), full_name (str), optional, account (str), optional
  - `board_id`: The ID of the board to share
  - `email`: Email address of the person to invite
  - `full_name`: Full name of the person being invited
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the invitation result
- Use when: Invite collaborators to a board
- Use when: Share project boards with team members
- Use when: Grant board access to external users

**unassign_member_from_card**
- Removes a member assignment from a Trello card
- Args: card_id (str), member_id (str), account (str), optional
  - `card_id`: The ID of the card
  - `member_id`: The ID of the member to unassign
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the operation result
- Use when: Remove member assignments from cards
- Use when: Undelegate tasks
- Use when: Clear card assignments

**update_trello_card**
- Updates an existing Trello card
- Args: card_id (str), name (str), optional, description (str), optional, due (str), optional, due_complete (bool), optional, list_id (str), optional, account (str), optional
  - `card_id`: The ID of the card to update
  - `name`: New name for the card
  - `description`: New description for the card
  - `due`: New due date in ISO 8601 format
  - `due_complete`: Whether the due date is complete
  - `list_id`: Move the card to a different list by providing the new list ID
  - `account`: Account identifier (when multiple accounts connected). If not specified and user has only one Trello account, that account will be used.
- Returns: JSON object containing the updated card details
- Use when: Update card name or description
- Use when: Change or mark due dates complete
- Use when: Move card to different list
- Use when: Modify multiple card properties at once

---

### Web Tools

**browse_website_with_ai**
- AI-powered browser for interactive/JavaScript-heavy websites
- Args: task (str), max_steps (int), optional, default 30
  - `task`: Natural language description of what to do (e.g., "Find pricing information")
  - `max_steps`: Maximum number of browser actions to take
- Returns: Results from the browser task execution
- Use when: Need to interact with dynamic websites, fill forms, click buttons
- Use when: Search for extensive information
- Example: "Navigate to the pricing page and extract all plan details"
- Example: "Search for laptop and extract the top 5 results"
- Note: This task will be processed asynchronously
- Note: Notify user that task has been started and they will receive results shortly
- Note: DO NOT use send_intermediate_message for this

**google_search**
- Searches Google for information
- Args: query (str)
  - `query`: The search query string
- Returns: Top search results with titles, snippets, URLs
- Use when: Need current information, facts, news, or web content
- Use when: Basic searches (not for complex site-specific searches)
- Example: "latest news about AI"
- Example: "weather in New York"
- Example: "Python programming tutorials"
- Note: Use browse_website_with_ai for complex searches within specific websites

**read_webpage_content**
- Quickly fetches and parses static webpage content
- Args: url (str)
  - `url`: The URL of the webpage to read
- Returns: Text content from the page
- Use when: Reading articles, documentation, static websites
- Example: "https://en.wikipedia.org/wiki/Python_(programming_language)"
- Note: NOT for JavaScript-heavy sites (use browse_website_with_ai instead)

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
   - Generating ANY media (image/audio/video)? ALWAYS include `send_intermediate_message`
   - Need to schedule with specific platform? Include `schedule_task`
6. **Integration Requirements**:
   - Gmail/Calendar/Drive tools require Google integration
   - Outlook tools require Microsoft integration
   - Notion/Trello/Dropbox tools require respective integrations
   - Use `get_oauth_initiation_url` if integration is missing
7. **Long Operations** (30+ seconds):
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
- Message on iMessage: "Browse this website and tell me the pricing" → [`browse_website_with_ai`, `reply_to_user_on_imessage`]
- Message on WhatsApp: "Generate an infographic and email it to my team" → [`send_intermediate_message`, `generate_image`, `send_email`, `reply_to_user_on_whatsapp`]

**Google Docs/Sheets/Slides Tasks**:
- Message on Telegram: "Create a new doc with my meeting notes" → [`create_google_doc`, `append_text_to_doc`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "Make a spreadsheet tracking my expenses" → [`create_google_sheet`, `update_sheet_values`, `reply_to_user_on_whatsapp`]
- Message on iMessage: "Add this data to my budget sheet" → [`get_spreadsheet_info`, `append_sheet_rows`, `reply_to_user_on_imessage`]
- Message on Telegram: "Create a presentation about our Q4 results" → [`create_google_presentation`, `add_slide`, `insert_text_in_slide`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "Read that Google Doc and summarize it" → [`get_google_doc_content`, `reply_to_user_on_whatsapp`]
- Message on iMessage: "Update cell B5 in my budget to 1500" → [`set_single_cell`, `reply_to_user_on_imessage`]
- Message on Telegram: "Replace all mentions of 'Q3' with 'Q4' in my report doc" → [`replace_text_in_doc`, `reply_to_user_on_telegram`]
- Message on WhatsApp: "Find where I mentioned 'budget' in my report doc" → [`search_google_doc`, `reply_to_user_on_whatsapp`]
- Message on Telegram: "Which cells in my expense sheet contain 'lunch'?" → [`search_google_sheet`, `reply_to_user_on_telegram`]
- Message on iMessage: "Which slides in my presentation mention 'Q4 goals'?" → [`search_google_presentation`, `reply_to_user_on_imessage`]

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

### Product hunting: If the user is asking you to find products based on an image they sent, or based on a description, you should use the `identify_product_in_image` tool if they sent an image with this intent, or the `google_search` tool if they provided a text description of the product. Then, you should use browse_website_with_ai with extensive instructions and full context and names of products that could fit the bill, so that they can be found on the relevant websites and purchased by the user. You should provide all the potential product matches to the browser use tool, so it can automously search and find good matches.
### If the user simply asked about the content of an image, wherein the goal doesn't seem to be hunting a product, but translating or transcribing, no tools are needed, as this is a conversational query. the LLM should be able to handle this on its own.
### FURTHER NOTE: If the query has variables or other data that you need to fill in, you should use the appropriate tools to obtain the data, then, perform the task. You should be chaining tools together as needed.
### If the user seems to be saying that you are not correctly handling a task, or that you are  providing the wrong information, you should unlock more tools, for example google search if the info is incorrect, or browse website if the info is not available. Take note of the user's feedback and sentiment during the conversation.
### In the event that the user's query requires an integration which is this list, but the list of the user's integrations do not include the required provider, it means that the user has not integrated that service yet. In such cases, you must use the integration management tool to help the user integrate that service, before you can perform the task.
### Take into account the previous tool calls and their results. The plan must only indicate what needs to be done moving forward, not what has already been done. if a tool has already been called and results obtained, you may add it in the steps as "done", but do not include it in the list of tools to be used.
### consider if prior messages by the user indicated that we needed a tool, and whether that tool was already used, with results obtained. Do not include tools that have already been used and obtained results for. Conversely, if the user's query had indicated the need for a tool, but we had to ask questions, and they have now provided the needed info, you should now include the tool again.
### indicate explicitly if a step is done or needs to be done. steps are necessary when multiple tools are present.
"""




