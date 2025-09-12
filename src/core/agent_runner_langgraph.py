import pytz
from datetime import datetime
from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from src.config.settings import settings
from src.core.context import UserContext
from src.tools.tool_factory import AgentToolsFactory
from src.services.conversation_manager import ConversationManager
from src.utils.database import db_manager
from src.services.integration_service import integration_service
from pydantic import BaseModel, Field
from src.utils.logging import setup_logger
from src.core.praxos_client import PraxosClient
from langgraph.graph import MessagesState
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chat_models import init_chat_model
import uuid
from bson import ObjectId
from src.utils.blob_utils import download_from_blob_storage_and_encode_to_base64
from src.utils.audio import convert_ogg_b64_to_wav_b64
from src.services.user_service import user_service

logger = setup_logger(__name__)

LANGUAGE_MAP = {
    'en': 'English',
    'es': 'Spanish',
    'pt': 'Portuguese',
    'fr': 'French',
    'it': 'Italian',
    'de': 'German',
    'ja': 'Japanese'
}

# --- 1. Define the Structured Output and State ---
class AgentFinalResponse(BaseModel):
    """The final structured response from the agent."""
    response: str = Field(description="The final, user-facing response to be delivered.")
    delivery_modality: str = Field(description="The channel for the response. Should be the same as the input source.", enum=["email", "whatsapp", "websocket", "telegram"])
    execution_notes: Optional[str] = Field(description="Internal notes about the execution, summarizing tool calls or errors.")

class AgentState(MessagesState):
    user_context: UserContext
    metadata: Optional[Dict[str, Any]]
    final_response: Optional[AgentFinalResponse] # To hold the structured output

