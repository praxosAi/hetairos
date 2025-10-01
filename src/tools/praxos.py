import json
from langchain_core.tools import tool
from src.core.praxos_client import PraxosClient
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from typing import List
logger = setup_logger(__name__)

def create_praxos_memory_tool(praxos_client: PraxosClient) -> list:
    """Create Praxos memory tool"""
    
    @tool
    async def query_praxos_memory(query: str) -> ToolExecutionResponse:
        """
        Queries the Praxos knowledge base to retrieve context and information. This will have past converesations and information about the user and their preferences.
        Use this for questions about past interactions, user preferences, or stored knowledge. this is often a good first step. you may use it to obtain information about the user and their preferences. However, do not blindly use it if you do not feel that more info is necessary.
        

        Try to make the query itself rich, adding information when needed. short queries are unlikely to get good results.
        Args:
            query: Search query for the knowledge base
        """
        try:
            logger.info(f"Querying Praxos memory: '{query}'")
            contexts = await praxos_client.search_memory(query, search_modality='node_vec', top_k=4)
            
            if not contexts:
                return json.dumps(ToolExecutionResponse(status="success", result=[]).dict(),indent=4)
            response = []
            formatted_context = "\n".join([ctx for ctx in contexts.get('sentences', [])])
            if not formatted_context:
                response = [{'text': "There is no relevant information in the Praxos memory for this query."}]
            else:
                response = contexts.get('results')

            return json.dumps(ToolExecutionResponse(status="success", result=response).dict(),indent=4)

        except Exception as e:
            logger.error(f"Error querying Praxos memory: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))
    
    @tool
    async def query_praxos_memory_intelligent_search(query: str) -> ToolExecutionResponse:
        """
        Queries the Praxos knowledge base with the computationally much more expensive intelligent search, to retrieve context and information. This will have past conversations and information about the user and their preferences.
        use this if
   
        Args:
            query: Search query for the knowledge base
        """
        try:
            logger.info(f"Querying Praxos memory: '{query}'")
            contexts = await praxos_client.search_memory(query, search_modality='intelligent', top_k=4)
            
            if not contexts:
                return json.dumps(ToolExecutionResponse(status="success", result=[]).dict(),indent=4)
            response = []
            formatted_context = "\n".join([ctx for ctx in contexts.get('sentences', [])])
            if not formatted_context:
                response = [{'text': "There is no relevant information in the Praxos memory for this query."}]
            else:
                response = contexts.get('results')

            return json.dumps(ToolExecutionResponse(status="success", result=response).dict(),indent=4)

        except Exception as e:
            logger.error(f"Error querying Praxos memory: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))
    @tool
    async def enrich_praxos_memory_entries(node_ids: List[str]) -> ToolExecutionResponse:
        """
        Enriches Praxos memory entries with additional metadata or context, taking in node_ids and returning more related entities for each node_id, within a given number of hops.
        this is to be used when you feel that you have found a relevant node to the user's query, but do not have the full context. you may use this to obtain more information about a specific node or entity.
        Args:
            entries: List of memory entries to enrich
        """
        try:
            logger.info(f"Enriching Praxos memory entries: {node_ids}")
            enriched_entries = await praxos_client.enrich_nodes(node_ids)
            return json.dumps(ToolExecutionResponse(status="success", result=enriched_entries).dict(),indent=4)
        except Exception as e:
            logger.error(f"Error enriching Praxos memory entries: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))
    async def setup_new_trigger(trigger_conditional_statement: str) -> ToolExecutionResponse:
        """Setup a trigger in Praxos memory. a trigger is a conditional statement, of form "If I receive an email from X, then do Y"
        Args:
            trigger_conditional_statement: The conditional statement to setup as a trigger. it should be complete and descriptive, in plain english. 
        """
        try:
            logger.info(f"Setting up new trigger in Praxos memory: {trigger_conditional_statement}")
            trigger_setup_response = await praxos_client.setup_trigger(trigger_conditional_statement)
            return json.dumps(ToolExecutionResponse(status="success", result=trigger_setup_response).dict(),indent=4)
        except Exception as e:
            logger.error(f"Error setting up new trigger in Praxos memory: {e}")
            return ToolExecutionResponse(status="error", system_error=str(e))
    return [query_praxos_memory,enrich_praxos_memory_entries,query_praxos_memory_intelligent_search,setup_new_trigger]


