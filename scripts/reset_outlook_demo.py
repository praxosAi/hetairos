import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to the Python path if necessary
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from src.utils.database import db_manager

# --- CONFIGURATION ---
# Change these variables depending on the demo setup
USER_ID = os.getenv("DEMO_USER_ID")  # MongoDB User ID used for the demo
TARGET_SENDER = "demo@example.com"   # Provide a specific sender to match for reset
TARGET_SUBJECT = ""                  # Provide a partial subject match (optional)
# ---------------------

async def run_reset():
    if not USER_ID:
        print("Error: DEMO_USER_ID environment variable is not set. Please set the user ID.")
        return

    # Initialize the integration and authenticate
    outlook = MicrosoftGraphIntegration(USER_ID)
    auth_success = await outlook.authenticate()
    if not auth_success:
        print(f"Error: Failed to authenticate Outlook integration for user {USER_ID}.")
        return

    print(f"Successfully authenticated Outlook for user {USER_ID}")

    # Fetch recent emails from the specific sender to narrow down
    print(f"Fetching recent emails from '{TARGET_SENDER}'...")
    try:
        messages = await outlook.get_emails_from_sender(TARGET_SENDER, max_results=50)
    except Exception as e:
        print(f"Failed to fetch emails: {e}")
        return

    # Filter messages based on our target conditions
    matched_messages = []
    for msg in messages:
        subject = msg.get("subject", "")
        if TARGET_SUBJECT and TARGET_SUBJECT.lower() not in subject.lower():
            continue
        matched_messages.append(msg)

    print(f"Found {len(matched_messages)} matching emails to reset.")

    # Apply reverse actions to each matched message
    for msg in matched_messages:
        msg_id = msg.get("id")
        subject = msg.get("subject", "No Subject")
        print(f"\nProcessing: '{subject}' (ID: {msg_id})")

        # 1. Mark as unread
        try:
            await outlook.mark_email_read(msg_id, is_read=False)
            print("  - Marked as UNREAD")
        except Exception as e:
            print(f"  - Failed to mark as unread: {e}")

        # 2. Clear categories
        try:
            await outlook.categorize_email(msg_id, categories=[])
            print("  - Categories CLEARED")
        except Exception as e:
            print(f"  - Failed to clear categories: {e}")

        # 3. Move back to Inbox (the folder ID for standard Inbox is typically 'inbox')
        try:
            await outlook.move_email(msg_id, destination_folder_id='inbox')
            print("  - Moved to INBOX")
        except Exception as e:
            print(f"  - Failed to move to inbox: {e}")

    print("\nDemo reset complete!")

if __name__ == "__main__":
    asyncio.run(run_reset())
