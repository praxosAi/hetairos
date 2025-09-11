from azure.storage.blob.aio import BlobServiceClient
from azure.servicebus.aio import ServiceBusClient
from src.config.settings import settings
import base64
from azure.servicebus import ServiceBusMessage


async def upload_to_blob_storage(file_path: str, blob_name: str):
    """Uploads a file to Azure Blob Storage."""
    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(settings.AZURE_BLOB_CONTAINER_NAME)
        with open(file_path, "rb") as data:
            await container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    return blob_name


async def upload_bytes_to_blob_storage(data: bytes, blob_name: str):
    """Uploads bytes data to Azure Blob Storage."""
    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(settings.AZURE_BLOB_CONTAINER_NAME)
        await container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    return blob_name
async def download_from_blob_storage_and_encode_to_base64(blob_name: str) -> str:
    """Downloads a file from Azure Blob Storage and encodes it to base64."""
    blob_service_client = BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(
            settings.AZURE_BLOB_CONTAINER_NAME
        )
        blob_client = container_client.get_blob_client(blob_name)
        
        # Download the blob as bytes
        downloader = await blob_client.download_blob()
        data = await downloader.readall()
        
        # Encode to base64
        return base64.b64encode(data).decode("utf-8")
async def send_to_service_bus(message_body: str):
    """Sends a message to Azure Service Bus."""
    async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
        sender = client.get_queue_sender(queue_name="audio")
        async with sender:
            message = ServiceBusMessage(message_body)
            await sender.send_messages(message)