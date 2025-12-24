import os
from typing import List, Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.core.praxos_client import PraxosClient
from src.config.settings import settings

logger = setup_logger(__name__)

DOCS_ENV_NAME = "system_documentation_v1"

def create_documentation_tools(tool_registry=None) -> list:
    """
    Create documentation tools for the agent.

    These tools allow the agent to consult its own documentation.
    """

    @tool
    async def consult_documentation(query: str) -> ToolExecutionResponse:
        """
        Search the agent's internal documentation using semantic search.

        Use this tool to find information about the agent's capabilities, 
        how to use tools, and general usage guidelines.

        Args:
            query: The search query (natural language question or keywords).

        Returns:
            Relevant documentation text.
        """
        try:
            if not query or not query.strip():
                 return ErrorResponseBuilder.invalid_parameter(
                    operation="consult_documentation",
                    param_name="query",
                    param_value=query,
                    expected_format="Non-empty search query"
                )
            
            logger.info(f"Consulting documentation for: '{query}'")
            
            # Initialize Praxos Client for the doc environment
            try:
                praxos = PraxosClient(
                    environment_name=DOCS_ENV_NAME,
                    api_key=settings.PRAXOS_API_KEY
                )
            except Exception as e:
                logger.error(f"Failed to connect to documentation environment: {e}")
                return ErrorResponseBuilder.from_exception(
                    operation="consult_documentation",
                    exception=e,
                    integration="documentation",
                    technical_details="Could not connect to knowledge base backend."
                )

            # Perform vector search
            # We use search_memory which does vector search + scoring
            result = await praxos.search_memory(
                query=query,
                top_k=4,
                search_modality="node_vec"
            )

            if not result or result.get('error'):
                error_msg = result.get('error') if result else "No response from search service"
                logger.error(f"Search failed: {error_msg}")
                return ToolExecutionResponse(
                    status="error",
                    result="Failed to search documentation at this time."
                )

            sentences = result.get('sentences', [])
            
            if not sentences:
                 return ToolExecutionResponse(
                    status="success",
                    result=f"No relevant documentation found for: '{query}'. Try rephrasing your question."
                )
            
            # Format the output
            # Praxos returns 'sentences' which are actually chunks of text
            formatted_results = "\n\n---\n\n".join(sentences)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Documentation Search Results for '{query}':\n\n{formatted_results}"
            )

        except Exception as e:
            logger.error(f"Error consulting documentation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="consult_documentation",
                exception=e,
                integration="documentation"
            )

    all_tools = [consult_documentation]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools
