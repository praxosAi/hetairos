import asyncio
import tempfile
import os
from typing import List, Dict, Any
from datetime import datetime
from fpdf import FPDF
from src.core.praxos_client import PraxosClient
from src.utils.database import DatabaseManager
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger
import uuid
logger = setup_logger(__name__)

class IngestWorker:
    """
    Ingests in-memory files into Praxos and records them in the database.
    Converts text-based files to PDF to meet Praxos client requirements.
    """

    def __init__(self):
        self.db_manager = DatabaseManager()

    def _convert_text_to_pdf_bytes(self, text_content: str) -> bytes:
        """Converts a string of text into a PDF and returns it as bytes using fpdf2."""
        pdf = FPDF()
        pdf.add_page()
        # Add a Unicode font that supports a wide range of characters
        pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        pdf.set_font('DejaVu', '', 12)
        # Use multi_cell to handle newlines and long lines automatically
        pdf.multi_cell(0, 10, text_content)
        return pdf.output(dest='S')

    async def ingest_files(self, user_id: str, files: List[Dict[str, Any]]):
        """
        Processes a list of in-memory files, adds them to Praxos,
        and creates corresponding entries in the database.
        """
        ingestion_results = []
        user_record = user_service.get_user_by_id(user_id)
        env_name = f"env_for_{user_record['email']}"
        
        from src.config.settings import settings
        if settings.OPERATING_MODE == "local":
            praxos_api_key = settings.PRAXOS_API_KEY
        else:
            praxos_api_key = user_record.get("praxos_api_key")

        if not praxos_api_key:
            raise ValueError("Praxos API key not found.")

        praxos_client = PraxosClient(env_name, api_key=praxos_api_key)

        for file_data in files:
            try:
                logger.info(f"Ingesting file: {file_data['filename']}")
                
                content_to_upload = file_data['content']
                upload_filename = file_data['filename']
                
                if file_data['mimetype'] == 'text/plain':
                    text_content = file_data['content'].decode('utf-8', errors='replace')
                    content_to_upload = self._convert_text_to_pdf_bytes(text_content)
                    base_name, _ = os.path.splitext(upload_filename)
                    upload_filename = f"{base_name}_{uuid.uuid4().hex[:8]}.pdf"

                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{upload_filename}") as temp_file:
                    temp_file.write(content_to_upload)
                    temp_file_path = temp_file.name
                
                try:
                    result = await praxos_client.add_file(
                        file_path=temp_file_path,
                        name=upload_filename,
                        description=f"Ingested from {file_data['metadata'].get('source', 'unknown')}"
                    )
                    
                    if result:
                        source_id = result.id
                        document_record = {
                            "user_id": user_id,
                            "source_id": source_id,
                            "filename": upload_filename,
                            "mimetype": "application/pdf",
                            "metadata": file_data["metadata"],
                            "ingested_at": datetime.utcnow()
                        }
                        await self.db_manager.add_document(document_record)
                        ingestion_results.append({"filename": upload_filename, "status": "success", "source_id": result["source_id"]})
                    else:
                        ingestion_results.append({"filename": upload_filename, "status": "failed", "error": result.get("error")})

                finally:
                    os.unlink(temp_file_path)
            
            except Exception as e:
                logger.error(f"Error ingesting file {file_data['filename']}: {e}", exc_info=True)
                ingestion_results.append({"filename": file_data['filename'], "status": "failed", "error": str(e)})
        
        return ingestion_results
