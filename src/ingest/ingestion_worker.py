from typing import Dict

from src.ingest.read_worker import ReadWorker
from src.ingest.ingest_worker import IngestWorker
import asyncio
from src.utils.blob_utils import download_from_blob_storage
from src.utils.logging import setup_logger
class InitialIngestionCoordinator:
    """
    Coordinates the initial data ingestion process by using ReadWorker and IngestWorker.
    """

    def __init__(self):
        self.read_worker = ReadWorker()
        self.ingest_worker = IngestWorker()
        self.logger = setup_logger("ingestion_coordinator")

    async def perform_initial_ingestion(self, user_id: str, integration_type: str) -> Dict:
        """
        Performs the initial data ingestion for a newly added integration. ingestion is not working until we fix the integration id
        """
        pass
        # try:
        #     # 1. Read data from the integration
        #     self.logger.info(f"Starting initial ingestion for {integration_type} for user {user_id}...")
        #     in_memory_files = await self.read_worker.read_data(user_id, integration_type)
        #     self.logger.info(f"Read {len(in_memory_files)} files from {integration_type}.")

        #     # 2. Ingest the files into Praxos and database
        #     ingestion_results = await self.ingest_worker.ingest_files(user_id, in_memory_files)
        #     self.logger.info(f"Ingestion complete for {integration_type}.")

        #     successful_ingestions = [res for res in ingestion_results if res['status'] == 'success']
        #     failed_ingestions = [res for res in ingestion_results if res['status'] == 'failed']

        #     return {
        #         "success": True,
        #         "integration_type": integration_type,
        #         "ingested_counts": {
        #             "total_files": len(in_memory_files),
        #             "successful": len(successful_ingestions),
        #             "failed": len(failed_ingestions)
        #         },
        #         "message": f"Successfully ingested data for {integration_type}",
        #         "details": ingestion_results
        #     }

        # except Exception as e:
        #     return {"error": f"Ingestion failed for {integration_type}: {str(e)}"}
    async def ingest_uploaded_files(self, user_id: str, files: list) -> Dict:
        """
        Ingests files uploaded directly by the user via the API.
        """
        ### convert files from event format to in-memory file format.

        new_files = []
        file_download_tasks = []
        for file in files:
            file_download_tasks.append(download_from_blob_storage(file['blob_path']))
        

        downloaded_contents = await asyncio.gather(*file_download_tasks, return_exceptions=True)
        for old_file, content in zip(files, downloaded_contents):
            if isinstance(content, Exception):
                continue
            new_files.append({
                "filename": old_file.get("file_name", "unknown"),
                "content": content,
                "mimetype": old_file.get("mime_type"),
                "type": old_file.get("type"),
                "metadata": {"source": "file_upload", **old_file.get("metadata", {}), 'skip_db_record': True}
            })

        ingestion_results = await self.ingest_worker.ingest_files(user_id, new_files)
        successful_ingestions = [res for res in ingestion_results if res['status'] == 'success']
        failed_ingestions = [res for res in ingestion_results if res['status'] == 'failed']

        return {
            "success": True,
            "ingested_counts": {
                "total_files": len(files),
                "successful": len(successful_ingestions),
                "failed": len(failed_ingestions)
            },
            "message": "Successfully ingested uploaded files",
            "details": ingestion_results
        }
    async def ingest_event(self, user_id: str, event_details: dict) -> Dict:
        """
        Ingests an event directly by the user via the API.
        """
        ### convert files from event format to in-memory file format.

        # new_files = []
        # file_download_tasks = []
        # for file in files:
        #     file_download_tasks.append(download_from_blob_storage(file['blob_path']))
        

        # downloaded_contents = await asyncio.gather(*file_download_tasks, return_exceptions=True)
        # for old_file, content in zip(files, downloaded_contents):
        #     if isinstance(content, Exception):
        #         continue
        #     new_files.append({
        #         "filename": old_file.get("file_name", "unknown"),
        #         "content": content,
        #         "mimetype": old_file.get("mime_type"),
        #         "type": old_file.get("type"),
        #         "metadata": {"source": "file_upload", **old_file.get("metadata", {}), 'skip_db_record': True}
        #     })
        pass
        # ingestion_results = await self.ingest_worker.ingest_files(user_id, new_files)
        # successful_ingestions = [res for res in ingestion_results if res['status'] == 'success']
        # failed_ingestions = [res for res in ingestion_results if res['status'] == 'failed']

        # return {
        #     "success": True,
        #     "ingested_counts": {
        #         "total_files": len(files),
        #         "successful": len(successful_ingestions),
        #         "failed": len(failed_ingestions)
        #     },
        #     "message": "Successfully ingested uploaded files",
        #     "details": ingestion_results
        # }