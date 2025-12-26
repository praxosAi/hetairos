import asyncio
import uuid
from ..src.core.event_queue import event_queue

async def main():
    """
    Injects a series of benchmark tasks into the event queue.
    """
    print("Starting benchmark injection...")

    # --- Define Benchmark Cases ---
    benchmark_queries = [
        # {
        #     "description": "Simple conversational query",
        #     "query": "Hi there, how are you?",
        #     "user_id": "benchmark_user_01"
        # },
        # {
        #     "description": "Simple command with all data present",
        #     "query": "Please schedule a meeting with 'jane.doe@example.com' for tomorrow at 4pm titled 'Catch up'",
        #     "user_id": "68a4e992fc24111a6257dec8"
        # },
        {
            "description": "How would I have you make all of my emails from colleagues into trello tasks?",
            "query": "Can you find the email for 'John Doe' and then send him a message saying 'Hi'?",
            "user_id": "benchmark_user_03"
        }
    ]

    # --- Define Strategies to Test ---
    strategies = ["langgraph_only"]
    # strategies = ["exec_graph_preselection"]

    for case in benchmark_queries:
        for strategy in strategies:
            session_id = str(uuid.uuid4())
            event = {
                "session_id": session_id,
                "source": "whatsapp",  # Simulate a generic source
                "user_id": "68a4e992fc24111a6257dec8",
                "payload": {"text": case["query"]},
                "metadata": {
                            "strategy": strategy,
                            "benchmark_description": case["description"]
                        }
                    }

            await event_queue.publish(event,f"{event['metadata']['benchmark_description']}_{strategy}") 
            print(f"Published event for session {session_id}: Strategy='{strategy}', Desc='{case['description']}'")

    print("Benchmark injection complete.")

if __name__ == "__main__":
    asyncio.run(main())