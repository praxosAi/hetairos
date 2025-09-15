"""
Gmail webhook handler for processing push notifications.
Handles incoming Gmail Pub/Sub messages and triggers email sync.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Any
from src.config.settings import settings
from src.utils.rate_limiter import rate_limiter
from src.integrations.email.gmail_pubsub import gmail_pubsub_manager
from src.integrations.email.gmail_client import GmailIntegration
from src.core.praxos_client import PraxosClient
from src.utils.logging.webhook_logger import (
    log_gmail_webhook_received, log_gmail_webhook_processed, log_gmail_webhook_failed,
    log_gmail_webhook_skipped, log_gmail_authentication_failure, log_gmail_rate_limit_hit,
    log_gmail_history_fetch
)

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)

class GmailWebhookHandler:
    """Handles Gmail push notification webhooks for lurbisaia@gmail.com"""
    
    def __init__(self):
        self.test_user = settings.GMAIL_TEST_USER
        self.webhook_token = settings.GMAIL_WEBHOOK_TOKEN
        # Track last processed history ID to avoid duplicates
        self.last_history_id = None
    
    async def handle_gmail_notification(self, request_body: Dict, headers: Dict) -> Dict:
        """
        Process Gmail push notification for lurbisaia@gmail.com.
        
        Args:
            request_body: Pub/Sub message containing historyId
            headers: HTTP headers for validation
        
        Returns:
            Processing result dictionary
        """
        start_time = time.time()
        
        try:
            # 1. Validate the request
            if not self.validate_notification(request_body, headers):
                return {
                    "status": "error",
                    "message": "Invalid notification",
                    "processing_time": time.time() - start_time
                }
            
            # 2. Parse the Pub/Sub message
            parsed_message = gmail_pubsub_manager.parse_pubsub_message(request_body)
            if not parsed_message:
                return {
                    "status": "error",
                    "message": "Failed to parse Pub/Sub message",
                    "processing_time": time.time() - start_time
                }
            
            # 3. Validate it's a Gmail notification
            if not gmail_pubsub_manager.validate_pubsub_message(parsed_message):
                return {
                    "status": "error",
                    "message": "Invalid Gmail notification",
                    "processing_time": time.time() - start_time
                }
            
            # 4. Extract Gmail notification data
            gmail_data = gmail_pubsub_manager.extract_gmail_notification_data(parsed_message)
            if not gmail_data:
                return {
                    "status": "error",
                    "message": "Failed to extract Gmail data",
                    "processing_time": time.time() - start_time
                }
            
            history_id = gmail_data['history_id']
            message_id = gmail_data.get('message_id')
            publish_time = gmail_data.get('publish_time')
            
            # Enhanced logging
            log_gmail_webhook_received(history_id, message_id, publish_time)
            
            # 5. Check for duplicate notifications
            if self.last_history_id and history_id <= self.last_history_id:
                log_gmail_webhook_skipped(history_id, f"Duplicate (current: {self.last_history_id})")
                return {
                    "status": "skipped",
                    "message": "Duplicate notification",
                    "history_id": history_id,
                    "processing_time": time.time() - start_time
                }
            
            # 6. Process the history changes
            processed_count = await self.process_history_changes(history_id)
            
            # 7. Update last processed history ID
            self.last_history_id = history_id
            
            processing_time = time.time() - start_time
            
            # Enhanced logging
            log_gmail_webhook_processed(history_id, processed_count, processing_time)
            
            return {
                "status": "success",
                "message": f"Processed {processed_count} email changes",
                "history_id": history_id,
                "emails_processed": processed_count,
                "processing_time": processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Enhanced error logging
            history_id = "unknown"
            try:
                # Try to extract history_id for logging
                parsed_message = gmail_pubsub_manager.parse_pubsub_message(request_body)
                if parsed_message:
                    gmail_data = gmail_pubsub_manager.extract_gmail_notification_data(parsed_message)
                    if gmail_data:
                        history_id = gmail_data.get('history_id', 'unknown')
            except:
                pass
            
            log_gmail_webhook_failed(history_id, str(e), processing_time)
            
            return {
                "status": "error", 
                "message": str(e),
                "processing_time": processing_time
            }
    
    def validate_notification(self, message: Dict, headers: Dict) -> bool:
        """
        Validate incoming notification authenticity.
        
        Args:
            message: Pub/Sub message
            headers: HTTP headers
            
        Returns:
            True if notification is valid
        """
        try:
            # Basic validation - check if it's a Pub/Sub message
            if 'message' not in message:
                logger.warning("Invalid notification: missing 'message' field")
                return False
            
            # TODO: Add more sophisticated validation
            # - Verify Pub/Sub message signature
            # - Check webhook token if provided
            # - Validate message timestamp
            
            # For now, basic validation
            if self.webhook_token:
                # Check for webhook token in headers or message
                auth_header = headers.get('Authorization', '')
                if not auth_header or self.webhook_token not in auth_header:
                    logger.warning("Invalid notification: webhook token mismatch")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating notification: {e}")
            return False
    
    async def process_history_changes(self, history_id: str) -> int:
        """
        Process email changes since historyId for the test user by routing them
        to the AssistantController.
        """
        from src.core.assistant_controller import AssistantController

        try:
            # Rate limit check
            allowed, _ = rate_limiter.check_limit(self.test_user, "gmail_webhooks")
            if not allowed:
                log_gmail_rate_limit_hit("gmail_webhooks", self.test_user, 0)
                return 0

            gmail_client = GmailIntegration(self.test_user)
            if not await gmail_client.authenticate():
                log_gmail_authentication_failure(self.test_user)
                return 0

            # Get message IDs from history changes
            history_changes = await self.get_history_since(gmail_client, history_id)
            if not history_changes:
                logger.info("No new email changes to process.")
                return 0

            new_message_ids = []
            for item in history_changes:
                for msg_added in item.get('messagesAdded', []):
                    new_message_ids.append(msg_added['message']['id'])

            if not new_message_ids:
                logger.info("History changes did not contain any new messages.")
                return 0

            # Initialize the controller to process messages
            assistant_controller = AssistantController()
            logger.info(f"Processing message, controller initialized")
            for message_id in new_message_ids:
                try:
                    # Get the full, formatted email details
                    email_details = await gmail_client.get_formatted_email(message_id)
                    if not email_details:
                        continue

                    # The assistant expects a dictionary of content
                    message_content = {
                        "subject": email_details.get("subject"),
                        "snippet": email_details.get("snippet"),
                        "from": email_details.get("sender"),
                        "body": email_details.get("body")
                    }

                    # Route the email to the assistant controller
                    await assistant_controller.process_message(
                        user_record=self.test_user,
                        message_content=message_content,
                        source="gmail",
                        message_id=message_id
                    )
                except Exception as e:
                    logger.error(f"Failed to process email message {message_id}: {e}")

            rate_limiter.increment_usage(self.test_user, "gmail_webhooks", 1)
            return len(new_message_ids)

        except Exception as e:
            logger.error(f"Error processing history changes: {e}")
            return 0
    
    async def get_history_since(self, gmail_client: GmailIntegration, history_id: str) -> list:
        """
        Get Gmail history changes since the given historyId.
        
        Args:
            gmail_client: Authenticated Gmail client
            history_id: Starting history ID
            
        Returns:
            List of history changes
        """
        try:
            # Check rate limits for history API calls
            allowed, remaining = rate_limiter.check_limit(self.test_user, "gmail_history_calls")
            if not allowed:
                log_gmail_rate_limit_hit("gmail_history_calls", self.test_user, remaining)
                return []
            
            # Use Gmail API to get history
            history_result = gmail_client.service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                historyTypes=['messageAdded'],  # Only interested in new messages
                maxResults=100  # Limit for webhook processing
            ).execute()
            
            history_items = history_result.get('history', [])
            
            # Update rate limiter
            rate_limiter.increment_usage(self.test_user, "gmail_history_calls", 1)
            
            # Enhanced logging
            fetch_time = time.time() - time.time()  # This would be calculated properly in real implementation
            log_gmail_history_fetch(history_id, len(history_items), 0.1)  # Mock fetch time for now
            
            return history_items
            
        except Exception as e:
            logger.error(f"Error getting Gmail history: {e}")
            return []
    
    async def convert_history_to_emails(self, gmail_client: GmailIntegration, history_changes: list) -> list:
        """
        Convert Gmail history changes to email format for sync.
        
        Args:
            gmail_client: Authenticated Gmail client
            history_changes: List of history change items
            
        Returns:
            List of formatted email messages
        """
        emails = []
        
        try:
            for history_item in history_changes:
                # Process messages added
                messages_added = history_item.get('messagesAdded', [])
                
                for message_added in messages_added:
                    message_id = message_added['message']['id']
                    
                    try:
                        # Get full message details
                        msg_detail = gmail_client.service.users().messages().get(
                            userId='me',
                            id=message_id,
                            format='full'
                        ).execute()
                        
                        # Format using existing method
                        formatted_message = await gmail_client._format_message(msg_detail)
                        emails.append(formatted_message)
                        
                    except Exception as e:
                        logger.error(f"Error processing message {message_id}: {e}")
                        continue
            
            logger.info(f"Converted {len(emails)} history changes to email format")
            return emails
            
        except Exception as e:
            logger.error(f"Error converting history to emails: {e}")
            return []

# Global webhook handler instance
gmail_webhook_handler = GmailWebhookHandler()