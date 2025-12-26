from typing import List
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.utils.user_docs_manager import user_docs_manager

logger = setup_logger(__name__)

def create_user_guide_tool(tool_registry=None) -> list:
    """
    Create the user guide consultation tool.
    """

    @tool
    async def consult_user_guide(query: str) -> ToolExecutionResponse:
        """
        Search the user-facing documentation for tools and capabilities.

        Use this tool when you need to explain to the user HOW to use a specific feature,
        or to find out which tool supports a specific user request.

        Args:
            query: The search query (e.g. "how to schedule a meeting", "what can you do with Trello").

        Returns:
            Relevant sections from the user guides.
        """
        logger.info('consult user guide called with query:', query)
        try:
            if not query or not query.strip():
                 return ErrorResponseBuilder.invalid_parameter(
                    operation="consult_user_guide",
                    param_name="query",
                    param_value=query,
                    expected_format="Non-empty search query"
                )
            
            logger.info(f"Consulting user guide for: '{query}'")
            
            # Perform search (returns dict with categories)
            results = await user_docs_manager.search(query)
            
            # Check if we have any results
            total_results = len(results['tools']) + len(results['patterns']) + len(results['capabilities'])
            
            if total_results == 0:
                 return ToolExecutionResponse(
                    status="success",
                    result=f"No relevant user guides found for: '{query}'. Try different keywords."
                )
            
            # Format output
            final_output = f"User Guide Search Results for '{query}':\n"
            
            if results['patterns']:
                final_output += "\n## 🧠 RELEVANT PATTERNS (How to chain tools)\n"
                for res in results['patterns']:
                    final_output += f"### {res['tool_id']}\n{res['content'][:500]}...\n\n"

            if results['tools']:
                final_output += "\n## 🛠️ RELEVANT TOOLS (Atomic Actions)\n"
                for res in results['tools']:
                    final_output += f"### {res['tool_id']}\n{res['content'][:300]}...\n\n"
                    
            if results['capabilities']:
                final_output += "\n## 📚 CAPABILITIES (Context)\n"
                for res in results['capabilities']:
                    final_output += f"### {res['tool_id']}\n{res['content'][:300]}...\n\n"
            
            return ToolExecutionResponse(
                status="success",
                result=final_output
            )

        except Exception as e:
            logger.error(f"Error consulting user guide: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="consult_user_guide",
                exception=e,
                integration="user_guide"
            )

    all_tools = [consult_user_guide]
    if tool_registry:
        tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools