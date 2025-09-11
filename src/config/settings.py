import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Praxos
    PRAXOS_API_KEY = os.getenv("PRAXOS_API_KEY", "nsbYFCqqJpnXehXQ5ur6ZBCOxsRylJhKDapnfv6nRcnIE8rktha7hRi8CFX99ZyhMXO8vogvnZrWrmN4HOwN0tGVJXsD7dAiHpPbXX8TorNRo5t67jTJ8Z8NOG4QCDBp")
    PRAXOS_BASE_URL = "https://api.praxos.ai"
    PRAXOS_ENVIRONMENT_NAME = os.getenv("PRAXOS_ENVIRONMENT_NAME")
    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    # WhatsApp Business API
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN","stavros")
    WHATSAPP_API_VERSION = "v23.0"
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Test user data
    TEST_PHONE_NUMBER = os.getenv("TEST_PHONE_NUMBER")
    TEST_EMAIL_LUCAS = os.getenv("TEST_EMAIL_LUCAS")
    TEST_EMAIL_PERSONAL = os.getenv("TEST_EMAIL_PERSONAL")
    
    # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
    
    # Microsoft OAuth
    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_REFRESH_TOKEN = os.getenv("MICROSOFT_REFRESH_TOKEN")
    MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
    GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
    OUTLOOK_VALIDATION_TOKEN = os.getenv("OUTLOOK_VALIDATION_TOKEN")
    AZURE_SERVICEBUS_CONNECTION_STRING = os.getenv("AZURE_SERVICEBUS_CONNECTION_STRING")
    AZURE_SERVICEBUS_QUEUE_NAME = 'events'
    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_BLOB_CONTAINER_NAME = 'audio-transcriptions'
    # Notion
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    
    # Rate limits for testing
    MAX_EMAILS = 100
    MAX_EMAIL_ATTACHMENTS = 20
    MAX_WHATSAPP_MESSAGES = 400
    
    # Sync settings
    SYNC_THRESHOLD_MINUTES = 2
    
    # Database settings
    DB_TYPE = os.getenv("DB_TYPE", "cloud") # "cloud" or "local"
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "mypraxos")
    
    _local_mongo_connection_string = "mongodb://localhost:27017"
    _cloud_mongo_connection_string = os.getenv("MONGO_CONNECTION_STRING")

    MONGO_CONNECTION_STRING = _cloud_mongo_connection_string if DB_TYPE == "cloud" else _local_mongo_connection_string
    
    # Gmail Webhook settings (for testing with lurbisaia@gmail.com)
    GOOGLE_CLOUD_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    GMAIL_PUBSUB_TOPIC = os.getenv("GMAIL_PUBSUB_TOPIC", "gmail-notifications")
    GMAIL_PUBSUB_SUBSCRIPTION = os.getenv("GMAIL_PUBSUB_SUBSCRIPTION", "gmail-webhook-subscription")
    GMAIL_TEST_USER = os.getenv("GMAIL_TEST_USER", "lurbisaia@gmail.com")
    GMAIL_WEBHOOK_TOKEN = os.getenv("GMAIL_WEBHOOK_TOKEN")
    BASE_URL = os.getenv("BASE_URL", "https://localhost:8000")
    # REDIS_URL = os.getenv("REDIS_URL","praxosforms.redis.cache.windows.net")
    REDIS_URL = "praxosforms.redis.cache.windows.net"
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_QUEUE_NAME = "mypraxos"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    # Rate limits for webhooks
    MAX_GMAIL_WEBHOOKS_PER_HOUR = 1000
    MAX_HISTORY_CALLS_PER_HOUR = 500
    
    # Voice transcription settings
    TRANSCRIPTION_METHOD = os.getenv("TRANSCRIPTION_METHOD", "gemini")  # "gemini" or "local"
    GEMINI_TRANSCRIPTION_MODEL = os.getenv("GEMINI_TRANSCRIPTION_MODEL", "gemini-2.5-pro")
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # "tiny", "base", "small", "medium", "large"
    AUDIO_MAX_DURATION_SECONDS = int(os.getenv("AUDIO_MAX_DURATION_SECONDS", "300"))  # 5 minutes
    ENABLE_FALLBACK_TO_LOCAL = os.getenv("ENABLE_FALLBACK_TO_LOCAL", "true").lower() == "true"
    
    # Bot Identity
    BOT_EMAIL_ADDRESS = "my@praxos.ai"
    SENDER_SERVICE_URL = "https://prod-49.eastus2.logic.azure.com:443/workflows/aeaeb778b54549e0af5af99fd41d3594/triggers/When_an_HTTP_request_is_received/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2FWhen_an_HTTP_request_is_received%2Frun&sv=1.0&sig=Mg2ug-r_lbgNi1MClKfs5cOQAWE-DhIv3ycPAuHtnOQ"
    
settings = Settings()