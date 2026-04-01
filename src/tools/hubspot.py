import json
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from src.integrations.hubspot.hubspot_client import HubSpotIntegration
from src.utils.logging import setup_logger
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder

logger = setup_logger(__name__)

def create_hubspot_tools(hubspot_client: HubSpotIntegration, tool_registry) -> List:
    """Creates a toolkit of HubSpot actions for the agent."""
    
    @tool
    async def hubspot_search_contacts(
        query: str = "", limit: int = 10, properties: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Search for contacts in HubSpot CRM. 
        If query is empty, returns the most recent contacts.
        Otherwise, it searches by matching email.
        You can pass a comma-separated string of property names to fetch (e.g. 'firstname,email,jobtitle').
        """
        try:
            logger.info(f"Searching HubSpot contacts: query='{query}', limit={limit}")
            props_list = [p.strip() for p in properties.split(",")] if properties else None
            results = await hubspot_client.search_contacts(query=query, limit=limit, properties=props_list)
            
            formatted_results = []
            for item in results:
                props = item.get("properties", {})
                formatted_results.append({
                    "id": item.get("id"),
                    **props
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} contacts: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_search_contacts",
                exception=e,
                integration="hubspot",
                context={"query": query}
            )

    @tool
    async def hubspot_create_contact(
        email: str, firstname: str = "", lastname: str = "", phone: str = "", company: str = ""
    ) -> ToolExecutionResponse:
        """
        Create a new contact in HubSpot CRM.
        Requires an email address.
        """
        try:
            properties = {"email": email}
            if firstname: properties["firstname"] = firstname
            if lastname: properties["lastname"] = lastname
            if phone: properties["phone"] = phone
            if company: properties["company"] = company
            
            logger.info(f"Creating HubSpot contact: {properties}")
            result = await hubspot_client.create_contact(properties)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created HubSpot contact with ID {result.get('id')}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_create_contact",
                exception=e,
                integration="hubspot",
                context={"email": email}
            )

    @tool
    async def hubspot_search_companies(
        query: str = "", limit: int = 10, properties: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Search for companies in HubSpot CRM.
        If query is empty, returns recent companies.
        Otherwise, it searches by matching company name.
        You can pass a comma-separated string of property names to fetch (e.g. 'name,domain,city').
        """
        try:
            logger.info(f"Searching HubSpot companies: query='{query}', limit={limit}")
            props_list = [p.strip() for p in properties.split(",")] if properties else None
            results = await hubspot_client.search_companies(query=query, limit=limit, properties=props_list)
            
            formatted_results = []
            for item in results:
                props = item.get("properties", {})
                formatted_results.append({
                    "id": item.get("id"),
                    **props
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} companies: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_search_companies",
                exception=e,
                integration="hubspot",
                context={"query": query}
            )

    @tool
    async def hubspot_create_company(
        name: str, domain: str = "", industry: str = "", phone: str = "", city: str = ""
    ) -> ToolExecutionResponse:
        """
        Create a new company in HubSpot CRM.
        Requires a company name.
        """
        try:
            properties = {"name": name}
            if domain: properties["domain"] = domain
            if industry: properties["industry"] = industry
            if phone: properties["phone"] = phone
            if city: properties["city"] = city
            
            logger.info(f"Creating HubSpot company: {properties}")
            result = await hubspot_client.create_company(properties)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created HubSpot company with ID {result.get('id')}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_create_company",
                exception=e,
                integration="hubspot",
                context={"name": name}
            )

    @tool
    async def hubspot_create_deal(
        dealname: str, pipeline: str = "default", dealstage: str = "", amount: str = ""
    ) -> ToolExecutionResponse:
        """
        Create a new deal in HubSpot CRM.
        Requires a deal name. Amount should be a numeric string.
        """
        try:
            properties = {"dealname": dealname, "pipeline": pipeline}
            if dealstage: properties["dealstage"] = dealstage
            if amount: properties["amount"] = amount
            
            logger.info(f"Creating HubSpot deal: {properties}")
            result = await hubspot_client.create_deal(properties)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created HubSpot deal with ID {result.get('id')}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_create_deal",
                exception=e,
                integration="hubspot",
                context={"dealname": dealname}
            )

    @tool
    async def hubspot_create_note(
        body: str, contact_id: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Create a note in HubSpot CRM to record meeting summaries or details about a contact.
        If contact_id is provided, the note will be associated with that contact.
        """
        try:
            logger.info(f"Creating HubSpot note: body='{body}', contact_id='{contact_id}'")
            result = await hubspot_client.create_note(body=body, contact_id=contact_id)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created HubSpot note with ID {result.get('id')}."
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_create_note",
                exception=e,
                integration="hubspot",
                context={"contact_id": contact_id}
            )

    @tool
    async def hubspot_create_task(
        subject: str, body: str = "", contact_id: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Create a task in HubSpot CRM to remind you to follow up with a contact.
        If contact_id is provided, the task will be associated with that contact.
        """
        try:
            logger.info(f"Creating HubSpot task: subject='{subject}', contact_id='{contact_id}'")
            result = await hubspot_client.create_task(subject=subject, body=body, contact_id=contact_id)
            
            return ToolExecutionResponse(
                status="success",
                result=f"Successfully created HubSpot task with ID {result.get('id')}."
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_create_task",
                exception=e,
                integration="hubspot",
                context={"subject": subject}
            )

    @tool
    async def hubspot_search_deals(
        query: str = "", limit: int = 10, properties: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Search for deals in HubSpot CRM.
        If query is empty, returns recent deals.
        Otherwise, it searches by matching deal name.
        You can pass a comma-separated string of property names to fetch (e.g. 'dealname,amount,dealstage').
        """
        try:
            logger.info(f"Searching HubSpot deals: query='{query}', limit={limit}")
            props_list = [p.strip() for p in properties.split(",")] if properties else None
            results = await hubspot_client.search_deals(query=query, limit=limit, properties=props_list)
            
            formatted_results = []
            for item in results:
                props = item.get("properties", {})
                formatted_results.append({
                    "id": item.get("id"),
                    **props
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} deals: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_search_deals",
                exception=e,
                integration="hubspot",
                context={"query": query}
            )

    @tool
    async def hubspot_get_notes(
        contact_id: str
    ) -> ToolExecutionResponse:
        """
        Retrieve all notes associated with a specific HubSpot contact.
        Use hubspot_search_contacts to find the contact_id first.
        """
        try:
            logger.info(f"Getting HubSpot notes for contact '{contact_id}'")
            results = await hubspot_client.get_notes(contact_id=contact_id)
            
            formatted_results = []
            for item in results:
                props = item.get("properties", {})
                formatted_results.append({
                    "id": item.get("id"),
                    **props
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} notes: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_get_notes",
                exception=e,
                integration="hubspot",
                context={"contact_id": contact_id}
            )

    @tool
    async def hubspot_get_tasks(
        contact_id: str
    ) -> ToolExecutionResponse:
        """
        Retrieve all tasks associated with a specific HubSpot contact.
        Use hubspot_search_contacts to find the contact_id first.
        """
        try:
            logger.info(f"Getting HubSpot tasks for contact '{contact_id}'")
            results = await hubspot_client.get_tasks(contact_id=contact_id)
            
            formatted_results = []
            for item in results:
                props = item.get("properties", {})
                formatted_results.append({
                    "id": item.get("id"),
                    **props
                })
            
            return ToolExecutionResponse(
                status="success",
                result=f"Found {len(formatted_results)} tasks: {json.dumps(formatted_results, indent=2)}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="hubspot_get_tasks",
                exception=e,
                integration="hubspot",
                context={"contact_id": contact_id}
            )

    all_tools = [
        hubspot_search_contacts,
        hubspot_create_contact,
        hubspot_search_companies,
        hubspot_create_company,
        hubspot_create_deal,
        hubspot_create_note,
        hubspot_create_task,
        hubspot_search_deals,
        hubspot_get_notes,
        hubspot_get_tasks
    ]
    tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools