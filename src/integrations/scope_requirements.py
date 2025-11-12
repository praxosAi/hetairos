"""
OAuth Scope Requirements

Defines the minimum required OAuth scopes for each operation across all integrations.
Used for scope validation before API calls.
"""

# Gmail API Scope Requirements
GMAIL_SCOPE_REQUIREMENTS = {
    # Read operations - require gmail.readonly OR gmail.modify
    'search_emails': ['https://www.googleapis.com/auth/gmail.readonly'],
    'get_message': ['https://www.googleapis.com/auth/gmail.readonly'],
    'get_emails_from_sender': ['https://www.googleapis.com/auth/gmail.readonly'],
    'get_message_by_id': ['https://www.googleapis.com/auth/gmail.readonly'],
    'list_labels': ['https://www.googleapis.com/auth/gmail.readonly'],
    'fetch_recent_data': ['https://www.googleapis.com/auth/gmail.readonly'],

    # Modify operations - require gmail.modify
    'modify_message_labels': ['https://www.googleapis.com/auth/gmail.modify'],
    'archive_message': ['https://www.googleapis.com/auth/gmail.modify'],
    'mark_as_unread': ['https://www.googleapis.com/auth/gmail.modify'],
    'add_star': ['https://www.googleapis.com/auth/gmail.modify'],
    'remove_star': ['https://www.googleapis.com/auth/gmail.modify'],
    'move_to_spam': ['https://www.googleapis.com/auth/gmail.modify'],
    'move_to_trash': ['https://www.googleapis.com/auth/gmail.modify'],
    'create_draft': ['https://www.googleapis.com/auth/gmail.modify'],
    'add_label_to_message': ['https://www.googleapis.com/auth/gmail.modify'],
    'remove_label_from_message': ['https://www.googleapis.com/auth/gmail.modify'],

    # Send operations - require gmail.send OR gmail.modify
    'send_email': ['https://www.googleapis.com/auth/gmail.send'],
    'reply_to_message': ['https://www.googleapis.com/auth/gmail.send'],

    # Contacts - require contacts.readonly
    'find_contact_email': ['https://www.googleapis.com/auth/contacts.readonly'],

    # Webhook setup
    'setup_push_notifications': ['https://www.googleapis.com/auth/gmail.readonly'],
    'stop_push_notifications': ['https://www.googleapis.com/auth/gmail.readonly'],
}

# Google Drive Scope Requirements
GDRIVE_SCOPE_REQUIREMENTS = {
    'list_files': ['https://www.googleapis.com/auth/drive.readonly'],
    'download_file': ['https://www.googleapis.com/auth/drive.readonly'],
    'read_file_content_by_id': ['https://www.googleapis.com/auth/drive.readonly'],
    'get_changed_files_since': ['https://www.googleapis.com/auth/drive.readonly'],
    'fetch_recent_data': ['https://www.googleapis.com/auth/drive.readonly'],

    'create_text_file': ['https://www.googleapis.com/auth/drive.file'],
    'save_file_to_drive': ['https://www.googleapis.com/auth/drive.file'],
}

# Google Calendar Scope Requirements
CALENDAR_SCOPE_REQUIREMENTS = {
    'get_events': ['https://www.googleapis.com/auth/calendar.readonly'],
    'list_calendars': ['https://www.googleapis.com/auth/calendar.readonly'],

    'create_event': ['https://www.googleapis.com/auth/calendar.events'],
    'update_event': ['https://www.googleapis.com/auth/calendar.events'],
    'delete_event': ['https://www.googleapis.com/auth/calendar.events'],
}

# Google Sheets Scope Requirements
SHEETS_SCOPE_REQUIREMENTS = {
    'read_sheet': ['https://www.googleapis.com/auth/spreadsheets.readonly'],
    'get_sheet_values': ['https://www.googleapis.com/auth/spreadsheets.readonly'],

    'update_sheet': ['https://www.googleapis.com/auth/spreadsheets'],
    'append_to_sheet': ['https://www.googleapis.com/auth/spreadsheets'],
    'create_sheet': ['https://www.googleapis.com/auth/spreadsheets'],
}

# Google Docs Scope Requirements
DOCS_SCOPE_REQUIREMENTS = {
    'read_document': ['https://www.googleapis.com/auth/documents.readonly'],
    'get_document': ['https://www.googleapis.com/auth/documents.readonly'],

    'update_document': ['https://www.googleapis.com/auth/documents'],
    'create_document': ['https://www.googleapis.com/auth/documents'],
}

# Google Slides Scope Requirements
SLIDES_SCOPE_REQUIREMENTS = {
    'read_presentation': ['https://www.googleapis.com/auth/presentations.readonly'],
    'get_presentation': ['https://www.googleapis.com/auth/presentations.readonly'],

    'update_presentation': ['https://www.googleapis.com/auth/presentations'],
    'create_presentation': ['https://www.googleapis.com/auth/presentations'],
}

# Microsoft Graph Scope Requirements
MICROSOFT_SCOPE_REQUIREMENTS = {
    'get_user': ['User.Read'],
    'read_mail': ['Mail.Read'],
    'send_mail': ['Mail.Send'],
    'read_calendar': ['Calendars.Read'],
    'write_calendar': ['Calendars.ReadWrite'],
}

# Combined lookup by integration name
SCOPE_REQUIREMENTS = {
    'gmail': GMAIL_SCOPE_REQUIREMENTS,
    'google_drive': GDRIVE_SCOPE_REQUIREMENTS,
    'google_calendar': CALENDAR_SCOPE_REQUIREMENTS,
    'google_sheets': SHEETS_SCOPE_REQUIREMENTS,
    'google_docs': DOCS_SCOPE_REQUIREMENTS,
    'google_slides': SLIDES_SCOPE_REQUIREMENTS,
    'microsoft': MICROSOFT_SCOPE_REQUIREMENTS,
}
