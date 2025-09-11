from typing import Dict

from src.ingest.read_worker import ReadWorker
from src.ingest.ingest_worker import IngestWorker

class InitialIngestionCoordinator:
    """
    Coordinates the initial data ingestion process by using ReadWorker and IngestWorker.
    """

    def __init__(self):
        self.read_worker = ReadWorker()
        self.ingest_worker = IngestWorker()

    async def perform_initial_ingestion(self, user_id: str, integration_type: str) -> Dict:
        """
        Performs the initial data ingestion for a newly added integration.
        """
        try:
            # 1. Read data from the integration
            print(f"Starting initial ingestion for {integration_type} for user {user_id}...")
            in_memory_files = await self.read_worker.read_data(user_id, integration_type)
            print(f"Read {len(in_memory_files)} files from {integration_type}.")

            # 2. Ingest the files into Praxos and database
            ingestion_results = await self.ingest_worker.ingest_files(user_id, in_memory_files)
            print(f"Ingestion complete for {integration_type}.")

            successful_ingestions = [res for res in ingestion_results if res['status'] == 'success']
            failed_ingestions = [res for res in ingestion_results if res['status'] == 'failed']

            return {
                "success": True,
                "integration_type": integration_type,
                "ingested_counts": {
                    "total_files": len(in_memory_files),
                    "successful": len(successful_ingestions),
                    "failed": len(failed_ingestions)
                },
                "message": f"Successfully ingested data for {integration_type}",
                "details": ingestion_results
            }

        except Exception as e:
            return {"error": f"Ingestion failed for {integration_type}: {str(e)}"}
