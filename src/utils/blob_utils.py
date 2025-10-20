from azure.storage.blob.aio import BlobServiceClient
from azure.servicebus.aio import ServiceBusClient
from src.config.settings import settings
import base64
from azure.servicebus import ServiceBusMessage
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from datetime import datetime, timedelta


async def get_blob_sas_url(blob_name: str, container_name: str = None) -> str:
    """Generates a SAS URL for a blob."""
    if container_name is None:
        container_name = settings.AZURE_BLOB_CONTAINER_NAME

    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        blob_client = blob_service_client.get_blob_client(container_name, blob_name)

        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=48)
        )

        return f"{blob_client.url}?{sas_token}"

async def get_cdn_url(blob_name: str, container_name: str = "cdn-container") -> str:
    """
    Generates a public CDN URL for a blob (no SAS token needed).
    Use this for images that need to be publicly accessible (e.g., for Google Lens).

    Args:
        blob_name: Name of the blob
        container_name: Container name (default: cdn-container)

    Returns:
        Public CDN URL
    """
    cdn_endpoint = "https://praxos-images-b2bac6cwguawgwfd.z03.azurefd.net"
    return f"{cdn_endpoint}/{container_name}/{blob_name}"


async def upload_to_blob_storage(file_path: str, blob_name: str, container_name: str = None):
    """Uploads a file to Azure Blob Storage."""
    if container_name is None:
        container_name = settings.AZURE_BLOB_CONTAINER_NAME

    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(container_name)
        with open(file_path, "rb") as data:
            await container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    return blob_name


from azure.storage.blob import ContentSettings

async def upload_bytes_to_blob_storage(data: bytes, blob_name: str, content_type: str = "application/octet-stream", container_name: str = None):
    """Uploads bytes data to Azure Blob Storage with explicit content type."""
    if container_name is None:
        container_name = settings.AZURE_BLOB_CONTAINER_NAME

    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(container_name)
        await container_client.upload_blob(
            name=blob_name,
            data=data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )
    return blob_name

async def upload_image_to_cdn(data: bytes, blob_name: str, content_type: str = "image/jpeg") -> str:
    """
    Uploads an image to the CDN-enabled container and returns the public CDN URL.

    Args:
        data: Image bytes
        blob_name: Blob name (should include file extension)
        content_type: MIME type (default: image/jpeg)

    Returns:
        Public CDN URL (no SAS token)
    """
    await upload_bytes_to_blob_storage(data, blob_name, content_type, container_name="cdn-container")
    return await get_cdn_url(blob_name, container_name="cdn-container")
async def download_from_blob_storage_and_encode_to_base64(blob_name: str, container_name: str = None) -> str:
    """Downloads a file from Azure Blob Storage and encodes it to base64."""
    if container_name is None:
        container_name = settings.AZURE_BLOB_CONTAINER_NAME

    blob_service_client = BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        # Download the blob as bytes
        downloader = await blob_client.download_blob()
        data = await downloader.readall()

        # Encode to base64
        return base64.b64encode(data).decode("utf-8")
async def download_from_blob_storage(blob_name: str, container_name: str = None) -> str:
    """Downloads a file from Azure Blob Storage and encodes it to base64."""
    if container_name is None:
        container_name = settings.AZURE_BLOB_CONTAINER_NAME

    blob_service_client = BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        
        # Download the blob as bytes
        downloader = await blob_client.download_blob()
        data = await downloader.readall()
        ## return bytes
        return data


async def upload_json_to_blob_storage(json_data: dict, blob_name: str):
    """Uploads JSON data to Azure Blob Storage."""
    import json
    blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    async with blob_service_client:
        container_client = blob_service_client.get_container_client(settings.AZURE_BLOB_CONTAINER_NAME)
        data = json.dumps(json_data,default=str).encode('utf-8')
        await container_client.upload_blob(name=blob_name, data=data, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
    return blob_name
    