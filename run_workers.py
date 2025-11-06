import asyncio

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)
from src.workers.execution_worker import execution_task

from src.workers.conversation_consolidator import ConversationConsolidator
from src.utils.database import conversation_db
from src.services.ai_service.prompts.cache_manager import check_and_regenerate_cache_if_needed
  

async def run_consolidator():
    """Periodically runs the conversation consolidator."""
    consolidator = ConversationConsolidator(conversation_db)
    while True:
        logger.info("Running conversation consolidator...")
        await consolidator.consolidate_all_ready_conversations()
        await asyncio.sleep(60 * 15) # Run every 15 minutes

async def main():
    """
    Main entry point to run all background workers.
    This should be run in a separate process from the web server.
    """
    logger.info("Starting all background workers...")
    await check_and_regenerate_cache_if_needed()
    await asyncio.gather(
        execution_task(),
        run_consolidator()
    )

if __name__ == "__main__":
    asyncio.run(main())
