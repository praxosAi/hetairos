from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

# Create ToolFunctionID enum dynamically at runtime from YAML
from src.tools.tool_registry import tool_registry
tool_registry.load()  # Load YAML definitions (happens once at module import)
ToolFunctionID = tool_registry.create_enum_class()  # Create enum dynamically

class BooleanResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the boolean response.")
    response: bool = Field(..., description="A boolean response indicating true or false.")


class StringResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the string response.")
    response: str = Field(..., description="A string response.")

class PlanningResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the planning response.")
    query_type: str = Field(..., description="The type of query: namely, 'command' or 'conversational'.",enum=['command', 'conversational'])
    tooling_need: bool = Field(..., description="Indicates whether external tools are needed to achieve the goal.")
    plan: str = Field(..., description="A detailed plan outlining the steps to achieve the goal, IF it's a command and tooling is needed.")
    steps: List[str] = Field(..., description="A list of actionable steps derived from the plan. Each step should be concise and clear. Not needed if it's a conversational query without tooling.")

class GranularPlanningResponse(BaseModel):
    """Enhanced planning response with specific tool function IDs."""
    reason: str = Field(..., description="A short reason for the planning decision.")
    query_type: str = Field(..., description="The type of query: 'command' or 'conversational'.", enum=['command', 'conversational'])
    tooling_need: bool = Field(False, description="Indicates whether external tools are needed.")
    required_tools: List[ToolFunctionID] = Field(
        default_factory=list,
        description="Specific tool function IDs required for this task. Only include tools that are ACTUALLY needed. Be precise and minimal."
    )
    missing_data_for_tools: Optional[bool] = Field(False, description="Indicates if any required data for the tools is missing.")
    plan: Optional[str] = Field(None, description="A detailed plan outlining the steps, if needed.")
    steps: Optional[List[str]] = Field(default_factory=list, description="Actionable steps for the task.")

