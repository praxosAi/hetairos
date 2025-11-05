#!/usr/bin/env python3
"""
Script to generate remaining YAML tool definition files.
This script creates YAML files for all remaining tools that haven't been migrated yet.
"""

import os
from pathlib import Path

BASE_DIR = Path("/Users/mohammadsoheilsadabadi/praxos-reboot/hetairos/src/tools/definitions")

# Define all remaining tools to migrate
TOOLS_TO_CREATE = {
    "media_bus": [
        {
            "tool_id": "list_available_media",
            "category": "media_bus",
            "short_description": "List media items currently available in this conversation",
            "detailed_description": """List media items currently available in this conversation.
  This tool shows all media that has been generated or received during the current conversation.
  Use this to see what media exists that you can reference or build upon.""",
            "arguments": [
                {"name": "media_type", "type": "str", "description": "Optional filter by type - 'image', 'audio', 'video', or 'document'", "required": False},
                {"name": "limit", "type": "int", "description": "Maximum number of items to return (default 10, max 50)", "required": False, "default": 10}
            ],
            "returns": "ToolExecutionResponse with formatted string describing available media",
            "examples": ["list_available_media(media_type='image')", "list_available_media()"],
            "use_cases": ["Check what images were generated", "See all recent media", "Get specific media details"],
            "requires_integration": "media_bus",
            "requires_auth": False
        },
        {
            "tool_id": "get_media_by_id",
            "category": "media_bus",
            "short_description": "Retrieve a specific media item by its ID and load it into conversation context",
            "detailed_description": """Retrieve a specific media item by its ID and load it into conversation context.
  This tool retrieves media from the media bus and adds it to the current conversation context,
  allowing you to see and reason about it. After calling this tool, the media will be visible to you.""",
            "arguments": [
                {"name": "media_id", "type": "str", "description": "The unique ID of the media item (from list_available_media)", "required": True}
            ],
            "returns": "Dictionary with 'url', 'file_name', 'file_type', 'description', and 'source'",
            "examples": ['get_media_by_id("550e8400-e29b-41d4-a716-446655440000")'],
            "use_cases": ["Reference and analyze previously generated media", "Create variations based on existing media", "Send previously generated media to user"],
            "requires_integration": "media_bus",
            "requires_auth": False
        },
        {
            "tool_id": "get_recent_images",
            "category": "media_bus",
            "short_description": "Get recently generated or uploaded images",
            "detailed_description": """Get recently generated or uploaded images.
  Quick access to recent images without needing to filter the full list.
  Useful for referencing previous images or creating variations.""",
            "arguments": [
                {"name": "limit", "type": "int", "description": "Maximum number of images to return (default 5, max 20)", "required": False, "default": 5}
            ],
            "returns": "ToolExecutionResponse with formatted string of image IDs, descriptions, and URLs",
            "examples": ["get_recent_images(limit=3)"],
            "use_cases": ["See what images exist", "Use descriptions in new prompts", "Create variations of recent images"],
            "requires_integration": "media_bus",
            "requires_auth": False
        }
    ],
    "google_calendar": [
        {
            "tool_id": "get_calendar_events",
            "category": "google_calendar",
            "short_description": "Fetches events from the user's Google Calendar within a specified time window",
            "arguments": [
                {"name": "time_min", "type": "datetime", "description": "Start of time window", "required": True},
                {"name": "time_max", "type": "datetime", "description": "End of time window", "required": True},
                {"name": "max_results", "type": "int", "description": "Maximum number of events to return", "required": False, "default": 10},
                {"name": "calendar_id", "type": "str", "description": "Calendar ID (default 'primary')", "required": False, "default": "primary"},
                {"name": "account", "type": "str", "description": "Account email for multi-account users", "required": False}
            ],
            "returns": "List of calendar events or empty message",
            "examples": ["get_calendar_events(datetime(2025, 11, 5), datetime(2025, 11, 10))"],
            "requires_integration": "google_calendar",
            "requires_auth": True,
            "supports_multi_account": True,
            "description_template": "Fetches events from Google Calendar. {account_info}"
        },
        {
            "tool_id": "create_calendar_event",
            "category": "google_calendar",
            "short_description": "Creates a new event on the user's Google Calendar",
            "arguments": [
                {"name": "title", "type": "str", "description": "Event title/summary", "required": True},
                {"name": "start_time", "type": "datetime", "description": "Start time as datetime object", "required": True},
                {"name": "end_time", "type": "datetime", "description": "End time as datetime object", "required": True},
                {"name": "attendees", "type": "list", "description": "List of attendee email addresses", "required": False, "default": []},
                {"name": "description", "type": "str", "description": "Event description", "required": False, "default": ""},
                {"name": "location", "type": "str", "description": "Event location", "required": False, "default": ""},
                {"name": "calendar_id", "type": "str", "description": "Calendar ID (default 'primary')", "required": False, "default": "primary"},
                {"name": "account", "type": "str", "description": "Account email for multi-account users", "required": False},
                {"name": "recurrence_rule", "type": "str", "description": "Optional RRULE string for recurring events (RFC 5545 format). Examples: 'FREQ=DAILY;COUNT=5', 'FREQ=WEEKLY;BYDAY=MO,WE,FR'", "required": False}
            ],
            "returns": "Success status and event link",
            "examples": ['create_calendar_event("Team Meeting", start_time, end_time)', 'create_calendar_event("Daily Standup", start_time, end_time, recurrence_rule="FREQ=DAILY;COUNT=30")'],
            "requires_integration": "google_calendar",
            "requires_auth": True,
            "supports_multi_account": True
        }
    ]
}

