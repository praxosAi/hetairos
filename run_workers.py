import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the main entry points for each worker type
from src.workers.execution_worker import execution_task
# Assuming other workers follow a similar pattern, add them here.
# from src.workers.conversation_consolidator import conversation_consolidator_task
# from src.ingest.ingest_worker import ingest_task

# --- Configuration ---
# Set the number of concurrent workers you want to run for each type
NUM_EXECUTION_WORKERS = 9
# NUM_CONSOLIDATOR_WORKERS = 1
# NUM_INGEST_WORKERS = 2

async def main():
    """
    Initializes and runs all the agent's background workers concurrently.
    """
    print("--- Initializing Workers ---")
    
    # Create a list to hold all the worker tasks
    tasks = []

    # Schedule the execution workers
    for i in range(NUM_EXECUTION_WORKERS):
        task = asyncio.create_task(execution_task())
        tasks.append(task)
        print(f"  - Scheduled Execution Worker {i + 1}")

    # Schedule other worker types here if they exist
    # for i in range(NUM_CONSOLIDATOR_WORKERS):
    #     task = asyncio.create_task(conversation_consolidator_task())
    #     tasks.append(task)
    #     print(f"  - Scheduled Consolidator Worker {i + 1}")

    print("\n--- All workers are running. Press Ctrl+C to stop. ---")
    
    # asyncio.gather will run all the tasks in the list concurrently.
    # It will complete when all tasks have completed. Since our workers
    # run in an infinite loop, this will run forever until the script is stopped.
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- Shutting down workers gracefully... ---")
        # The program will exit automatically as the asyncio loop is stopped.
        print("--- Shutdown complete. ---")