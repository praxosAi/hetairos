import json
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from src.integrations.airtable.airtable_client import AirtableIntegration
from src.utils.logging import setup_logger
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder

logger = setup_logger(__name__)

def create_airtable_tools(airtable_client: AirtableIntegration, tool_registry) -> List:
    """Creates a toolkit of Airtable actions for the agent."""
    
    @tool
    async def airtable_list_bases() -> ToolExecutionResponse:
        """
        List all Airtable bases the user has access to.
        Use this to find a base_id.
        """
        try:
            logger.info(f"Listing Airtable bases")
            results = await airtable_client.get_bases()
            
            formatted_results = []
            for item in results:
                formatted_results.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "permissionLevel": item.get("permissionLevel")
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} bases: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_list_bases",
                exception=e,
                integration="airtable"
            )

    @tool
    async def airtable_get_base_schema(base_id: str) -> ToolExecutionResponse:
        """
        Fetch the schema of a specific Airtable base.
        This tells you exactly what tables exist and what the exact column names and types are.
        Always run this before creating or updating a record if you don't know the exact column names!
        """
        try:
            logger.info(f"Fetching Airtable schema for base '{base_id}'")
            result = await airtable_client.get_base_schema(base_id)
            
            tables = result.get("tables", [])
            formatted_tables = []
            
            for table in tables:
                fields = [{"name": f.get("name"), "type": f.get("type")} for f in table.get("fields", [])]
                formatted_tables.append({
                    "id": table.get("id"),
                    "name": table.get("name"),
                    "fields": fields
                })
                
            return ToolExecutionResponse(
                status="success",
                result=f"Schema for base '{base_id}': {json.dumps(formatted_tables, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_get_base_schema",
                exception=e,
                integration="airtable",
                context={"base_id": base_id}
            )

    @tool
    async def airtable_search_records(
        base_id: str, table_id_or_name: str, formula: str = "", limit: int = 10
    ) -> ToolExecutionResponse:
        """
        Search for records in a specific Airtable base and table.
        Optionally accepts a filterByFormula string to narrow results.
        """
        try:
            logger.info(f"Searching Airtable records: base='{base_id}', table='{table_id_or_name}'")
            results = await airtable_client.search_records(base_id, table_id_or_name, formula, limit)
            
            formatted_results = []
            for item in results:
                formatted_results.append({
                    "id": item.get("id"),
                    "createdTime": item.get("createdTime"),
                    "fields": item.get("fields", {})
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} records: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_search_records",
                exception=e,
                integration="airtable",
                context={"base_id": base_id, "table_id_or_name": table_id_or_name}
            )

    @tool
    async def airtable_create_record(
        base_id: str, table_id_or_name: str, fields: str
    ) -> ToolExecutionResponse:
        """
        Create a new record in a specific Airtable base and table.
        The 'fields' parameter MUST be a valid JSON string mapping column names to values.
        Example fields: '{"Name": "John Doe", "Status": "In Progress"}'
        """
        try:
            logger.info(f"Creating Airtable record in {base_id}/{table_id_or_name}")
            
            try:
                parsed_fields = json.loads(fields)
            except json.JSONDecodeError:
                return ToolExecutionResponse(
                    status="error",
                    error="The 'fields' parameter must be a valid JSON string."
                )
                
            result = await airtable_client.create_record(base_id, table_id_or_name, parsed_fields)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created Airtable record with ID {result.get('id')}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_create_record",
                exception=e,
                integration="airtable",
                context={"base_id": base_id, "table_id_or_name": table_id_or_name}
            )

    @tool
    async def airtable_update_record(
        base_id: str, table_id_or_name: str, record_id: str, fields: str
    ) -> ToolExecutionResponse:
        """
        Update an existing record in an Airtable base and table.
        The 'fields' parameter MUST be a valid JSON string containing only the columns to update.
        Example fields: '{"Status": "Done", "Notes": "Completed"}'
        """
        try:
            logger.info(f"Updating Airtable record {record_id} in {base_id}/{table_id_or_name}")
            
            try:
                parsed_fields = json.loads(fields)
            except json.JSONDecodeError:
                return ToolExecutionResponse(
                    status="error",
                    error="The 'fields' parameter must be a valid JSON string."
                )
                
            result = await airtable_client.update_record(base_id, table_id_or_name, record_id, parsed_fields)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully updated Airtable record with ID {result.get('id')}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_update_record",
                exception=e,
                integration="airtable",
                context={"base_id": base_id, "table_id_or_name": table_id_or_name, "record_id": record_id}
            )

    @tool
    async def airtable_delete_record(
        base_id: str, table_id_or_name: str, record_id: str
    ) -> ToolExecutionResponse:
        """
        Delete a record from a specific Airtable base and table.
        """
        try:
            logger.info(f"Deleting Airtable record {record_id} from {base_id}/{table_id_or_name}")
            success = await airtable_client.delete_record(base_id, table_id_or_name, record_id)
            
            if success:
                return ToolExecutionResponse(
                    status="success",
                    result=f"Successfully deleted Airtable record {record_id}"
                )
            else:
                return ToolExecutionResponse(
                    status="error",
                    error=f"Failed to delete Airtable record {record_id}"
                )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="airtable_delete_record",
                exception=e,
                integration="airtable",
                context={"base_id": base_id, "table_id_or_name": table_id_or_name, "record_id": record_id}
            )

    all_tools = [
        airtable_list_bases,
        airtable_get_base_schema,
        airtable_search_records,
        airtable_create_record,
        airtable_update_record,
        airtable_delete_record
    ]
    tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools