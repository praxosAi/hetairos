"""
Tool Registry - Centralized tool metadata management.

Loads tool definitions from tool_database.yaml and provides methods to:
1. Query tool metadata
2. Generate ToolFunctionID enum
3. Generate documentation for granular_tooling_capabilities.py
4. Validate tool implementations against definitions
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


@dataclass
class ToolArgument:
    """Represents a tool argument with type and description."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum_values: Optional[List[str]] = None
    injected: bool = False  # For parameters like tool_call_id


@dataclass
class ToolDefinition:
    """Complete tool definition from YAML."""
    tool_id: str
    category: str
    display_name: str
    short_description: str
    detailed_description: str = ""
    arguments: List[ToolArgument] = None
    returns: str = ""
    examples: List[str] = None
    use_cases: List[str] = None
    notes: List[str] = None
    requires_integration: Optional[str] = None
    requires_auth: bool = False
    is_long_running: bool = False
    requires_intermediate_message: bool = False
    estimated_duration_seconds: Optional[int] = None
    supports_multi_account: bool = False
    description_template: Optional[str] = None

    def __post_init__(self):
        """Initialize default values for list fields."""
        if self.arguments is None:
            self.arguments = []
        if self.examples is None:
            self.examples = []
        if self.use_cases is None:
            self.use_cases = []
        if self.notes is None:
            self.notes = []


