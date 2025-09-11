from typing import Any, Optional
from pydantic import BaseModel

class ToolExecutionResponse(BaseModel):
    status: str
    user_message: Optional[str] = None
    result: Optional[Any] = None
    system_error: Optional[str] = None
