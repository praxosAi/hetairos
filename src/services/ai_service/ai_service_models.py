from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

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