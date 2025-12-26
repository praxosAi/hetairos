import os
import yaml
from pathlib import Path

# Constants
TOOL_DEFINITIONS_DIR = Path("src/tools/definitions")
USER_GUIDES_DIR = Path("docs/user_guides")

def load_tool_definition(file_path):
    """Load and parse a YAML tool definition file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def generate_user_guide_content(tool_def):
    """Generate user-facing documentation from tool definition."""
    if not tool_def:
        return None
    
    display_name = tool_def.get('display_name', tool_def.get('tool_id', 'Unknown Tool'))
    description = tool_def.get('short_description', 'No description available.')
    detailed_desc = tool_def.get('detailed_description', '').strip()
    use_cases = tool_def.get('use_cases', [])
    examples = tool_def.get('examples', [])
    
    # Template
    content = f"# {display_name}\n\n"
    content += f"## What is it?\n{description}\n\n"
    
    if detailed_desc:
        content += f"## Details\n{detailed_desc}\n\n"
        
    if use_cases:
        content += "## When to use this?\n"
        for use_case in use_cases:
            content += f"- {use_case}\n"
        content += "\n"
        
    if examples:
        content += "## Examples of requests\n"
        for ex in examples:
            # Clean up example if it's code-like
            if '(' in ex and ')' in ex:
                 # Try to make it look like a user request if possible, 
                 # but for now just listing the example as is or wrapped
                 content += f"- `{ex}`\n"
            else:
                 content += f"- {ex}\n"
    
    content += "\n---\n"
    content += f"**Tool ID:** `{tool_def.get('tool_id')}`\n"
    
    return content

def main():
    """Main execution function."""
    if not TOOL_DEFINITIONS_DIR.exists():
        print(f"Definitions directory not found: {TOOL_DEFINITIONS_DIR}")
        return

    # Create output directory
    USER_GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    
    count = 0
    # Walk through definitions
    for root, _, files in os.walk(TOOL_DEFINITIONS_DIR):
        for file in files:
            if file.endswith('.yaml') and not file.startswith('_'):
                file_path = Path(root) / file
                tool_def = load_tool_definition(file_path)
                
                if tool_def:
                    content = generate_user_guide_content(tool_def)
                    if content:
                        # Save to user guides
                        # We use flat structure or preserve category? 
                        # Flat with category prefix is easier for simple searching
                        category = tool_def.get('category', 'general')
                        tool_id = tool_def.get('tool_id', Path(file).stem)
                        output_filename = f"{category}_{tool_id}.md"
                        output_path = USER_GUIDES_DIR / output_filename
                        
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        count += 1
                        print(f"Generated guide for: {tool_id}")

    print(f"\nSuccessfully generated {count} user guides in {USER_GUIDES_DIR}")

if __name__ == "__main__":
    main()
