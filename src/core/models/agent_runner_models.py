from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from src.core.context import UserContext
class FileLink(BaseModel):
    url: str = Field(description="URL to the file.")
    file_type: Optional[str] = Field(description="Type of the file, e.g., image, document, etc.", enum=["image", "document", "audio", "video","other_file"])
    file_name: Optional[str] = Field(description=" name of the file, if available. if not, come up with a descriptive name based on the content of the file.")
class AgentFinalResponse(BaseModel):
    """The final structured response from the agent."""
    response: str = Field(description="The final, user-facing response to be delivered.")
    execution_notes: Optional[str] = Field(description="Internal notes about the execution, summarizing tool calls or errors.")

    delivery_platform: str = Field(description="The channel for the response. Should be the same as the input source, unless otherwise specified.", enum=["email", "whatsapp", "websocket", "telegram",'imessage','slack','discord'])
    output_modality: Optional[str] = Field(description="The modality of the output, e.g., text, image, file, etc. unless otherwise specified by user needs, this should be text", enum=["text", "voice", 'audio', "image", "video",'file'])
    generation_instructions: Optional[str] = Field(description="Instructions for generating audio, video, or image if applicable.")
    file_links: Optional[List[FileLink]] = Field(description="Links to any files generated or used in the response.")
    class Config:
        extra = "forbid"
        arbitrary_types_allowed = True

class AgentState(MessagesState):
    user_context: UserContext
    metadata: Optional[Dict[str, Any]]
    final_response: Optional[AgentFinalResponse] # To hold the structured output
    tool_iter_counter: int
    data_iter_counter: int
    param_probe_done: bool  # has obtain_data been executed?