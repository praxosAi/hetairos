#!/usr/bin/env python3
"""
Generate tool artifacts from tool_database.yaml.

This script reads the central tool database and generates:
1. ToolFunctionID enum in ai_service_models.py
2. Tool documentation in granular_tooling_capabilities.py
3. (Optional) Regenerates Gemini cache

Usage:
    python scripts/generate_tool_artifacts.py --enum        # Generate enum only
    python scripts/generate_tool_artifacts.py --docs        # Generate docs only
    python scripts/generate_tool_artifacts.py --cache       # Regenerate cache only
    python scripts/generate_tool_artifacts.py --all         # Generate all
    python scripts/generate_tool_artifacts.py --validate    # Validate tools
"""

import sys
from pathlib import Path
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.tool_registry import tool_registry


def generate_enum(output_path: Path = None):
    """Generate ToolFunctionID enum as a clean Python file."""
    if output_path is None:
        output_path = project_root / "src/services/ai_service/tool_enums_generated.py"

    print(f"Generating ToolFunctionID enum...")

    # Generate enum code
    enum_code = tool_registry.generate_enum()

    # Create complete Python file
    file_content = f'''"""
Auto-generated tool enum from YAML definitions.
DO NOT EDIT - Run: python scripts/generate_tool_artifacts.py --enum

Generated from: src/tools/definitions/
Tool count: {len(tool_registry.get_all())}
Version hash: {tool_registry.get_version_hash()}
"""

from enum import Enum

{enum_code}
'''

    # Write clean file
    output_path.write_text(file_content)
    print(f"✓ Generated ToolFunctionID enum in {output_path}")
    print(f"  Total tools: {len(tool_registry.get_all())}")
    return True


def generate_documentation(output_path: Path = None):
    """Generate tool documentation as a clean Python string constant."""
    if output_path is None:
        output_path = project_root / "src/services/ai_service/prompts/tool_docs_generated.py"

    print(f"Generating tool documentation...")

    # Generate documentation
    docs = tool_registry.generate_documentation()

    # Create complete Python file with string constant
    file_content = f'''"""
Auto-generated tool documentation from YAML definitions.
DO NOT EDIT - Run: python scripts/generate_tool_artifacts.py --docs

Generated from: src/tools/definitions/
Tool count: {len(tool_registry.get_all())}
Version hash: {tool_registry.get_version_hash()}
"""

TOOL_DOCUMENTATION = """
{docs}
"""
'''

    # Write clean file
    output_path.write_text(file_content)
    print(f"✓ Generated documentation in {output_path}")
    print(f"  Total tools documented: {len(tool_registry.get_all())}")
    return True


def regenerate_cache():
    """Regenerate Gemini cache with updated tool documentation."""
    print(f"Regenerating Gemini cache...")

    try:
        from src.services.ai_service.prompts import caches
        # Import the cache regeneration function if available
        # This is a placeholder - implement based on your cache system

        version_hash = tool_registry.get_version_hash()
        print(f"  Tool database version: {version_hash}")

        # TODO: Implement cache regeneration
        # cache_id = caches.regenerate_planning_cache()
        # print(f"✓ Cache regenerated: {cache_id}")

        print(f"⚠️  Cache regeneration not yet implemented")
        print(f"   Manual step required: Regenerate Gemini cache with new tool docs")
        return True

    except Exception as e:
        print(f"❌ Error regenerating cache: {e}")
        return False


def validate_tools():
    """Validate that tool implementations match their definitions."""
    print(f"Validating tool implementations...")

    # This is a basic validation - can be expanded to inspect actual tool files
    tools = tool_registry.get_all()

    print(f"\nValidation Summary:")
    print(f"  Total tools defined: {len(tools)}")
    print(f"  Categories: {', '.join(tool_registry.get_categories())}")

    # Check for tools with no arguments
    no_args_tools = [t for t in tools if not t.arguments]
    if no_args_tools:
        print(f"\n  Tools with no arguments: {len(no_args_tools)}")
        for tool in no_args_tools[:5]:
            print(f"    - {tool.tool_id}")

    # Check for long-running tools
    long_running = [t for t in tools if t.is_long_running]
    if long_running:
        print(f"\n  Long-running tools: {len(long_running)}")
        for tool in long_running:
            print(f"    - {tool.tool_id} (~{tool.estimated_duration_seconds}s)")

    # Check for tools requiring auth
    auth_required = [t for t in tools if t.requires_auth]
    print(f"\n  Tools requiring auth: {len(auth_required)}")

    # Check for multi-account support
    multi_account = [t for t in tools if t.supports_multi_account]
    if multi_account:
        print(f"\n  Multi-account tools: {len(multi_account)}")
        for tool in multi_account:
            print(f"    - {tool.tool_id}")

    print(f"\n✓ Validation complete")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Generate tool artifacts from tool_database.yaml'
    )
    parser.add_argument('--enum', action='store_true',
                       help='Generate ToolFunctionID enum')
    parser.add_argument('--docs', action='store_true',
                       help='Generate tool documentation')
    parser.add_argument('--cache', action='store_true',
                       help='Regenerate Gemini cache')
    parser.add_argument('--validate', action='store_true',
                       help='Validate tool definitions')
    parser.add_argument('--all', action='store_true',
                       help='Generate all artifacts')

    args = parser.parse_args()

    # Load the tool registry
    print("Loading tool database...")
    tool_registry.load()
    print()

    # Determine what to do
    if not any([args.enum, args.docs, args.cache, args.validate, args.all]):
        parser.print_help()
        return

    success = True

    if args.all or args.validate:
        success &= validate_tools()
        print()

    if args.all or args.enum:
        success &= generate_enum()
        print()

    if args.all or args.docs:
        success &= generate_documentation()
        print()

    if args.all or args.cache:
        success &= regenerate_cache()
        print()

    if success:
        print("✓ All operations completed successfully")
        sys.exit(0)
    else:
        print("❌ Some operations failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
