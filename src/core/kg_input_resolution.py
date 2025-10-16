"""
Type-Driven Tool Input Resolution System

This module enables automatic resolution of tool parameters from the knowledge graph
based on type matching. Instead of asking users for information that already exists,
the AI can query the KG and auto-fill parameters.

Example:
    Tool: send_email(recipient: EmailType, subject: str, body: str)

    User: "Email John about the meeting"

    Resolution:
    1. Parse docstring → recipient is EmailType (KG-resolvable)
    2. Query KG → Find Person(label="John") with EmailType literal
    3. Auto-resolve → recipient = "john@company.com"
    4. Execute directly without asking user
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)


class ToolInputResolver:
    """
    Analyzes tool parameters and resolves them from the knowledge graph when possible.
    Uses type matching to determine which parameters can be auto-filled from KG data.
    """

    def __init__(self, praxos_client: PraxosClient):
        self.praxos = praxos_client

        # Mapping of common parameter names to KG literal types
        # This helps when docstrings don't explicitly specify types
        self.PARAM_NAME_TO_TYPE_MAP = {
            # Email-related
            "email": "EmailType",
            "recipient": "EmailType",
            "sender": "EmailType",
            "sender_email": "EmailType",
            "to": "EmailType",
            "from_email": "EmailType",
            "cc": "EmailType",
            "bcc": "EmailType",

            # Phone-related
            "phone": "PhoneNumberType",
            "phone_number": "PhoneNumberType",
            "mobile": "PhoneNumberType",

            # Address-related
            "address": "PostalAddress",
            "street_address": "PostalAddress",
            "location": "PostalAddress",

            # Name-related
            "name": "NameType",
            "first_name": "FirstNameType",
            "last_name": "LastNameType",
            "full_name": "NameType",

            # Organization-related
            "company": "OrganizationNameType",
            "organization": "OrganizationNameType",

            # URL-related
            "url": "URLType",
            "link": "URLType",
            "website": "URLType",
        }

        # Types that should NEVER be resolved from KG (always user-provided)
        self.DE_NOVO_TYPES = {
            "str", "string", "text", "content", "message", "body",
            "subject", "title", "description", "note", "comment",
            "int", "integer", "float", "number", "bool", "boolean",
            "datetime", "date", "time"
        }

    def parse_parameter_type_from_docstring(self, tool_docstring: str, param_name: str) -> Optional[str]:
        """
        Parse parameter type from tool docstring.

        Looks for patterns like:
        - "recipient: EmailType" or "recipient (EmailType)"
        - "phone: PhoneNumberType (KG)"
        - "email: str - EmailType literal from KG"

        Args:
            tool_docstring: The tool's docstring
            param_name: Parameter name to find type for

        Returns:
            KG type string if found, None otherwise
        """
        if not tool_docstring:
            return None

        # Pattern 1: "param_name: TypeName" or "param_name (TypeName)"
        pattern1 = rf"{param_name}\s*:\s*(\w+Type|\w+Address)"
        match = re.search(pattern1, tool_docstring, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 2: "param_name (TypeName)" in Args section
        pattern2 = rf"{param_name}.*?\((\w+Type|\w+Address)\)"
        match = re.search(pattern2, tool_docstring, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: "param_name: ... TypeName"
        pattern3 = rf"{param_name}:.*?(\w+Type|\w+Address)"
        match = re.search(pattern3, tool_docstring, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 4: Check for "(KG)" marker indicating KG-resolvable
        pattern4 = rf"{param_name}.*?\(KG\)"
        if re.search(pattern4, tool_docstring, re.IGNORECASE):
            # Use param name mapping
            return self.PARAM_NAME_TO_TYPE_MAP.get(param_name.lower())

        return None

    def infer_kg_type_from_param_name(self, param_name: str) -> Optional[str]:
        """
        Infer KG literal type from parameter name using heuristics.

        Args:
            param_name: Parameter name

        Returns:
            Inferred KG type or None
        """
        param_lower = param_name.lower()

        # Direct mapping
        if param_lower in self.PARAM_NAME_TO_TYPE_MAP:
            return self.PARAM_NAME_TO_TYPE_MAP[param_lower]

        # Heuristic matching
        if 'email' in param_lower:
            return "EmailType"
        elif 'phone' in param_lower or 'mobile' in param_lower:
            return "PhoneNumberType"
        elif 'address' in param_lower and 'email' not in param_lower:
            return "PostalAddress"
        elif 'url' in param_lower or 'link' in param_lower:
            return "URLType"
        elif param_lower in ['name', 'contact', 'person']:
            return "NameType"

        return None

    def is_kg_resolvable(self, kg_type: str) -> bool:
        """
        Check if a type should be resolved from KG or is de novo.

        Args:
            kg_type: The type string

        Returns:
            True if should query KG, False if always de novo
        """
        if not kg_type:
            return False

        kg_type_lower = kg_type.lower()

        # Explicit de novo types
        if kg_type_lower in self.DE_NOVO_TYPES:
            return False

        # Types ending in "Type" or containing "Type" are usually KG literals
        if 'type' in kg_type_lower or 'address' in kg_type_lower:
            return True

        return False

    async def find_kg_candidates(
        self,
        kg_type: str,
        search_context: str,
        param_value_hint: Any = None,
        max_candidates: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find candidate values from KG for a given type.

        Args:
            kg_type: The KG literal type to search for (e.g., "EmailType")
            search_context: Context from user query to help matching
            param_value_hint: Optional hint value from query parsing (e.g., "John")
            max_candidates: Maximum candidates to return

        Returns:
            List of candidate entities with their literal values
        """
        try:
            # Build search query
            if param_value_hint:
                search_query = f"{param_value_hint} {kg_type}"
            else:
                search_query = f"{search_context} {kg_type}"

            # Use intelligent literal extraction
            result = await self.praxos.extract_intelligent(
                query=search_query,
                strategy='literal_extraction',
                max_results=max_candidates
            )

            candidates = result.get('hits', [])

            logger.info(f"Found {len(candidates)} candidates for {kg_type} with query '{search_query}'")

            return candidates

        except Exception as e:
            logger.error(f"Error finding KG candidates for {kg_type}: {e}")
            return []

    async def resolve_parameter(
        self,
        param_name: str,
        param_type: Optional[str],
        user_query: str,
        param_value_hint: Any = None
    ) -> Dict[str, Any]:
        """
        Attempt to resolve a single parameter from KG.

        Args:
            param_name: Parameter name
            param_type: Inferred/parsed KG type
            user_query: Full user query for context
            param_value_hint: Optional hint extracted from query

        Returns:
            Dictionary with resolution result:
            {
                "resolvable": bool,
                "kg_type": str,
                "candidates": List[Dict],
                "auto_resolvable": bool,  # True if exactly 1 candidate
                "resolution_strategy": str
            }
        """
        # Determine KG type
        kg_type = param_type or self.infer_kg_type_from_param_name(param_name)

        if not kg_type or not self.is_kg_resolvable(kg_type):
            return {
                "resolvable": False,
                "kg_type": None,
                "candidates": [],
                "auto_resolvable": False,
                "resolution_strategy": "de_novo"
            }

        # Find candidates from KG
        candidates = await self.find_kg_candidates(
            kg_type=kg_type,
            search_context=user_query,
            param_value_hint=param_value_hint,
            max_candidates=5
        )

        auto_resolvable = len(candidates) == 1

        return {
            "resolvable": True,
            "kg_type": kg_type,
            "candidates": candidates,
            "auto_resolvable": auto_resolvable,
            "resolution_strategy": "auto" if auto_resolvable else "disambiguate"
        }

    async def analyze_tool_parameters(
        self,
        tool_name: str,
        tool_docstring: str,
        tool_params: List[str],
        user_query: str,
        query_entities: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Analyze all parameters for a tool to determine which can be resolved from KG.

        Args:
            tool_name: Name of the tool
            tool_docstring: Tool's docstring
            tool_params: List of parameter names
            user_query: User's query
            query_entities: Optional pre-extracted entities from query

        Returns:
            Complete analysis with resolution strategies for each parameter
        """
        analysis = {
            "tool_name": tool_name,
            "parameters": {},
            "kg_resolvable_count": 0,
            "auto_resolvable_count": 0,
            "needs_disambiguation_count": 0,
            "de_novo_count": 0,
            "overall_confidence": "unknown"
        }

        for param_name in tool_params:
            # Skip common system parameters
            if param_name in ['self', 'cls', 'return', 'kwargs', 'args']:
                continue

            # Parse type from docstring
            param_type = self.parse_parameter_type_from_docstring(tool_docstring, param_name)

            # Extract hint from query_entities if available
            param_hint = None
            if query_entities:
                param_hint = query_entities.get(param_name)

            # Resolve parameter
            resolution = await self.resolve_parameter(
                param_name=param_name,
                param_type=param_type,
                user_query=user_query,
                param_value_hint=param_hint
            )

            analysis["parameters"][param_name] = resolution

            # Update counters
            if resolution["resolvable"]:
                analysis["kg_resolvable_count"] += 1
                if resolution["auto_resolvable"]:
                    analysis["auto_resolvable_count"] += 1
                else:
                    analysis["needs_disambiguation_count"] += 1
            else:
                analysis["de_novo_count"] += 1

        # Assess overall confidence
        total_params = len(analysis["parameters"])
        if total_params == 0:
            analysis["overall_confidence"] = "n/a"
        else:
            auto_ratio = analysis["auto_resolvable_count"] / total_params
            if auto_ratio >= 0.8:
                analysis["overall_confidence"] = "high"
            elif auto_ratio >= 0.5:
                analysis["overall_confidence"] = "medium"
            elif analysis["kg_resolvable_count"] > 0:
                analysis["overall_confidence"] = "low"
            else:
                analysis["overall_confidence"] = "none"

        logger.info(
            f"Tool {tool_name} analysis: "
            f"{analysis['auto_resolvable_count']}/{total_params} auto-resolvable, "
            f"{analysis['needs_disambiguation_count']} need disambiguation, "
            f"{analysis['de_novo_count']} de novo"
        )

        return analysis

    def format_resolution_guidance(self, analysis: Dict[str, Any]) -> str:
        """
        Format resolution analysis into AI-readable guidance.

        Args:
            analysis: Output from analyze_tool_parameters

        Returns:
            Formatted string for AI context
        """
        guidance = f"**Parameter Resolution for {analysis['tool_name']}:**\n\n"

        auto_resolvable = []
        needs_disambiguation = []
        de_novo = []

        for param_name, resolution in analysis["parameters"].items():
            if resolution["auto_resolvable"]:
                candidate = resolution["candidates"][0]
                value = self._extract_value_from_candidate(candidate)
                auto_resolvable.append(f"  ✓ {param_name}: Auto-filled with '{value}' from KG")

            elif resolution["resolvable"] and resolution["candidates"]:
                candidate_values = [self._extract_value_from_candidate(c) for c in resolution["candidates"][:3]]
                needs_disambiguation.append(
                    f"  ? {param_name}: Multiple options found - {', '.join(candidate_values)}"
                )

            elif resolution["resolvable"]:
                needs_disambiguation.append(
                    f"  ? {param_name}: Type {resolution['kg_type']} - No matches found in KG, ask user"
                )

            else:
                de_novo.append(f"  ✗ {param_name}: User must provide (not in KG)")

        if auto_resolvable:
            guidance += "**Auto-Resolved from KG:**\n" + "\n".join(auto_resolvable) + "\n\n"

        if needs_disambiguation:
            guidance += "**Needs Clarification:**\n" + "\n".join(needs_disambiguation) + "\n\n"

        if de_novo:
            guidance += "**User Must Provide:**\n" + "\n".join(de_novo) + "\n\n"

        guidance += f"**Confidence:** {analysis['overall_confidence']}\n"

        return guidance

    def _extract_value_from_candidate(self, candidate: Dict[str, Any]) -> str:
        """Extract the actual value from a candidate result"""
        # Handle different result formats
        if 'payload' in candidate:
            payload = candidate['payload']
            if 'literal_value' in payload:
                return payload['literal_value']
            if 'value' in payload:
                return payload['value']

        if 'sentence' in candidate:
            return candidate['sentence']

        if 'label' in candidate:
            return candidate['label']

        return str(candidate.get('id', 'unknown'))

    async def build_auto_fill_map(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a map of parameter names to auto-filled values.
        Only includes parameters with exactly 1 candidate (auto-resolvable).

        Args:
            analysis: Output from analyze_tool_parameters

        Returns:
            Dictionary mapping parameter names to values
        """
        auto_fill = {}

        for param_name, resolution in analysis["parameters"].items():
            if resolution["auto_resolvable"] and resolution["candidates"]:
                value = self._extract_value_from_candidate(resolution["candidates"][0])
                auto_fill[param_name] = value
                logger.info(f"Auto-filling {param_name} = {value}")

        return auto_fill


class ToolParameterExtractor:
    """
    Extracts parameter information from tool objects.
    """

    @staticmethod
    def extract_parameters_from_tool(tool) -> Tuple[List[str], str]:
        """
        Extract parameter names and docstring from a tool.

        Args:
            tool: LangChain tool object

        Returns:
            Tuple of (parameter_names, docstring)
        """
        try:
            # Get parameter names from tool schema
            if hasattr(tool, 'args_schema') and tool.args_schema:
                # Pydantic model
                params = list(tool.args_schema.__fields__.keys())
            elif hasattr(tool, 'args'):
                # Direct args dict
                params = list(tool.args.keys())
            elif hasattr(tool, 'func'):
                # Function-based tool
                import inspect
                sig = inspect.signature(tool.func)
                params = [p.name for p in sig.parameters.values()]
            else:
                params = []

            # Get docstring
            docstring = tool.description or ""
            if hasattr(tool, 'func') and tool.func.__doc__:
                docstring = tool.func.__doc__

            return params, docstring

        except Exception as e:
            logger.error(f"Error extracting parameters from tool: {e}")
            return [], ""


async def analyze_tools_for_query(
    tools: List[Any],
    required_tool_ids: List[str],
    user_query: str,
    praxos_client: PraxosClient
) -> Dict[str, Any]:
    """
    Analyze all required tools to determine parameter resolution strategies.

    Args:
        tools: List of available tools
        required_tool_ids: IDs of tools needed for this query
        user_query: User's query
        praxos_client: PraxosClient instance

    Returns:
        Complete resolution analysis for all tools
    """
    resolver = ToolInputResolver(praxos_client)
    extractor = ToolParameterExtractor()

    resolution_context = {}

    for tool in tools:
        tool_name = tool.name if hasattr(tool, 'name') else str(tool)

        # Only analyze required tools
        if tool_name not in required_tool_ids:
            continue

        # Extract parameters and docstring
        params, docstring = extractor.extract_parameters_from_tool(tool)

        if not params:
            logger.warning(f"No parameters extracted for tool {tool_name}")
            continue

        # Analyze parameters
        analysis = await resolver.analyze_tool_parameters(
            tool_name=tool_name,
            tool_docstring=docstring,
            tool_params=params,
            user_query=user_query
        )

        resolution_context[tool_name] = {
            "analysis": analysis,
            "guidance": resolver.format_resolution_guidance(analysis),
            "auto_fill": await resolver.build_auto_fill_map(analysis)
        }

    return resolution_context
