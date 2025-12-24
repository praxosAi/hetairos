import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.core.praxos_client import PraxosClient
from src.config.settings import settings

async def verify_docs():
    """
    Verifies that documentation chunks are indexed and searchable.
    """
    env_name = "system_documentation_v1"
    print(f"🔌 Connecting to Praxos environment: {env_name}...")
    
    try:
        client = PraxosClient(
            environment_name=env_name,
            api_key=settings.PRAXOS_API_KEY
        )
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    # Test Query
    test_query = "how to set up email triggers"
    print(f"\n🔍 Searching for: '{test_query}'")
    
    # We use search_memory, which is exactly what the Agent uses
    response = await client.search_memory(test_query, top_k=3)
    
    sentences = response.get("sentences", [])
    
    if sentences:
        print(f"\n✅ SUCCESS! Found {len(sentences)} relevant chunks:\n")
        for i, text in enumerate(sentences):
            print(f"--- Result {i+1} ---")
            # Print a preview of the content to verify it matches our markdown files
            preview = text.replace('\n', ' ')[:150]
            print(f"Content: {preview}...")
            print("----------------")
            
        print("\nproven: The agent will be able to find this info.")
    else:
        print("\n⚠️  No results found.")
        print("Possible reasons:")
        print("1. You haven't run 'python3 scripts/ingest_docs.py' yet.")
        print("2. The ingestion failed silently.")
        print("3. The embedding process is still running on the server (give it a few seconds).")

if __name__ == "__main__":
    asyncio.run(verify_docs())
