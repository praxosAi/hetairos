import os
from datetime import datetime, timedelta
from azure.monitor.query import LogsQueryClient
from azure.identity import DefaultAzureCredential

# --- Configuration ---
# Replace with your Log Analytics Workspace ID
# You can find this in the Azure Portal under your Log Analytics Workspace -> Overview -> Workspace ID
LOG_ANALYTICS_WORKSPACE_ID = "388ceb7e-395a-453f-bca6-87127bb03250"

# Define your KQL query to inspect the raw log message
KQL_QUERY = """
ContainerLogV2
| where PodNamespace == "hetairoi"
| project TimeGenerated, PodName, LogMessage
| order by TimeGenerated desc
| limit 50
"""

async def run_kql_query():
    # Authenticate using DefaultAzureCredential
    # This will try various methods: environment variables, managed identity,
    # and your Azure CLI login (if you're logged in via `az login`).
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)

    print(f"Running KQL query against workspace: {LOG_ANALYTICS_WORKSPACE_ID}")
    print(f"Time range: Last 1 hour")
    print("-" * 50)

    try:
        response =  client.query_workspace(
            workspace_id=LOG_ANALYTICS_WORKSPACE_ID,
            query=KQL_QUERY,
            timespan=timedelta(hours=1)
        )

        if response.tables:
            for table in response.tables:
                print(f"Table: {table.name}")
                # Print headers
                print("\t".join([col for col in table.columns]))
                # Print rows
                for row in table.rows:
                    print("\t".join([str(item) for item in row]))
        else:
            print("No results found.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_kql_query())