# --- 2. Define the Agent Runner Class ---
class LangGraphAgentRunner:
    def __init__(self,trace_id: str, has_media: bool = False):
        
        self.tools_factory = AgentToolsFactory(config=settings, db_manager=db_manager)
        self.conversation_manager = ConversationManager(db_manager.db, integration_service)
        ### this is here to force langchain lazy importer to pre import before portkey corrupts.
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id=trace_id)
        ### note that this is not OpenAI, this is azure. we will use portkey to access OAI Azure.
        self.llm = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        if has_media:
            self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            )
        self.structured_llm = self.llm.with_structured_output(AgentFinalResponse)



    async def _get_long_term_memory(self, praxos_client: PraxosClient, input_text: str) -> List[str]:
        """Fetches long-term memory for the user from Praxos."""
        praxos_history = await praxos_client.search_memory(input_text,10)
        long_term_memory_context = ''
        for i,itm in enumerate(praxos_history['sentences']):
            long_term_memory_context += f"Context Info{i+1}: {itm}\n"
        if long_term_memory_context:
            long_term_memory_context = "\n\nThe following relevant information is known about this user from their long-term memory:\n" + long_term_memory_context
        return long_term_memory_context

    def _create_system_prompt(self, user_context: UserContext, source: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Replicates the system prompt construction from the original AgentRunner."""
        user_record = user_context.user_record
        user_record_for_context = "\n\nThe following information is known about this user of the assistant:"
        if user_record:
            if user_record.get("first_name"): user_record_for_context += f"\nFirst Name: {user_record.get('first_name')}"
            if user_record.get("last_name"): user_record_for_context += f"\nLast Name: {user_record.get('last_name')}"
            if user_record.get("email"): user_record_for_context += f"\nEmail: {user_record.get('email')}"
            if user_record.get("phone_number"): user_record_for_context += f"\nPhone Number: {user_record.get('phone_number')}"
        else:
            user_record_for_context = ""

        nyc_tz = pytz.timezone('America/New_York')
        current_time_nyc = datetime.now(nyc_tz).isoformat()

        base_prompt = (
            "You are a helpful AI assistant. Use the available tools to complete the user's request. "
            "If it's not a request, but a general conversation, just respond to the user's message. "
            "Do not mention tools if the user's final, most current request, does not require them. "
            "If the user's request requires you to do an action in the future or in a recurring manner, "
            "use the available tools to schedule the task."
            "do not confirm the scheduling with the user, just do it, unless the user specifically asks you to confirm it with them."
            "use best judgement, instead of asking the user to confirm. confirmation or clarification should only be done if absolutely necessary."
        )
        
        time_prompt = f"\nThe current time in NYC is {current_time_nyc}. You should always assume New York time (EDT/EST)."
        
        tool_output_prompt = (
            "\nThe output format of most tools will be an object containing information, including the status of the tool execution. "
            "If the execution is successful, the status will be 'success'. In cases where the tool execution is not successful, "
            "there might be a property called 'user_message' which contains an error message. This message must be relayed to the user EXACTLY as it is. "
            "Do not add any other text to the user's message in these cases. If the preferd language has been set up to something different than English, you must translate the 'user_message' message to prefered language in the unsuccessful cases."
        )


        side_effect_explanation_prompt = """ note that there is a difference between the final output delivery modality, and using tools to send a response. the tool usage for communication is to be used when the act of sending a communication is a side effect, and not the final output or goal. """
        
        task_prompt = ""
        if source in ["scheduled", "recurring"]:
            task_prompt = "\nNote: this is the command part of a previously scheduled task. You should now complete the task. If a time was previously specified, assume that now is the time to perform it."
            if metadata and metadata.get("output_type"):
                task_prompt += f" The output modality for the final response of this scheduled task was previously specified as '{metadata.get('output_type')}'."
            else:
                task_prompt += " The output modality for the final response of this scheduled task was not specified, so you should choose the most appropriate one based on the user's preferences and context. this cannot be websocket in this case."


        preferences = user_service.get_user_preferences(user_context.user_id) 
        preferences = preferences if preferences else {}
        assistance_name = preferences.get('assistant_name', 'Praxos')
        preferred_language = LANGUAGE_MAP[preferences.get('language_responses', 'en')]
        personilization_prompt = (f"\nYou are personilized to the user. User wants to call you '{assistance_name}' to get assistance. You should respond to the user's request as if you are the assistant named '{assistance_name}'."
         f"The prefered language to use is '{preferred_language}'. You must always respond in the prefered language."
        )

        return base_prompt + time_prompt + tool_output_prompt + user_record_for_context + side_effect_explanation_prompt + task_prompt + personilization_prompt

    async def _get_conversation_history(self, conversation_id: str) -> List[BaseMessage]:
        """Fetches and formats the conversation history."""
        context = await self.conversation_manager.get_conversation_context(conversation_id)
        history = []
        for msg in context.get("messages", []):
            if msg["role"] == "user":
                history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                history.append(AIMessage(content=msg["content"]))

        ## now, fetch relevant info from praxos. 


        return history

    async def _generate_file_messages(
        self,
        input_files: List[Dict],
        messages: List[BaseMessage],
        model: str = None,  # kept for backward compatibility; unused
    ) -> List[BaseMessage]:
        """Generates file messages from the input files."""
        logger.info(f"Generating file messages; current messages length: {len(messages)}")

        for file in input_files:
            ftype = file.get("type")
            blob_path = file.get("blob_path")
            mime_type = file.get("mime_type")

            if not ftype or not blob_path:
                logger.warning(f"Skipping file with missing type/blob_path: {file}")
                continue

            # Always: download file and prepare caption (if any)
            file_content_b64 = await download_from_blob_storage_and_encode_to_base64(blob_path)
            logger.info(f"Processing file entry: {file}")

            new_message_contents = []
            caption = file.get("caption")
            if caption:
                new_message_contents.append({"type": "text", "text": caption})

            # Per-type payload
            payload = None
            if ftype in {"voice", "audio", "video"}:
                
                payload = {
                    "type": "media",
                    "data": file_content_b64,
                    "mime_type": mime_type,
                }
            elif ftype == "image":
                # Use data URL for images
                payload = {
                    "type": "image_url",
                    "image_url": f"data:{mime_type};base64,{file_content_b64}",
                }
            elif ftype in {"document", "file"}:
                payload = {
                    "type": "file",
                    "source_type": "base64",
                    "mime_type": mime_type,
                    "data": file_content_b64,
                }
            else:
                logger.warning(f"Unknown file type '{ftype}'; skipping: {file}")
                continue

            message = HumanMessage(content=new_message_contents + [payload])
            messages.append(message)
            logger.info(f"Added '{ftype}' message; messages length now {len(messages)}")

        return messages
    async def run(self, user_context: UserContext, input: Dict, source: str, metadata: Optional[Dict] = None) -> AgentFinalResponse:
        execution_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        execution_record = {
            "execution_id": execution_id,
            "user_id": ObjectId(user_context.user_id),
            "trigger_type": source,
            "trigger_data": {"input": input, "metadata": metadata},
            "status": "running",
            "started_at": start_time,
        }

        await db_manager.db["execution_history"].insert_one(execution_record)      
        try:
            
            """Main entry point for the LangGraph agent runner."""
            input_text = input.get("text")
            input_files = input.get("files")
            if input_text:
                logger.info(f"Running LangGraph agent runner for user {user_context.user_id} with input {input_text} and source {source}")
            elif input_files and not input_text:
                logger.info(f"Running LangGraph agent runner for user {user_context.user_id} with input {input_files} and source {source}")
                input_text = "SYSTEM NOTE: the user sent a multimedia message. the files are attached to the message."
            tools = await self.tools_factory.create_tools(user_context, metadata)
            logger.info(f"Tools created: {tools}")
            tool_executor = ToolNode(tools)
            llm_with_tools = self.llm.bind_tools(tools)

            system_prompt = self._create_system_prompt(user_context, source, metadata)
            
            from src.config.settings import settings
            if settings.OPERATING_MODE == "local":
                praxos_api_key = settings.PRAXOS_API_KEY
            else:
                praxos_api_key = user_context.user_record.get("praxos_api_key")

            try:
                if input_text and praxos_api_key:
                    praxos_client = PraxosClient(f"env_for_{user_context.user_record.get('email')}", api_key=praxos_api_key)

                    long_term_memory_context = await self._get_long_term_memory(praxos_client, input_text)
                    if long_term_memory_context:
                        system_prompt += long_term_memory_context
            except Exception as e:
                logger.error(f"Error fetching long-term memory: {e}", exc_info=True)

            # --- Graph Definition ---
            async def call_model(state: AgentState):
                messages = state['messages']
                response = await llm_with_tools.ainvoke([("system", system_prompt)] + messages)
                return {"messages": state['messages'] + [response]}

            def should_continue(state: AgentState):
                last_message = state['messages'][-1]
                if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
                    return "end"
                else:
                    return "continue"

            async def generate_final_response(state: AgentState):
                final_message = state['messages'][-1].content
                prompt = (
                    f"Given the final response from an agent: '{final_message}', "
                    f"and knowing the initial request came from the '{source}' channel, "
                    "format this into the required JSON structure. The delivery_modality must match the source channel."
                )
                response = await self.structured_llm.ainvoke(prompt)
                return {"final_response": response}

            workflow = StateGraph(AgentState)
            workflow.add_node("agent", call_model)
            workflow.add_node("action", tool_executor)
            workflow.add_node("finalize", generate_final_response)
            
            workflow.set_entry_point("agent")
            
            workflow.add_conditional_edges(
                "agent",
                should_continue,
                {"continue": "action", "end": "finalize"}
            )
            workflow.add_edge('action', 'agent')
            workflow.add_edge('finalize', END)
            
            app = workflow.compile()
            nyc_tz = pytz.timezone('America/New_York')
            current_time_nyc = datetime.now(nyc_tz).isoformat()
            # --- Execution ---
            conversation_id = metadata.get("conversation_id") or await self.conversation_manager.get_or_create_conversation(user_context.user_id, source)
            await self.conversation_manager.add_user_message(conversation_id, 'message sent on date ' + current_time_nyc + ' by ' + user_context.user_record.get('first_name', '') + ' ' + user_context.user_record.get('last_name', '') + ': ' + input_text, metadata)
            history = await self._get_conversation_history(conversation_id)
            if input_files:
                history = await self._generate_file_messages(input_files,history,model='gemini')
            initial_state: AgentState = {
                "messages": history,
                "user_context": user_context,
                "metadata": metadata,
                "final_response": None
            }

            final_state = await app.ainvoke(initial_state)
            
            final_response = final_state['final_response']
            await self.conversation_manager.add_assistant_message(conversation_id, final_response.response)

            return final_response

        except Exception as e:
            logger.error(f"Error during agent run {execution_id}: {e}", exc_info=True)
            execution_record["status"] = "failed"
            execution_record["error_message"] = str(e)
            return AgentFinalResponse(response="I'm sorry, I'm having trouble processing your request. Please try again later.", delivery_modality=source, execution_notes=str(e))

        finally:
            execution_record["completed_at"] = datetime.utcnow()
            execution_record["duration_seconds"] = (execution_record["completed_at"] - start_time).total_seconds()
            await db_manager.db["execution_history"].update_one(
                {"execution_id": execution_id},
                {"$set": execution_record}
            )