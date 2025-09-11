import logging
from typing import Optional, Dict
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from src.config.settings import settings
from bson import ObjectId
from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
from datetime import timezone, timedelta
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

    # def get_user_timezone(self,user_id: str) -> ZoneInfo:
    #     """
    #     Get the user's timezone as a ZoneInfo object from their stored
    #     IANA timezone name. Defaults to UTC if not found or invalid.
    #     """
    #     try:
    #         db = self._get_database()
    #         user = db.users.find_one({"_id": ObjectId(user_id)})
            
    #         # Use a safe default of 'UTC' if user or timezone field is missing
    #         if user and user.get("timezone"):
    #             timezone_str = user["timezone"]
    #             try:
    #                 # This line converts the string into a rich timezone object
    #                 return ZoneInfo(timezone_str)
    #             except ZoneInfoNotFoundError:
    #                 logger.warning(
    #                     f"User {user_id} has an invalid timezone stored: '{timezone_str}'. "
    #                     "Defaulting to UTC."
    #                 )
    #                 # Default to UTC if the string is not a valid IANA name
    #                 return ZoneInfo("UTC")
    #         else:
    #             return ZoneInfo("UTC")
                
    #     except Exception as e:
    #         logger.error(f"Unexpected error retrieving timezone for user {user_id}: {e}")
    #         # Return a safe, unambiguous default in case of any database error
    #         return ZoneInfo("UTC")

# Global instance
user_service = UserService()