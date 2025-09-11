import asyncio
import logging
from typing import Dict, Optional
from src.core.praxos_client import PraxosClient
from src.integrations.calendar.google_calendar import GoogleCalendarIntegration
from src.integrations.email.gmail_client import GmailIntegration
from src.integrations.microsoft.graph_client import GraphClient as OutlookIntegration
from src.integrations.email.gmail_pubsub import gmail_pubsub_manager
from src.integrations.email.gmail_webhook import gmail_webhook_handler
from src.services.user_service import user_service
from src.config.settings import settings

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)

class SyncManager:
    def __init__(self):
        self.integration_classes = {
            "calendar": GoogleCalendarIntegration,
            "email": GmailIntegration,
            "gmail": GmailIntegration,  # Alias for convenience
            "outlook": OutlookIntegration,
            # TODO: Add more integrations as they're implemented
        }
        
        # Track active webhook subscriptions (for testing with single user)
        self.active_subscriptions = {}
        self.test_user_id = settings.GMAIL_TEST_USER
    
    async def sync_integration(self, user_id: str, integration_type: str):
        """Sync a specific integration for a user"""
        if integration_type not in self.integration_classes:
            print(f"Integration type {integration_type} not yet implemented")
            return 0
        
        try:
            # Initialize integration
            integration_class = self.integration_classes[integration_type]
            integration = integration_class(user_id)
            user_record = user_service.get_user_by_id(user_id)
            praxos_client = PraxosClient(f"env_for_{user_record['email']}", api_key=user_record.get("praxos_api_key"))
            # Perform sync
            ###TODO:Currently broken.
            return 0
            synced_count = await integration.full_sync(praxos_client)
            
            print(f"Synced {synced_count} items from {integration_type} for user {user_id}")
            return synced_count
            
        except Exception as e:
            print(f"Error syncing {integration_type} for user {user_id}: {e}")
            raise
    
    async def sync_all_user_integrations(self, user_id: str):
        """Sync all integrations for a user"""
        # TODO: Get user's enabled integrations from Praxos or database
        # For now, sync all available integrations
        
        tasks = []
        for integration_type in self.integration_classes.keys():
            task = self.sync_integration(user_id, integration_type)
            tasks.append(task)
        
        if not tasks:
            return [], []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_syncs = []
        failed_syncs = []
        
        for i, result in enumerate(results):
            integration_type = list(self.integration_classes.keys())[i]
            if isinstance(result, Exception):
                failed_syncs.append((integration_type, str(result)))
            else:
                successful_syncs.append((integration_type, result))
        
        return successful_syncs, failed_syncs
    
    # Gmail Webhook Methods (for testing with lurbisaia@gmail.com)
    
    async def setup_push_notifications(self) -> bool:
        """
        Setup push notifications for test user (lurbisaia@gmail.com).
        This includes both Pub/Sub infrastructure and Gmail watch setup.
        """
        try:
            logger.info(f"🔄 Setting up Gmail push notifications for {self.test_user_id}")
            
            # 1. Setup Pub/Sub infrastructure
            webhook_url = f"{settings.BASE_URL}/webhooks/gmail"
            
            # Ensure topic exists
            if not await gmail_pubsub_manager.ensure_topic_exists():
                logger.error("Failed to ensure Pub/Sub topic exists")
                return False
            
            # Ensure subscription exists with webhook endpoint
            if not await gmail_pubsub_manager.ensure_subscription_exists(webhook_url):
                logger.error("Failed to ensure Pub/Sub subscription exists")
                return False
            
            # 2. Setup Gmail watch for test user
            return await self._setup_gmail_webhook()
            
        except Exception as e:
            logger.error(f"Failed to setup push notifications: {e}")
            return False
    
    async def _setup_gmail_webhook(self) -> bool:
        """
        Setup Gmail push notifications for lurbisaia@gmail.com.
        Similar to existing calendar webhook pattern but for Gmail.
        """
        try:
            # Initialize Gmail client for test user
            gmail_client = GmailIntegration(self.test_user_id)
            
            # Authenticate
            if not await gmail_client.authenticate():
                logger.error(f"Gmail authentication failed for {self.test_user_id}")
                return False
            
            # Setup push notifications
            webhook_url = f"{settings.BASE_URL}/webhooks/gmail"
            subscription_info = await gmail_client.setup_push_notifications(webhook_url)
            
            if subscription_info:
                # Store subscription info
                self.active_subscriptions['gmail'] = {
                    'user_id': self.test_user_id,
                    'history_id': subscription_info['history_id'],
                    'expiration': subscription_info['expiration'],
                    'topic_name': subscription_info['topic_name'],
                    'webhook_url': webhook_url
                }
                
                logger.info(f"✅ Gmail webhook setup successful for {self.test_user_id}")
                logger.info(f"   History ID: {subscription_info['history_id']}")
                logger.info(f"   Expiration: {subscription_info['expiration']}")
                return True
            else:
                logger.error("Failed to setup Gmail push notifications")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up Gmail webhook: {e}")
            return False
    
    async def handle_gmail_notification(self, history_id: str, metadata: Dict = None) -> int:
        """
        Handle Gmail push notification for test user with history-based sync.
        This is called by the webhook handler after processing the notification.
        
        Args:
            history_id: Gmail history ID from webhook notification
            metadata: Additional metadata from the webhook
            
        Returns:
            Number of emails processed
        """
        try:
            logger.info(f"📧 Handling Gmail notification for {self.test_user_id}, historyId: {history_id}")
            
            # Use the webhook handler to process the notification
            # This creates a mock request structure for testing
            mock_request = {
                "message": {
                    "messageId": f"webhook-{history_id}",
                    "publishTime": metadata.get('publish_time') if metadata else None,
                    "data": gmail_pubsub_manager._encode_gmail_data(history_id, self.test_user_id),
                    "attributes": {}
                }
            }
            
            mock_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.GMAIL_WEBHOOK_TOKEN}"
            }
            
            # Process through webhook handler
            result = await gmail_webhook_handler.handle_gmail_notification(mock_request, mock_headers)
            
            if result['status'] == 'success':
                emails_processed = result.get('emails_processed', 0)
                logger.info(f"✅ Gmail notification processed: {emails_processed} emails")
                return emails_processed
            else:
                logger.error(f"Gmail notification processing failed: {result['message']}")
                return 0
                
        except Exception as e:
            logger.error(f"Error handling Gmail notification: {e}")
            return 0
    
    async def stop_push_notifications(self) -> bool:
        """
        Stop Gmail push notifications for test user.
        """
        try:
            logger.info(f"🛑 Stopping Gmail push notifications for {self.test_user_id}")
            
            # Initialize Gmail client
            gmail_client = GmailIntegration(self.test_user_id)
            
            # Authenticate
            if not await gmail_client.authenticate():
                logger.warning(f"Gmail authentication failed for {self.test_user_id} during stop")
                return False
            
            # Stop push notifications
            success = await gmail_client.stop_push_notifications()
            
            if success:
                # Clear stored subscription info
                if 'gmail' in self.active_subscriptions:
                    del self.active_subscriptions['gmail']
                
                logger.info(f"✅ Gmail push notifications stopped for {self.test_user_id}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error stopping Gmail push notifications: {e}")
            return False
    
    async def get_webhook_status(self) -> Dict:
        """
        Get current webhook subscription status.
        """
        return {
            'test_user': self.test_user_id,
            'active_subscriptions': self.active_subscriptions,
            'webhook_url': f"{settings.BASE_URL}/webhooks/gmail",
            'pubsub_topic': settings.GMAIL_PUBSUB_TOPIC,
            'project_id': settings.GOOGLE_CLOUD_PROJECT_ID
        }