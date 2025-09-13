from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class BooleanResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the boolean response.")
    response: bool = Field(..., description="A boolean response indicating true or false.")


class StringResponse(BaseModel):
    reason: str = Field(..., description="a short reason for the string response.")
    response: str = Field(..., description="A string response.")