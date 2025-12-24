import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from src.core.praxos_client import PraxosClient
from src.config.settings import settings
from src.utils.logging import setup_logger
from src.utils.text_chunker import TextChunker

logger = setup_logger(__name__)

DOCS_DIR = Path("docs/knowledge_base")
ENV_NAME = "system_documentation_v1"

async def ingest_docs():
    """
    Ingest documentation files into Praxos memory as simple vector chunks.
    Uses local chunking for better control over the knowledge base.
    """
    
    if not DOCS_DIR.exists():
        logger.error(f"Documentation directory {DOCS_DIR} not found.")
        return

    # Initialize Praxos Client
    logger.info(f"Connecting to Praxos environment: {ENV_NAME}")
    try:
        praxos = PraxosClient(
            environment_name=ENV_NAME,
            api_key=settings.PRAXOS_API_KEY
        )
    except Exception as e:
        logger.error(f"Failed to initialize Praxos client: {e}")
        return

    files = list(DOCS_DIR.glob("*.md"))
    logger.info(f"Found {len(files)} markdown files to ingest.")

    # Initialize chunker (approx 1000 chars per chunk for good semantic granularity)
    chunker = TextChunker(max_length=1000)

    for file_path in files:
        try:
            logger.info(f"Processing {file_path.name}...")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Chunk the content
            chunks = list(chunker.chunk(content))
            logger.info(f"  - Split into {len(chunks)} chunks.")
            
            for i, chunk_text in enumerate(chunks):
                # Upload each chunk as a vector-searchable node
                result = await praxos.add_knowledge_chunk(
                    text=chunk_text,
                    source=file_path.name,
                    metadata={
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "doc_title": file_path.stem.replace('_', ' ').title()
                    }
                )
                
                if result.get("error"):
                    logger.error(f"    - Failed chunk {i}: {result['error']}")
                else:
                    # dot progress
                    print(".", end="", flush=True)
            
            print(f"\n  - Completed {file_path.name}")
                
        except Exception as e:
            logger.error(f"Error processing {file_path.name}: {e}")

    logger.info("Ingestion complete.")

if __name__ == "__main__":
    asyncio.run(ingest_docs())
