import json
from langchain_core.tools import tool
from src.core.praxos_client import PraxosClient
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from src.utils.database import db_manager
from typing import List
logger = setup_logger(__name__)

def create_praxos_memory_tool(praxos_client: PraxosClient, user_id: str, conversation_id: str) -> list:
    """Create Praxos memory tool"""
    
    @tool
    async def query_praxos_memory(query: str, top_k: int = 4, exclude_seen_node_ids: List[str] = None) -> ToolExecutionResponse:
        """
        Queries the Praxos knowledge base to retrieve context and information. This will have past converesations and information about the user and their preferences.
        Use this for questions about past interactions, user preferences, or stored knowledge. this is often a good first step. you may use it to obtain information about the user and their preferences. However, do not blindly use it if you do not feel that more info is necessary.


        Try to make the query itself rich, adding information when needed. short queries are unlikely to get good results.
        Args:
            query: Search query for the knowledge base
            top_k: Number of results to return
            exclude_seen_node_ids: Optional list of node IDs to exclude from results (useful for iterative searches)
        """
        try:
            logger.info(f"Querying Praxos memory: '{query}'")
            contexts = await praxos_client.search_memory(query, search_modality='node_vec', top_k=top_k, exclude_seen=exclude_seen_node_ids)
            
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
            logger.error(f"Error querying Praxos memory: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="query_praxos_memory",
                exception=e,
                integration="Praxos",
                context={"query": query}
            )
    
    @tool
    async def query_praxos_memory_intelligent_search(query: str, top_k: int = 10) -> ToolExecutionResponse:
        """
        Queries the Praxos knowledge base with the computationally much more expensive intelligent search, to retrieve context and information. This will have past conversations and information about the user and their preferences.
        use this if you have not found relevant information with the normal search, or if you feel that the query is complex and requires a deeper understanding of the context. this is often a good second step, if the normal search does not yield good results.
   
        Args:
            query: Search query for the knowledge base
        """
        try:
            logger.info(f"Querying Praxos memory: '{query}'")
            contexts = await praxos_client.search_memory(query, search_modality='intelligent', top_k=top_k)
            
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
            logger.error(f"Error querying Praxos memory: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="query_praxos_memory",
                exception=e,
                integration="Praxos",
                context={"query": query}
            )
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
            logger.error(f"Error enriching Praxos memory entries: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="enrich_praxos_memory_entries",
                exception=e,
                integration="Praxos",
                context={"node_ids": node_ids}
            )
    @tool
    async def setup_new_trigger(trigger_conditional_statement: str, one_time: bool = True) -> ToolExecutionResponse:
        """Setup a trigger in Praxos memory. a trigger is a conditional statement, of form "If I receive an email from X, then do Y"
        Args:
            trigger_conditional_statement: The conditional statement to setup as a trigger. it should be complete and descriptive, in plain english. 
            one_time: Whether the trigger should be one-time or persistent. Defaults to True (one-time). if the user wants a persistent trigger, set this to False. Try to guess from context and nature of the task, but if unsure, ask the user.
        """
        try:
            logger.info(f"Setting up new trigger in Praxos memory: {trigger_conditional_statement}")
            trigger_setup_response = await praxos_client.setup_trigger(trigger_conditional_statement)
            if 'rule_id' in trigger_setup_response:
                await db_manager.insert_new_trigger(trigger_setup_response['rule_id'], conversation_id,trigger_conditional_statement, user_id, one_time,)
            return json.dumps(ToolExecutionResponse(status="success", result=trigger_setup_response).dict(),indent=4)
        except Exception as e:
            logger.error(f"Error setting up new trigger in Praxos memory: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="setup_new_trigger",
                exception=e,
                integration="Praxos",
                context={"trigger_conditional_statement": trigger_conditional_statement}
            )

    @tool
    async def extract_entities_by_type(type_description: str, max_results: int = 20) -> ToolExecutionResponse:
        """
        Extract entities from the knowledge graph using intelligent type-based extraction.
        This uses AI to understand what type of entity you're looking for and retrieves all matching entities.

        Args:
            type_description: Natural language description of entities to extract (e.g., "people I know", "vehicles", "meetings")
            max_results: Maximum number of entities to return

        Examples:
            - "people I've communicated with"
            - "companies I've mentioned"
            - "vehicles I own"
            - "calendar events"
        """
        try:
            logger.info(f"Extracting entities: '{type_description}'")
            result = await praxos_client.extract_intelligent(
                query=type_description,
                strategy='entity_extraction',
                max_results=max_results
            )

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="extract_entities_by_type",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            return json.dumps(ToolExecutionResponse(status="success", result=result['hits']).dict(), indent=4)

        except Exception as e:
            logger.error(f"Error extracting entities: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="extract_entities_by_type",
                exception=e,
                integration="Praxos",
                context={"type_description": type_description}
            )

    @tool
    async def extract_literals_by_type(literal_description: str, max_results: int = 20) -> ToolExecutionResponse:
        """
        Extract literal values (emails, phones, addresses, etc.) from the knowledge graph using intelligent extraction.
        This uses AI to understand what type of literal you're looking for and retrieves all matching values.

        Args:
            literal_description: Natural language description of literals to extract (e.g., "email addresses", "phone numbers", "addresses")
            max_results: Maximum number of literals to return

        Examples:
            - "all email addresses"
            - "phone numbers I have stored"
            - "postal addresses"
            - "dates I've mentioned"
        """
        try:
            logger.info(f"Extracting literals: '{literal_description}'")
            result = await praxos_client.extract_intelligent(
                query=literal_description,
                strategy='literal_extraction',
                max_results=max_results
            )

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="extract_literals_by_type",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            return json.dumps(ToolExecutionResponse(status="success", result=result['hits']).dict(), indent=4)

        except Exception as e:
            logger.error(f"Error extracting literals: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="extract_literals_by_type",
                exception=e,
                integration="Praxos",
                context={"literal_description": literal_description}
            )

    @tool
    async def get_entities_by_type_name(type_name: str, max_results: int = 50) -> ToolExecutionResponse:
        """
        Get all entities of a specific type from the knowledge graph.
        Use this when you know the exact type name (e.g., "schema:Person", "Vehicle", "Organization").

        Args:
            type_name: Exact type name of entities to retrieve (e.g., "schema:Person", "Vehicle", "schema:Integration")
            max_results: Maximum number of entities to return

        Examples:
            - "schema:Person" → All people in the knowledge graph
            - "Vehicle" → All vehicles
            - "schema:Integration" → All connected integrations
            - "Organization" → All organizations
        """
        try:
            logger.info(f"Getting entities by type: '{type_name}'")
            results = await praxos_client.get_nodes_by_type(
                type_name=type_name,
                include_literals=True,
                max_results=max_results
            )

            if isinstance(results, dict) and 'error' in results:
                return ErrorResponseBuilder.from_exception(
                    operation="get_entities_by_type_name",
                    exception=Exception(results['error']),
                    integration="Praxos"
                )

            return json.dumps(ToolExecutionResponse(status="success", result=results).dict(), indent=4)

        except Exception as e:
            logger.error(f"Error getting entities by type: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="get_entities_by_type_name",
                exception=e,
                integration="Praxos",
                context={"type_name": type_name}
            )

    @tool
    async def store_new_entity_in_knowledge_graph(
        entity_type: str,
        label: str,
        properties_json: str
    ) -> ToolExecutionResponse:
        """
        Store a new entity in the knowledge graph for future reference.
        Use this when the user wants to remember new information about people, places, organizations, or things.

        Args:
            entity_type: Type of entity - "schema:Person", "Vehicle", "Organization", "Event", etc.
            label: Human-readable name/label for the entity
            properties_json: JSON string of properties, format: [{"key": "email", "value": "...", "type": "EmailType"}, ...]
                            Types are optional and will be auto-inferred if not provided.

        Examples:
            User: "Remember that Sarah works at Google as a Software Engineer"
            → entity_type="schema:Person", label="Sarah", properties_json='[{"key":"employer","value":"Google"},{"key":"role","value":"Software Engineer"}]'

            User: "Store my new car - Tesla Model 3"
            → entity_type="Vehicle", label="Tesla Model 3", properties_json='[{"key":"make","value":"Tesla"},{"key":"model","value":"Model 3"}]'

            User: "Add john@company.com to my contacts"
            → entity_type="schema:Person", label="John", properties_json='[{"key":"email","value":"john@company.com","type":"EmailType"}]'
        """
        try:
            import json
            properties = json.loads(properties_json)

            logger.info(f"Storing entity: {label} ({entity_type}) with {len(properties)} properties")

            result = await praxos_client.create_entity_in_kg(entity_type, label, properties)

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="store_new_entity_in_knowledge_graph",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            nodes_created = result.get('nodes_created', 0)
            created_ids = result.get('created_node_ids', [])

            return ToolExecutionResponse(
                status="success",
                result=f"Successfully stored '{label}' ({entity_type}) in the knowledge graph. Created {nodes_created} nodes."
            )

        except json.JSONDecodeError as e:
            return ErrorResponseBuilder.invalid_parameter(
                operation="store_new_entity_in_knowledge_graph",
                param_name="properties_json",
                param_value=properties_json,
                expected_format='JSON array like [{"key":"email","value":"test@example.com"}]',
                validation_error=str(e)
            )
        except Exception as e:
            logger.error(f"Error storing entity: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="store_new_entity_in_knowledge_graph",
                exception=e,
                integration="Praxos",
                context={"entity_type": entity_type, "label": label}
            )

    @tool
    async def update_knowledge_graph_literal(
        node_id: str,
        new_value: str,
        new_type: str = None
    ) -> ToolExecutionResponse:
        """
        Update a literal value in the knowledge graph.
        Use this when the user wants to correct or update stored information.

        Args:
            node_id: The node ID of the literal to update (obtained from search results)
            new_value: The new value for the literal
            new_type: Optional new type for the literal (e.g., "EmailType", "PhoneNumberType")

        Examples:
            User: "Update John's email to john@newcompany.com"
            → First search for John's email literal, then update with node_id

            User: "Change my phone number to 555-9999"
            → First search for phone literal, then update

        Workflow:
            1. Use query_praxos_memory or extract_literals_by_type to find the node
            2. Extract the node_id from the result
            3. Call this tool to update the value
        """
        try:
            logger.info(f"Updating literal {node_id} to: {new_value}")

            result = await praxos_client.update_literal_value(node_id, new_value, new_type)

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="update_knowledge_graph_literal",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            nodes_modified = result.get('nodes_modified', 0)

            return ToolExecutionResponse(
                status="success",
                result=f"Successfully updated literal to: {new_value}. Modified {nodes_modified} nodes."
            )

        except Exception as e:
            logger.error(f"Error updating literal: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="update_knowledge_graph_literal",
                exception=e,
                integration="Praxos",
                context={"node_id": node_id}
            )

    @tool
    async def update_entity_properties_in_knowledge_graph(
        node_id: str,
        properties_json: str,
        replace_all: bool = False
    ) -> ToolExecutionResponse:
        """
        Update an entity's properties in the knowledge graph.
        Use this to add new information to an existing entity or modify existing properties.

        Args:
            node_id: The node ID of the entity to update (obtained from search results)
            properties_json: JSON string of properties to add/update, format: [{"key": "...", "value": "...", "type": "..."}]
            replace_all: If True, replace ALL properties; if False, merge with existing (default: False)

        Examples:
            User: "Add Sarah's LinkedIn profile to her contact info"
            → node_id from search, properties_json='[{"key":"linkedin","value":"https://linkedin.com/in/sarah"}]', replace_all=False

            User: "Update my car's info - it's now silver instead of white"
            → properties_json='[{"key":"color","value":"silver"}]', replace_all=False

        Workflow:
            1. Use query_praxos_memory or get_entities_by_type_name to find the entity
            2. Extract the node_id
            3. Call this tool to update properties
        """
        try:
            import json
            properties = json.loads(properties_json)

            logger.info(f"Updating entity {node_id} with {len(properties)} properties (replace_all={replace_all})")

            result = await praxos_client.update_entity_properties(node_id, properties, replace_all)

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="update_entity_properties_in_knowledge_graph",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            nodes_modified = result.get('nodes_modified', 0)
            relationships_modified = result.get('relationships_modified', 0)

            return ToolExecutionResponse(
                status="success",
                result=f"Successfully updated entity properties. Modified {nodes_modified} nodes and {relationships_modified} relationships."
            )

        except json.JSONDecodeError as e:
            return ErrorResponseBuilder.invalid_parameter(
                operation="update_entity_properties_in_knowledge_graph",
                param_name="properties_json",
                param_value=properties_json,
                expected_format='JSON array like [{"key":"email","value":"test@example.com"}]',
                validation_error=str(e)
            )
        except Exception as e:
            logger.error(f"Error updating entity properties: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="update_entity_properties_in_knowledge_graph",
                exception=e,
                integration="Praxos",
                context={"node_id": node_id}
            )

    @tool
    async def delete_from_knowledge_graph(
        node_id: str,
        cascade: bool = True,
        force: bool = False
    ) -> ToolExecutionResponse:
        """
        Delete a node from the knowledge graph.
        Use this when the user wants to remove stored information.

        Args:
            node_id: The node ID to delete (obtained from search results)
            cascade: If True, also delete connected properties (default: True)
            force: If True, force delete even highly connected entities (default: False)

        Examples:
            User: "Delete my old phone number 555-1234"
            → First search for the phone literal, then delete it

            User: "Remove Sarah from my contacts"
            → First search for Person(Sarah), then delete with cascade=True

        Workflow:
            1. Use query_praxos_memory or extract tools to find the node
            2. Extract the node_id
            3. Call this tool to delete
        """
        try:
            logger.info(f"Deleting node {node_id} (cascade={cascade}, force={force})")

            result = await praxos_client.delete_node_from_kg(node_id, cascade, force)

            if 'error' in result:
                return ErrorResponseBuilder.from_exception(
                    operation="delete_from_knowledge_graph",
                    exception=Exception(result['error']),
                    integration="Praxos"
                )

            nodes_deleted = result.get('nodes_deleted', 0)
            cascade_deletes = result.get('cascade_deletes', 0)

            return ToolExecutionResponse(
                status="success",
                result=f"Successfully deleted node. Removed {nodes_deleted} nodes" +
                      (f" and {cascade_deletes} connected properties" if cascade_deletes else "")
            )

        except Exception as e:
            logger.error(f"Error deleting node: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="delete_from_knowledge_graph",
                exception=e,
                integration="Praxos",
                context={"node_id": node_id}
            )

    @tool
    async def check_connected_integrations() -> ToolExecutionResponse:
        """
        Check which integrations the user has connected (Gmail, Slack, Notion, etc.).
        Use this to determine what capabilities are available before planning actions.

        This is useful for:
        - Checking if user has required integrations before attempting operations
        - Discovering available integrations to suggest to the user
        - Understanding the user's connected ecosystem

        Returns:
            List of connected integrations with their status and capabilities

        Example Usage:
            User: "Can I send a Slack message?"
            → Check integrations first, if Slack is connected, proceed; otherwise, offer to connect it
        """
        try:
            logger.info("Checking connected integrations")

            integrations = await praxos_client.get_nodes_by_type(
                type_name="schema:Integration",
                include_literals=True,
                max_results=50
            )

            if isinstance(integrations, dict) and 'error' in integrations:
                return ErrorResponseBuilder.from_exception(
                    operation="check_connected_integrations",
                    exception=Exception(integrations['error']),
                    integration="Praxos"
                )

            # Format for AI consumption
            integration_summary = []
            for integ in integrations:
                data = integ.get('data', {})
                properties = data.get('properties', {})

                integration_summary.append({
                    "name": data.get('label', 'Unknown'),
                    "type": properties.get('integration_type', 'Unknown'),
                    "status": properties.get('status', 'Unknown'),
                    "capabilities": properties.get('capabilities', []),
                    "account": properties.get('account', 'N/A')
                })

            return json.dumps(ToolExecutionResponse(
                status="success",
                result={
                    "integrations": integration_summary,
                    "count": len(integration_summary),
                    "connected": [i['type'] for i in integration_summary if i['status'] == 'active']
                }
            ).dict(), indent=4)

        except Exception as e:
            logger.error(f"Error checking integrations: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="check_connected_integrations",
                exception=e,
                integration="Praxos"
            )

    return [
        query_praxos_memory,
        enrich_praxos_memory_entries,
        query_praxos_memory_intelligent_search,
        setup_new_trigger,
        extract_entities_by_type,
        extract_literals_by_type,
        get_entities_by_type_name,
        store_new_entity_in_knowledge_graph,
        update_knowledge_graph_literal,
        update_entity_properties_in_knowledge_graph,
        delete_from_knowledge_graph,
        check_connected_integrations
    ]