class ToolRegistry:
    """
    Central registry for tool metadata loaded from YAML database.

    Usage:
        registry = ToolRegistry()
        registry.load()  # Load from default path

        # Query tools
        tool = registry.get('google_search')

        # Generate artifacts
        enum_code = registry.generate_enum()
        docs = registry.generate_documentation()
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._loaded = False
        self._yaml_path: Optional[Path] = None

    def load(self, definitions_dir: str = None):
        """
        Load tools from YAML files in definitions directory.
        Scans all subdirectories and loads individual tool YAML files.

        Args:
            definitions_dir: Path to definitions directory. If None, uses default location.
        """
        if self._loaded:
            return

        if definitions_dir is None:
            definitions_dir = Path(__file__).parent / "definitions"
        else:
            definitions_dir = Path(definitions_dir)

        if not definitions_dir.exists():
            raise FileNotFoundError(f"Tool definitions directory not found: {definitions_dir}")

        # Scan all subdirectories for YAML files
        yaml_files = list(definitions_dir.glob("**/*.yaml"))

        if not yaml_files:
            raise ValueError(f"No YAML files found in {definitions_dir}")

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r') as f:
                    tool_dict = yaml.safe_load(f)

                if not tool_dict or 'tool_id' not in tool_dict:
                    print(f"⚠️  Skipping invalid YAML: {yaml_file.name}")
                    continue

                tool = self._parse_tool(tool_dict)
                self._tools[tool.tool_id] = tool

            except Exception as e:
                print(f"❌ Error loading {yaml_file.name}: {e}")

        self._loaded = True
        print(f"✓ Loaded {len(self._tools)} tools from {definitions_dir}")

        # Show category breakdown
        categories = {}
        for tool in self._tools.values():
            categories[tool.category] = categories.get(tool.category, 0) + 1

        print(f"  Categories: {', '.join(f'{cat}({count})' for cat, count in sorted(categories.items()))}")

    def _parse_tool(self, tool_dict: dict) -> ToolDefinition:
        """Parse a tool dictionary into a ToolDefinition object."""
        # Parse arguments
        arguments = []
        for arg_dict in tool_dict.get('arguments', []):
            arg = ToolArgument(
                name=arg_dict['name'],
                type=arg_dict['type'],
                description=arg_dict['description'],
                required=arg_dict.get('required', True),
                default=arg_dict.get('default'),
                enum_values=arg_dict.get('enum_values'),
                injected=arg_dict.get('injected', False)
            )
            arguments.append(arg)

        return ToolDefinition(
            tool_id=tool_dict['tool_id'],
            category=tool_dict['category'],
            display_name=tool_dict['display_name'],
            short_description=tool_dict['short_description'],
            detailed_description=tool_dict.get('detailed_description', ''),
            arguments=arguments,
            returns=tool_dict.get('returns', ''),
            examples=tool_dict.get('examples', []),
            use_cases=tool_dict.get('use_cases', []),
            notes=tool_dict.get('notes', []),
            requires_integration=tool_dict.get('requires_integration'),
            requires_auth=tool_dict.get('requires_auth', False),
            is_long_running=tool_dict.get('is_long_running', False),
            requires_intermediate_message=tool_dict.get('requires_intermediate_message', False),
            estimated_duration_seconds=tool_dict.get('estimated_duration_seconds'),
            supports_multi_account=tool_dict.get('supports_multi_account', False),
            description_template=tool_dict.get('description_template')
        )

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        """Get tool definition by ID."""
        if not self._loaded:
            self.load()
        return self._tools.get(tool_id)

    def get_all(self) -> List[ToolDefinition]:
        """Get all tool definitions."""
        if not self._loaded:
            self.load()
        return list(self._tools.values())

    def get_by_category(self, category: str) -> List[ToolDefinition]:
        """Get all tools in a specific category."""
        if not self._loaded:
            self.load()
        return [tool for tool in self._tools.values() if tool.category == category]

    def get_categories(self) -> List[str]:
        """Get list of all unique categories."""
        if not self._loaded:
            self.load()
        return sorted(list(set(tool.category for tool in self._tools.values())))

    def apply_descriptions_to_tools(self, tools: List, accounts: List[str] = None, account_param_name: str = 'account'):
        """
        Apply descriptions from YAML to tool objects at runtime.
        Handles multi-account scenarios using description templates.

        Args:
            tools: List of tool objects to update
            accounts: List of account identifiers (emails, IDs, etc.) if multi-account
            account_param_name: Name of the account parameter (default: 'account', but can be 'from_account' for some tools)

        Returns:
            The same tools list with updated descriptions
        """
        if not self._loaded:
            self.load()

        for tool in tools:
            # Get tool definition from YAML
            tool_def = self.get(tool.name)
            if not tool_def:
                # Tool not in YAML database, keep original description
                continue

            # Handle multi-account tools
            if tool_def.supports_multi_account and accounts:
                if tool_def.description_template:
                    # Generate account info string
                    if len(accounts) == 1:
                        account_info = f"Connected account: {accounts[0]}"
                    else:
                        account_list = ", ".join(f"'{acc}'" for acc in accounts)
                        account_info = (
                            f"Multiple accounts available: {account_list}. "
                            f"You MUST use the '{account_param_name}' parameter to specify which one."
                        )

                    # Apply template
                    tool.description = tool_def.description_template.format(account_info=account_info)
                else:
                    # No template, just use short description
                    tool.description = tool_def.short_description
            else:
                # Single account or no multi-account support
                tool.description = tool_def.short_description

        return tools

    def create_enum_class(self):
        """
        Create ToolFunctionID enum class dynamically at runtime.

        Returns:
            Enum class with all tool IDs as members
        """
        if not self._loaded:
            self.load()

        # Build enum members dictionary
        enum_members = {}
        for tool in self._tools.values():
            # Convert tool_id to UPPER_SNAKE_CASE for enum constant name
            const_name = tool.tool_id.upper()
            enum_members[const_name] = tool.tool_id

        # Create enum class dynamically
        ToolFunctionID = Enum('ToolFunctionID', enum_members, type=str)

        return ToolFunctionID

    def generate_enum(self) -> str:
        """
        Generate ToolFunctionID enum code for ai_service_models.py.

        Returns:
            Python code string for the enum class.
        """
        if not self._loaded:
            self.load()

        lines = []
        lines.append("# This enum is auto-generated from src/tools/tool_database.yaml")
        lines.append("# DO NOT EDIT MANUALLY - Run: python scripts/generate_tool_artifacts.py --enum")
        lines.append("")
        lines.append("class ToolFunctionID(str, Enum):")

        # Group by category
        by_category = {}
        for tool in self._tools.values():
            if tool.category not in by_category:
                by_category[tool.category] = []
            by_category[tool.category].append(tool)

        # Generate enum entries by category
        for category in sorted(by_category.keys()):
            tools = sorted(by_category[category], key=lambda t: t.tool_id)
            lines.append(f"\n    # {category.title()} tools")
            for tool in tools:
                const_name = tool.tool_id.upper()
                lines.append(f'    {const_name} = "{tool.tool_id}"')

        return "\n".join(lines)

    def generate_documentation(self) -> str:
        """
        Generate documentation for granular_tooling_capabilities.py.

        Returns:
            Markdown-formatted documentation string.
        """
        if not self._loaded:
            self.load()

        lines = []
        lines.append("# This documentation is auto-generated from src/tools/tool_database.yaml")
        lines.append("# DO NOT EDIT MANUALLY - Run: python scripts/generate_tool_artifacts.py --docs")
        lines.append("")
        lines.append("## Available Tool Functions")
        lines.append("")

        # Group by category
        by_category = {}
        for tool in self._tools.values():
            if tool.category not in by_category:
                by_category[tool.category] = []
            by_category[tool.category].append(tool)

        # Generate documentation by category
        for category in sorted(by_category.keys()):
            tools = sorted(by_category[category], key=lambda t: t.tool_id)

            # Category header
            lines.append(f"### {category.title()} Tools")
            if tools[0].requires_integration:
                lines.append(f"(requires {tools[0].requires_integration} integration)")
            lines.append("")

            # Document each tool
            for tool in tools:
                lines.append(f"**{tool.display_name}**")
                lines.append(f"- {tool.short_description}")

                # Arguments
                if tool.arguments:
                    arg_parts = []
                    for arg in tool.arguments:
                        if arg.injected:
                            continue  # Skip injected args in docs
                        arg_str = f"{arg.name} ({arg.type})"
                        if not arg.required:
                            arg_str += f", optional"
                            if arg.default is not None:
                                arg_str += f", default {arg.default}"
                        arg_parts.append(arg_str)
                    if arg_parts:
                        lines.append(f"- Args: {', '.join(arg_parts)}")

                    # Detailed argument descriptions
                    for arg in tool.arguments:
                        if arg.injected:
                            continue
                        lines.append(f"  - `{arg.name}`: {arg.description}")
                        if arg.enum_values:
                            lines.append(f"    - Valid values: {', '.join(arg.enum_values)}")

                # Returns
                if tool.returns:
                    lines.append(f"- Returns: {tool.returns}")

                # Use cases
                for use_case in tool.use_cases:
                    lines.append(f"- Use when: {use_case}")

                # Examples
                for example in tool.examples:
                    lines.append(f"- Example: {example}")

                # Notes
                for note in tool.notes:
                    lines.append(f"- Note: {note}")

                # Long running warning
                if tool.requires_intermediate_message:
                    lines.append(f"- IMPORTANT: Always use send_intermediate_message first")

                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def get_version_hash(self) -> str:
        """
        Generate a version hash for cache invalidation.
        Changes whenever tool definitions change.

        Returns:
            12-character hash string.
        """
        import hashlib
        import json

        if not self._loaded:
            self.load()

        # Create deterministic JSON representation
        tools_data = {}
        for tool_id, tool in sorted(self._tools.items()):
            tools_data[tool_id] = {
                'category': tool.category,
                'description': tool.short_description,
                'arguments': [
                    {
                        'name': arg.name,
                        'type': arg.type,
                        'required': arg.required
                    }
                    for arg in tool.arguments
                ]
            }

        json_str = json.dumps(tools_data, sort_keys=True)
        hash_obj = hashlib.sha256(json_str.encode())
        return hash_obj.hexdigest()[:12]

    def validate_tool_implementation(self, tool_id: str, actual_args: List[str]) -> bool:
        """
        Validate that a tool implementation matches its definition.

        Args:
            tool_id: The tool ID to validate
            actual_args: List of argument names from the actual function signature

        Returns:
            True if validation passes, False otherwise
        """
        tool = self.get(tool_id)
        if not tool:
            print(f"❌ Tool '{tool_id}' not found in database")
            return False

        # Get expected args (excluding injected ones)
        expected_args = [arg.name for arg in tool.arguments if not arg.injected]

        # Compare
        if set(actual_args) != set(expected_args):
            print(f"❌ Tool '{tool_id}' argument mismatch:")
            print(f"   Expected: {expected_args}")
            print(f"   Actual:   {actual_args}")
            return False

        print(f"✓ Tool '{tool_id}' validation passed")
        return True


# Global registry instance
tool_registry = ToolRegistry()


if __name__ == "__main__":
    """Test the registry."""
    registry = ToolRegistry()
    registry.load()

    print(f"\nLoaded {len(registry.get_all())} tools")
    print(f"Categories: {', '.join(registry.get_categories())}")
    print(f"Version hash: {registry.get_version_hash()}")

    # Show a sample tool
    tool = registry.get('google_search')
    if tool:
        print(f"\nSample tool: {tool.tool_id}")
        print(f"  Category: {tool.category}")
        print(f"  Description: {tool.short_description}")
        print(f"  Arguments: {[arg.name for arg in tool.arguments]}")