def create_yaml_content(tool):
    """Create YAML content from tool dictionary."""
    yaml_lines = []

    # Required fields
    yaml_lines.append(f"tool_id: {tool['tool_id']}")
    yaml_lines.append(f"category: {tool['category']}")
    yaml_lines.append(f"display_name: {tool['tool_id']}")
    yaml_lines.append(f"short_description: {tool['short_description']}")

    # Optional detailed description
    if "detailed_description" in tool:
        yaml_lines.append("\ndetailed_description: |")
        for line in tool['detailed_description'].split('\n'):
            yaml_lines.append(f"  {line}")

    # Arguments
    if "arguments" in tool:
        yaml_lines.append("\narguments:")
        for arg in tool['arguments']:
            yaml_lines.append(f"  - name: {arg['name']}")
            yaml_lines.append(f"    type: {arg['type']}")
            yaml_lines.append(f"    description: {arg['description']}")
            yaml_lines.append(f"    required: {str(arg['required']).lower()}")
            if "default" in arg:
                default = arg['default']
                if isinstance(default, str):
                    yaml_lines.append(f"    default: {default}")
                elif isinstance(default, list):
                    yaml_lines.append(f"    default: {default}")
                else:
                    yaml_lines.append(f"    default: {default}")

    # Returns
    if "returns" in tool:
        yaml_lines.append(f"\nreturns: {tool['returns']}")

    # Examples
    if "examples" in tool:
        yaml_lines.append("\nexamples:")
        for example in tool['examples']:
            yaml_lines.append(f"  - '{example}'")

    # Use cases
    if "use_cases" in tool:
        yaml_lines.append("\nuse_cases:")
        for use_case in tool['use_cases']:
            yaml_lines.append(f"  - {use_case}")

    # Notes
    if "notes" in tool:
        yaml_lines.append("\nnotes:")
        for note in tool['notes']:
            yaml_lines.append(f"  - {note}")

    # Integration requirements
    if "requires_integration" in tool:
        yaml_lines.append(f"\nrequires_integration: {tool['requires_integration']}")
    if "requires_auth" in tool:
        yaml_lines.append(f"requires_auth: {str(tool['requires_auth']).lower()}")

    # Multi-account support
    if "supports_multi_account" in tool:
        yaml_lines.append(f"supports_multi_account: {str(tool['supports_multi_account']).lower()}")
    if "description_template" in tool:
        yaml_lines.append(f"description_template: \"{tool['description_template']}\"")

    # Performance
    if "is_long_running" in tool:
        yaml_lines.append(f"is_long_running: {str(tool['is_long_running']).lower()}")
    if "requires_intermediate_message" in tool:
        yaml_lines.append(f"requires_intermediate_message: {str(tool['requires_intermediate_message']).lower()}")
    if "estimated_duration_seconds" in tool:
        yaml_lines.append(f"estimated_duration_seconds: {tool['estimated_duration_seconds']}")

    return "\n".join(yaml_lines) + "\n"

def main():
    """Generate all YAML files."""
    created_count = 0

    for category, tools in TOOLS_TO_CREATE.items():
        # Create category directory
        category_dir = BASE_DIR / category
        category_dir.mkdir(parents=True, exist_ok=True)

        for tool in tools:
            yaml_path = category_dir / f"{tool['tool_id']}.yaml"
            yaml_content = create_yaml_content(tool)

            with open(yaml_path, 'w') as f:
                f.write(yaml_content)

            print(f"Created: {yaml_path}")
            created_count += 1

    print(f"\nTotal YAML files created: {created_count}")

if __name__ == "__main__":
    main()
