import logging
from typing import Optional, Dict
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from src.config.settings import settings
from bson import ObjectId
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
from datetime import timezone, timedelta,datetime
import pytz
from src.config.tier_limits import TierLimits, SubscriptionTier
class UserService:
    def __init__(self):
        self._client = None
        self._db = None
    
    def _get_database(self):
        """Get MongoDB database connection"""
        if self._db is None:
            try:
                self._client = MongoClient(settings.MONGO_CONNECTION_STRING)
                self._db = self._client[settings.MONGO_DB_NAME]
                # Test connection
                self._client.admin.command('ping')
                logger.info(f"Connected to MongoDB: {settings.MONGO_DB_NAME}")
            except PyMongoError as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise
        return self._db
    
    def is_authorized_user(self, phone_number: str) -> dict:
        """Check if a phone number belongs to an authorized user"""
        try:
            db = self._get_database()
            users_collection = db.users
            
            # Query for user with matching phone_number
            user = users_collection.find_one({"phone_number": phone_number})
            
            is_authorized = user is not None
            if is_authorized:
                logger.info(f"Phone number {phone_number} is authorized")
                return user
            else:
                logger.info(f"Phone number {phone_number} is not authorized")
                return None
            
        except PyMongoError as e:
            logger.error(f"MongoDB error checking authorization for {phone_number}: {e}")
            # Fallback to original behavior on database error
            return phone_number == settings.TEST_PHONE_NUMBER
        except Exception as e:
            logger.error(f"Unexpected error checking authorization for {phone_number}: {e}")
            # Fallback to original behavior on error
            return phone_number == settings.TEST_PHONE_NUMBER
    
    def get_user_by_phone(self, phone_number: str) -> Optional[Dict]:
        """Get user data by phone number"""
        try:
            db = self._get_database()
            users_collection = db.users
            
            user = users_collection.find_one({"phone_number": phone_number})
            
            if user:
                # Convert MongoDB ObjectId to string for JSON serialization
                user["_id"] = str(user["_id"])
                logger.info(f"Retrieved user data for phone number {phone_number}")
            else:
                logger.info(f"No user found for phone number {phone_number}")
            
            return user
            
        except PyMongoError as e:
            logger.error(f"MongoDB error retrieving user for {phone_number}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving user for {phone_number}: {e}")
            return None
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user data by email"""
        try:
            db = self._get_database()
            users_collection = db.users
            user = users_collection.find_one({"email": email})
            return user
        except Exception as e:
            logger.error(f"Unexpected error retrieving user for {email}: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user data by user id"""
        try:
            db = self._get_database()
            users_collection = db.users
            user = users_collection.find_one({"_id": ObjectId(user_id)})
            return user
        except Exception as e:
            logger.error(f"Unexpected error retrieving user for {user_id}: {e}")
            return None

    def get_user_by_ms_id(self, ms_user_id: str) -> Optional[Dict]:
        """Get user data by Microsoft Graph user ID"""
        try:
            db = self._get_database()
            users_collection = db.users
            # Assuming the MS Graph user ID is stored in a field called 'ms_graph_user_id'
            user = users_collection.find_one({"ms_graph_user_id": ms_user_id})
            return user
        except Exception as e:
            logger.error(f"Unexpected error retrieving user for MS Graph ID {ms_user_id}: {e}")
            return None
    def close_connection(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")

    def get_user_preferences(self, user_id:str|ObjectId):
        db = self._get_database()
        preferences_collection = db.user_preferences
        preference = preferences_collection.find_one({"user_id": ObjectId(user_id)})
        return preference

    def get_user_tier(self, user: dict) -> str:
        """Get user's current tier with automatic detection"""
        # If tier is explicitly set, use it
        if user.get('tier') and user.get('tier') != SubscriptionTier.PERSONAL:
            return user.get('tier')

        # Auto-detect tier based on billing status
        if user.get('billing_setup_completed') and user.get('payment_status') in ['active', 'trialing']:
            return SubscriptionTier.PROFESSIONAL

        # Default to free tier
        return SubscriptionTier.PERSONAL

    def can_have_access(self, user:dict=None, user_id=None):
        """
        Check if user can access the application.
        Free tier users always have access.
        Pro/Enterprise users need active trial OR subscription.
        """
        if not user:
            if not user_id:
                logger.error("Either user or user_id should be passed in")
                return True
            user = self.get_user_by_id(user_id)
            if not user:
                logger.error(f"Can't find user from {user_id} id")
                return True

        # Get user's tier
        tier = self.get_user_tier(user)

        # Free tier users always have access
        if tier == SubscriptionTier.PERSONAL:
            logger.info(f"User {str(user.get('_id'))} has free tier access")
            return True

        # Pro/Enterprise users: Check trial OR billing
        if user.get('trial_end_date') and user.get('trial_end_date') > datetime.now():
            logger.info(f"User {str(user.get('_id'))} has trial access")
            return True

        if not user.get("billing_setup_completed") or (user.get('payment_status') in ['pending', 'incomplete', 'incomplete_expired']):
            logger.error(f"User {str(user.get('_id'))} doesn't have access, billing not setup or payment status is {user.get('payment_status')}")
            return False

        return True

    def is_feature_enabled(self, user: dict, feature_name: str) -> bool:
        """Check if a feature is enabled for user's tier"""
        tier = self.get_user_tier(user)
        return TierLimits.is_feature_enabled(tier, feature_name)

    def get_tier_limits(self, user: dict) -> Dict:
        """Get the limits for user's current tier"""
        tier = self.get_user_tier(user)
        return TierLimits.get_limits(tier)

    def add_new_preference_annotations(self, user_id: str | ObjectId, preferences: dict, append: bool = False):
        """
        Update or upsert user preferences.

        Args:
            user_id: str or ObjectId of the user
            preferences: dict of fields to update (do NOT include 'user_id' or '_id')
            append: if True, values under 'annotations' are appended (de-duplicated via $addToSet)
        """
        db = self._get_database()
        preferences_collection = db.user_preferences

        # sanitize incoming prefs; never allow user_id/_id to be overwritten
        prefs = dict(preferences or {})
        prefs.pop("user_id", None)
        prefs.pop("_id", None)

        now = datetime.now(timezone.utc)

        update_doc = {
            "$set": {"updated_at": now},
            "$setOnInsert": {
                "user_id": ObjectId(user_id),
                "created_at": now,
            },
        }

        if append and "annotations" in prefs:
            annotations = prefs.pop("annotations")
            if not isinstance(annotations, list):
                raise ValueError("annotations must be a list when append=True")
            # Create $addToSet only for annotations; this will create the field if missing
            update_doc["$addToSet"] = {"annotations": {"$each": annotations}}

        # set any remaining scalar/top-level fields
        if prefs:
            update_doc["$set"].update(prefs)

        logger.info(f"Updating preferences for user {user_id}: {preferences} (append={append})")

        result = preferences_collection.update_one(
            {"user_id": ObjectId(user_id)},
            update_doc,
            upsert=True
        )

        return result.modified_count > 0 or result.upserted_id is not None


    def remove_preference_annotations(self, user_id: str | ObjectId, annotations: list[str]) -> bool:
        """
        Remove one or more strings from the 'annotations' array only.
        No other fields may be deleted via this method.

        Args:
            user_id: str or ObjectId of the user.
            annotations: list of exact strings to remove from 'annotations'.

        Returns:
            bool indicating if an update or upsert occurred.
        """
        if not annotations:
            return False

        db = self._get_database()
        preferences_collection = db.user_preferences

        now = datetime.now(timezone.utc)

        update_doc = {
            # Remove any occurrences of the provided values
            "$pullAll": {"annotations": annotations},
            # Always bump updated_at
            "$set": {"updated_at": now},
            # If the doc doesn't exist, create the shell with user_id/created_at
            "$setOnInsert": {
                "user_id": ObjectId(user_id),
                "created_at": now,
            },
        }

        result = preferences_collection.update_one(
            {"user_id": ObjectId(user_id)},
            update_doc,
            upsert=True,  # harmless if doc doesn't exist; no annotations will be created
        )

        return result.modified_count > 0 or result.upserted_id is not None

    def save_user_location(self, user_id: str | ObjectId, latitude: float, longitude: float, platform: str, location_name: str = None):
        """
        Save user's location to preferences. Stores both the most recent location and appends to location history.

        Args:
            user_id: User ID
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            platform: Platform where location was shared (telegram, whatsapp, imessage)
            location_name: Optional name/label for the location
        """
        db = self._get_database()
        preferences_collection = db.user_preferences

        now = datetime.now(timezone.utc)

        location_data = {
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": now,
            "platform": platform
        }

        if location_name:
            location_data["name"] = location_name

        # Update last known location and append to history
        update_doc = {
            "$set": {
                "location_preferences.last_shared_location": location_data,
                "updated_at": now
            },
            "$push": {
                "location_preferences.location_history": {
                    "$each": [location_data],
                    "$slice": -100  # Keep only last 100 locations
                }
            },
            "$setOnInsert": {
                "user_id": ObjectId(user_id),
                "created_at": now
            }
        }

        logger.info(f"Saving location for user {user_id}: lat={latitude}, lng={longitude}, platform={platform}")

        result = preferences_collection.update_one(
            {"user_id": ObjectId(user_id)},
            update_doc,
            upsert=True
        )

        return result.modified_count > 0 or result.upserted_id is not None

    def get_user_last_location(self, user_id: str | ObjectId):
        """
        Get user's last shared location.

        Args:
            user_id: User ID

        Returns:
            Dictionary with location data or None if not found
        """
        try:
            preferences = self.get_user_preferences(user_id)
            if preferences and "location_preferences" in preferences:
                return preferences["location_preferences"].get("last_shared_location")
            return None
        except Exception as e:
            logger.error(f"Error getting last location for user {user_id}: {e}")
            return None

    def get_user_location_history(self, user_id: str | ObjectId, limit: int = 10):
        """
        Get user's location history.

        Args:
            user_id: User ID
            limit: Maximum number of locations to return (default 10)

        Returns:
            List of location dictionaries, most recent first
        """
        try:
            preferences = self.get_user_preferences(user_id)
            if preferences and "location_preferences" in preferences:
                history = preferences["location_preferences"].get("location_history", [])
                # Return most recent first, limited to requested count
                return list(reversed(history[-limit:]))
            return []
        except Exception as e:
            logger.error(f"Error getting location history for user {user_id}: {e}")
            return []

    def set_first_time_interaction_to_false(self, user_id: str) -> bool:
        """
        Sets the 'needs_first_interaction' field to False for the specified user.

        Args:
            user_id: str or ObjectId of the user.
        """
        db = self._get_database()
        users_collection = db.users

        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"needs_first_interaction": False}}
        )

        return result.modified_count > 0

    async def get_user_id_from_api_key(self, api_key: str) -> Optional[str]:
        """
        Validate API key and return associated user_id.
        Checks both mcp_api_key and api_key fields.

        Args:
            api_key: The API key to validate

        Returns:
            user_id string if valid, None if invalid
        """
        try:
            db = self._get_database()
            users_collection = db.users

            # Look up user by API key - try both fields
            user = users_collection.find_one({
                "$or": [
                    {"mcp_api_key": api_key},
                    {"api_key": api_key}
                ]
            })

            if not user:
                logger.warning("No user found for provided API key")
                return None

            user_id = str(user.get('_id'))
            logger.info(f"Validated API key for user {user_id}")
            return user_id

        except Exception as e:
            logger.error(f"Error validating API key: {e}", exc_info=True)
            return None

    async def initialize_user_knowledge_graph(self, user_id: str, user_email: str = None, user_data: Dict = None):
        """
        Initialize knowledge graph for a new user with their profile entity.
        Should be called during user registration/onboarding.

        Args:
            user_id: User ID
            user_email: User's email address
            user_data: Optional additional user data (first_name, last_name, etc.)
        """
        try:
            from src.core.praxos_client import PraxosClient

            praxos_client = PraxosClient(
                environment_name=f"user_{user_id}",
                api_key=settings.PRAXOS_API_KEY
            )

            # Build user profile properties
            properties = [
                {"key": "user_id", "value": user_id, "type": "UniqueIdentifierType"},
                {"key": "created_at", "value": datetime.now(timezone.utc).isoformat(), "type": "DateTimeType"}
            ]

            if user_email:
                properties.append({"key": "email", "value": user_email, "type": "EmailType"})

            if user_data:
                if user_data.get('first_name'):
                    properties.append({"key": "first_name", "value": user_data['first_name'], "type": "FirstNameType"})
                if user_data.get('last_name'):
                    properties.append({"key": "last_name", "value": user_data['last_name'], "type": "LastNameType"})
                if user_data.get('phone_number'):
                    properties.append({"key": "phone", "value": user_data['phone_number'], "type": "PhoneNumberType"})

            # Create user profile entity in KG
            result = await praxos_client.create_entity_in_kg(
                entity_type="schema:Person",
                label=f"User Profile",
                properties=properties
            )

            logger.info(f"Successfully initialized KG for user {user_id}: {result.get('nodes_created', 0)} nodes created")
            return result

        except Exception as e:
            logger.error(f"Failed to initialize KG for user {user_id}: {e}", exc_info=True)
            return {"error": str(e)}

    async def register_telegram_user(
        self,
        telegram_chat_id: int,
        telegram_username: str,
        first_name: str,
        last_name: str,
        language: str = "en"
    ) -> dict:
        """
        Register new user via Telegram bot.

        Flow:
        1. Call mypraxos-backend registration endpoint
        2. Receive user_id
        3. Create integration record in hetairos
        4. Update milestones
        5. Return user data
        """
        import httpx
        from datetime import datetime
        from bson import ObjectId

        try:
            # Step 1: Call mypraxos-backend
            backend_url = settings.PRAXOS_BASE_URL
            endpoint = f"{backend_url}/api/auth/register/telegram"

            payload = {
                "telegram_chat_id": telegram_chat_id,
                "telegram_username": telegram_username,
                "first_name": first_name,
                "last_name": last_name,
                "language": language
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=payload, timeout=30)
                response.raise_for_status()
                backend_response = response.json()
                logger.info(f"Telegram registration response: {backend_response}")
            user_id = backend_response['data']["user_id"]

            # Step 2: Create integration record in hetairos
            from src.services.integration_service import integration_service

            integration_data = {
                "user_id": ObjectId(user_id),
                "name": "telegram",
                "type": "messaging",
                "provider": "telegram",
                "connected_account": telegram_username or f"telegram_{telegram_chat_id}",
                "telegram_chat_id": telegram_chat_id,
                "status": "active",
                "settings": {
                    "username": telegram_username,
                    "notifications": True,
                    "consent_given": True,
                    "integration_method": "username"
                },
                "metadata": {
                    "connected_at": datetime.utcnow().isoformat(),
                    "consent_timestamp": datetime.utcnow().isoformat(),
                    "phone_verified": False
                }
            }

            integration_id = await integration_service.create_integration(integration_data)

            # Step 3: Update milestones
            from src.services.milestone_service import milestone_service
            await milestone_service.user_setup_messaging(user_id)


            logger.info(f"Successfully registered Telegram user {telegram_chat_id} as user_id {user_id}")

            return {
                "user_id": user_id,
                "integration_id": str(integration_id),
                "success": True
            }

        except Exception as e:
            logger.error(f"Failed to register Telegram user {telegram_chat_id}: {str(e)}")
            raise

# Global instance
user_service = UserService()
