"""
Google Cloud Pub/Sub integration for Gmail webhooks.
Handles Pub/Sub topic management and message processing for Gmail notifications.
"""

import asyncio
import base64
import json
import logging
from typing import Dict, Optional, Any
from google.cloud import pubsub_v1
from google.api_core import exceptions as gcp_exceptions
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)

class GmailPubSubManager:
    """Manages Google Cloud Pub/Sub integration for Gmail webhooks"""
    
    def __init__(self):
        self.project_id = settings.GOOGLE_CLOUD_PROJECT_ID
        self.topic_name = settings.GMAIL_PUBSUB_TOPIC
        self.subscription_name = settings.GMAIL_PUBSUB_SUBSCRIPTION
        
        # Lazy initialization - only create clients when needed
        self._publisher = None
        self._subscriber = None
        self._topic_path = None
        self._subscription_path = None
    
    @property
    def publisher(self):
        """Lazy-initialize publisher client"""
        if self._publisher is None:
            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher
    
    @property
    def subscriber(self):
        """Lazy-initialize subscriber client"""
        if self._subscriber is None:
            self._subscriber = pubsub_v1.SubscriberClient()
        return self._subscriber
    
    @property
    def topic_path(self):
        """Get topic path"""
        if self._topic_path is None:
            self._topic_path = self.publisher.topic_path(self.project_id, self.topic_name)
        return self._topic_path
    
    @property
    def subscription_path(self):
        """Get subscription path"""
        if self._subscription_path is None:
            self._subscription_path = self.subscriber.subscription_path(
                self.project_id, self.subscription_name
            )
        return self._subscription_path
    
    async def ensure_topic_exists(self) -> bool:
        """
        Ensure Gmail notification topic exists, create if necessary.
        Returns True if topic exists or was created successfully.
        """
        try:
            # Try to get the topic
            self.publisher.get_topic(request={"topic": self.topic_path})
            logger.info(f"Gmail Pub/Sub topic already exists: {self.topic_path}")
            return True
            
        except gcp_exceptions.NotFound:
            # Topic doesn't exist, create it
            try:
                topic = self.publisher.create_topic(request={"name": self.topic_path})
                logger.info(f"Created Gmail Pub/Sub topic: {topic.name}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to create Gmail Pub/Sub topic: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking Gmail Pub/Sub topic: {e}")
            return False
    
    async def ensure_subscription_exists(self, push_endpoint: str) -> bool:
        """
        Ensure push subscription exists for webhook endpoint.
        
        Args:
            push_endpoint: HTTPS URL for webhook delivery
            
        Returns:
            True if subscription exists or was created successfully
        """
        try:
            # Try to get the subscription
            self.subscriber.get_subscription(request={"subscription": self.subscription_path})
            logger.info(f"Gmail Pub/Sub subscription already exists: {self.subscription_path}")
            return True
            
        except gcp_exceptions.NotFound:
            try:
                push_config = pubsub_v1.PushConfig(push_endpoint=push_endpoint)
                
                subscription = self.subscriber.create_subscription(
                    request={
                        "name": self.subscription_path,
                        "topic": self.topic_path,
                        "push_config": push_config,
                    }
                )
                logger.info(f"Created Gmail Pub/Sub subscription: {subscription.name}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to create Gmail Pub/Sub subscription: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking Gmail Pub/Sub subscription: {e}")
            return False
    
    def parse_pubsub_message(self, request_data: Dict) -> Optional[Dict]:
        """
        Parse incoming Pub/Sub push message.
        
        Args:
            request_data: Raw request data from webhook
            
        Returns:
            Parsed message data or None if parsing fails
        """
        try:
            # Check if it has the basic Pub/Sub structure
            if 'message' not in request_data:
                logger.warning("Invalid Pub/Sub message: missing 'message' field")
                return None
            
            # Extract Pub/Sub message
            message = request_data.get('message', {})
            
            # Check required fields
            if 'messageId' not in message:
                logger.warning("Invalid Pub/Sub message: missing 'messageId'")
                return None
            
            # Decode message data
            data = message.get('data', '')
            if data:
                try:
                    decoded_data = base64.b64decode(data).decode('utf-8')
                    message_data = json.loads(decoded_data)
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"Invalid Pub/Sub message data: {e}")
                    return None
            else:
                message_data = {}
            
            # Extract attributes
            attributes = message.get('attributes', {})
            
            return {
                'message_id': message.get('messageId'),
                'publish_time': message.get('publishTime'),
                'data': message_data,
                'attributes': attributes
            }
            
        except Exception as e:
            logger.error(f"Failed to parse Pub/Sub message: {e}")
            return None
    
    def validate_pubsub_message(self, parsed_message: Dict) -> bool:
        """
        Validate that the Pub/Sub message is from Gmail.
        
        Args:
            parsed_message: Parsed Pub/Sub message
            
        Returns:
            True if message is valid Gmail notification
        """
        try:
            # Check for required Gmail notification fields
            data = parsed_message.get('data', {})
            
            # Gmail notifications should have historyId
            if 'historyId' not in data:
                logger.warning("Pub/Sub message missing historyId - not a Gmail notification")
                return False
            # Check if message is for our test user (in production, this would be dynamic)
            email_address = data.get('emailAddress')
            if not email_address:
                logger.warning(f"email address is not present in the message")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating Pub/Sub message: {e}")
            return False
    
    def extract_gmail_notification_data(self, parsed_message: Dict) -> Optional[Dict]:
        """
        Extract Gmail-specific data from validated Pub/Sub message.
        
        Args:
            parsed_message: Validated Pub/Sub message
            
        Returns:
            Gmail notification data or None if extraction fails
        """
        try:
            data = parsed_message.get('data', {})
            
            return {
                'history_id': data.get('historyId'),
                'email_address': data.get('emailAddress', settings.GMAIL_TEST_USER),
                'message_id': parsed_message.get('message_id'),
                'publish_time': parsed_message.get('publish_time')
            }
            
        except Exception as e:
            logger.error(f"Error extracting Gmail notification data: {e}")
            return None
    
    async def cleanup_resources(self) -> bool:
        """
        Clean up Pub/Sub resources (for testing/development).
        WARNING: This will delete the topic and subscription.
        """
        try:
            # Delete subscription first
            try:
                self.subscriber.delete_subscription(request={"subscription": self.subscription_path})
                logger.info(f"Deleted Pub/Sub subscription: {self.subscription_path}")
            except gcp_exceptions.NotFound:
                logger.info("Pub/Sub subscription already deleted")
            
            # Delete topic
            try:
                self.publisher.delete_topic(request={"topic": self.topic_path})
                logger.info(f"Deleted Pub/Sub topic: {self.topic_path}")
            except gcp_exceptions.NotFound:
                logger.info("Pub/Sub topic already deleted")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up Pub/Sub resources: {e}")
            return False
    
    def _encode_gmail_data(self, history_id: str, email_address: str) -> str:
        """
        Helper method to encode Gmail data for testing.
        
        Args:
            history_id: Gmail history ID
            email_address: Email address
            
        Returns:
            Base64-encoded JSON string
        """
        import base64
        import json
        
        gmail_data = {
            "historyId": history_id,
            "emailAddress": email_address
        }
        
        return base64.b64encode(json.dumps(gmail_data).encode()).decode()

# Global instance for use across the application
gmail_pubsub_manager = GmailPubSubManager()