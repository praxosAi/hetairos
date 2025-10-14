import pytz
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple,Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage,ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
import json
from src.tools.tool_types import ToolExecutionResponse
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from src.config.settings import settings
from src.core.context import UserContext
from src.tools.tool_factory import AgentToolsFactory
from src.services.conversation_manager import ConversationManager
from src.utils.database import db_manager
from src.services.integration_service import integration_service
from pydantic import BaseModel, Field
from src.utils.logging import setup_logger
from src.core.praxos_client import PraxosClient
from src.core.models.agent_runner_models import AgentFinalResponse, AgentState, FileLink,GraphConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chat_models import init_chat_model
import uuid
from src.core.prompts.system_prompt import create_system_prompt
from bson import ObjectId
from src.utils.blob_utils import download_from_blob_storage_and_encode_to_base64, upload_json_to_blob_storage,get_blob_sas_url
from src.services.user_service import user_service
from src.services.ai_service.ai_service import ai_service
from src.core.callbacks.ToolMonitorCallback import ToolMonitorCallback
from src.core.nodes import call_model, generate_final_response, obtain_data, should_continue_router

from src.utils.file_msg_utils import generate_file_messages,get_conversation_history,process_media_output, generate_user_messages_parallel,update_history
logger = setup_logger(__name__)




class LangGraphAgentRunner:
    def __init__(self,trace_id: str, has_media: bool = False,override_user_id: Optional[str] = None):
        
        self.tools_factory = AgentToolsFactory(config=settings, db_manager=db_manager)
        self.conversation_manager = ConversationManager(db_manager.db, integration_service)
        self.trace_id = trace_id
        ### this is here to force langchain lazy importer to pre import before portkey corrupts.
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id=trace_id)
        ### note that this is not OpenAI, this is azure. we will use portkey to access OAI Azure.
        self.llm = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        ### temporary, investigating refusals.
        self.media_llm =ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            )
        
        self.fast_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
            thinking_budget=0
            )
        self.llm = self.media_llm
        
        # else:
        #     logger.info("Using GPT-5 Mini for admin user logging")
        if has_media:
            self.llm = self.media_llm   
        self.structured_llm = self.fast_llm.with_structured_output(AgentFinalResponse)



    async def _get_long_term_memory(self, praxos_client: PraxosClient, input_text: str) -> List[str]:
        """Fetches long-term memory for the user from Praxos."""
        praxos_history = await praxos_client.search_memory(input_text,10)
        long_term_memory_context = ''
        for i,itm in enumerate(praxos_history['sentences']):
            long_term_memory_context += f"Context Info{i+1}: {itm}\n"
        if long_term_memory_context:
            long_term_memory_context = "\n\nThe following relevant information is known about this user from their long-term memory:\n" + long_term_memory_context
        return long_term_memory_context


    
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
            ### here's what I'll do. first of all, some methods do need a flattened text input. so even in the list case, we'll generate it.
            if isinstance(input, list):
                ### this is not really the best way to do it, but for now, we'll just concatenate all text parts.
                input_text = " ".join([item.get("text", "") for item in input if item.get("text")])
                input_files = [item.get("files", []) for item in input if item.get("files")]
                input_files = [file for sublist in input_files for file in sublist]  # flatten list of lists
                all_forwarded = all([item.get("metadata", {}).get("forwarded", False) for item in input if item.get("metadata")])
            else:
                input_text = input.get("text")
                input_files = input.get("files")
                all_forwarded = input.get("metadata", {}).get("forwarded", False)
            if input_text:
                logger.info(f"Running LangGraph agent runner for user {user_context.user_id} with input {input_text} and source {source}")

            # --- Data preparation ---
            conversation_id = metadata.get("conversation_id") or await self.conversation_manager.get_or_create_conversation(user_context.user_id, source, input)
            metadata['conversation_id'] = conversation_id
            # Get conversation history first (before adding new messages)
            history, has_media = await get_conversation_history(conversation_manager=self.conversation_manager, conversation_id=conversation_id)

            


                  
            user_preferences = user_service.get_user_preferences(user_context.user_id)    
            timezone_name = user_preferences.get('timezone', 'America/New_York') if user_preferences else 'America/New_York'
            user_tz = pytz.timezone(timezone_name)
            current_time_user = datetime.now(user_tz).isoformat()
            # Process input based on type
            if isinstance(input, list):
                # Grouped messages - use the parallel method
                base_message_prefix = f'message sent on date {current_time_user} by {user_context.user_record.get("first_name", "")} {user_context.user_record.get("last_name", "")}: '
                history, has_media = await generate_user_messages_parallel(
                    conversation_manager=self.conversation_manager, 
                    input_messages=input,
                    messages=history, 
                    conversation_id=conversation_id,
                    base_message_prefix=base_message_prefix,
                    user_context=user_context
                )
            elif isinstance(input, dict):
                # Single message - existing logic
                message_prefix = f'message sent on date {current_time_user} by {user_context.user_record.get("first_name", "")} {user_context.user_record.get("last_name", "")}: '
                if input_text:
                    ### filter out flags, empty text, etc.
                    input_text = input_text.replace('/START_NEW','').replace('/start_new','').strip()
                    if not input_text:
                        input_text = "The user sent a message with no text. if there are also no files, indicate that the user sent an empty message."
                    await self.conversation_manager.add_user_message(user_context.user_id, conversation_id, message_prefix + input_text, metadata)
                    history.append(HumanMessage(content=message_prefix + input_text))
                
                # Handle files for single message
                if input_files:
                    history = await generate_file_messages(
                        conversation_manager=self.conversation_manager,
                        input_files=input_files, 
                        messages=history, 
                        conversation_id=conversation_id,
                        message_prefix=message_prefix
                    )
            else:
                return AgentFinalResponse(response="Invalid input format.", delivery_platform=source, execution_notes="Input must be a dict or list of dicts.", output_modality="text", file_links=[], generation_instructions=None)            


            if has_media:
                logger.info(f"Conversation {conversation_id} has media; switching to media-capable LLM")
                self.llm = self.media_llm

            
            if all_forwarded:
                logger.info("All input messages are forwarded; verify with the user before taking actions.")
                return AgentFinalResponse(response="It looks like all the messages you sent were forwarded messages. Should I interpret this as a direct request to me? Awaiting confirmation.", delivery_platform=source, execution_notes="All input messages were marked as forwarded.", output_modality="text", file_links=[], generation_instructions=None)

            # Use granular planning to determine exact tools needed
            plan = None
            required_tool_ids = None
            plan_str = ''
            if source in ['scheduled','recurring','triggered']:
                ### here, we add an AI Message that indicates the scheduled nature of the request.
                if source == 'scheduled':
                    schedule_msg = AIMessage(content=f"NOTE: This command was previously scheduled. The user scheduled this command to happen now. I must now perform the requested actions. I should not ask the user for confirmation. if the request was of form 'remind me to ...', I should interpret this as a command to send the user a message now, and not set up a future reminder.")
                if source == 'recurring':
                    schedule_msg = AIMessage(content=f"NOTE: This command was previously set to recur. The user set this command to recur, and this moment is one of the times it must be performed. I must now perform the requested actions. I should not ask the user for confirmation. if the request was of form 'remind me to ...', I should interpret this as a command to send the user a message now, and not set up a future reminder.")
                if source == 'triggered':
                    schedule_msg = AIMessage(content=f"NOTE: This command was previously set to be triggered by an event. The triggering event has now occurred, and I must perform the requested actions. I should not ask the user for confirmation. if the request was of form 'if X happens, remind me to ...', I should interpret this as a command to send the user a message now, and not set up a future reminder.")
                history.append(schedule_msg)
            try:
                plan, required_tool_ids, plan_str = await ai_service.granular_planning(history)
            except Exception as e:
                logger.error(f"Error during granular planning call: {e}", exc_info=True)
                required_tool_ids = None  # Fallback to loading all tools

            tools = await self.tools_factory.create_tools(
                user_context,
                metadata,
                timezone_name,
                request_id=self.trace_id,
                required_tool_ids=required_tool_ids
            )
            logger.info(f"Loaded {len(tools)} tools based on planning")
            minimal_tools = True
            if required_tool_ids is not None and len(required_tool_ids) > 0:
                minimal_tools = False
            tool_executor = ToolNode(tools)
            llm_with_tools = self.llm.bind_tools(tools)
            tool_descriptions = ""
            for i, tool in enumerate(tools):
                try:
                    tool_descriptions += f"{tool.name}: {tool.description}\n"
                except Exception as e:
                    logger.error(f"Error getting description for tool: {e}, for tool {str(tool)}", exc_info=True)
                    continue
            system_prompt = create_system_prompt(user_context, source, metadata, tool_descriptions, plan)

            workflow = StateGraph(AgentState)
            workflow.add_node("agent", call_model)
            workflow.add_node("router", should_continue_router)
            workflow.add_node("obtain_data", obtain_data)   # NEW
            workflow.add_node("action", tool_executor)
            workflow.add_node("finalize", generate_final_response)

            workflow.set_entry_point("agent")
            workflow.add_edge("agent", "router")
            workflow.add_edge("obtain_data", "action")  # obtain_data always drives a single tool turn
            workflow.add_edge("action", "agent")
            workflow.add_edge("finalize", END)


                        
            app = workflow.compile()
            
            graph_config = GraphConfig(
                llm_with_tools=llm_with_tools,
                structured_llm=self.structured_llm,
                system_prompt=system_prompt,
                initial_state_len=len(history),
                plan_str=plan_str,
                required_tool_ids=required_tool_ids,
                minimal_tools=minimal_tools,
                source=source,
                input_text=input_text
            )
            initial_state: AgentState = {
                "messages": history,
                "user_context": user_context,
                "metadata": metadata,
                "final_response": None,
                "tool_iter_counter": 0,
                "data_iter_counter": 0,
                "param_probe_done": False,
                "config": graph_config,
            }
            # --- END Graph Definition ---

            # Create tool monitoring callback
            tool_monitor = ToolMonitorCallback(
                user_id=user_context.user_id,
                execution_id=execution_id
            )

            final_state = await app.ainvoke(
                initial_state,
                {
                    "recursion_limit": 100,
                    "callbacks": [tool_monitor],
                    "tool_iter_counter": 0,
                }
            )

            # Persist only NEW intermediate messages from this execution
            new_messages = final_state['messages'][len(initial_state['messages']):]

            await update_history( conversation_manager=self.conversation_manager, new_messages=new_messages, conversation_id=conversation_id, user_context=user_context, final_state=final_state)
            final_response = final_state['final_response']
            output_blobs = []
            await self.conversation_manager.add_assistant_message(user_context.user_id, conversation_id, final_response.response)
            logger.info(f"Final response generated for execution {execution_id}: {final_response.model_dump_json(indent=2)}")
            final_response = await process_media_output(conversation_manager=self.conversation_manager, final_response=final_response, user_context=user_context, source=source, conversation_id=conversation_id)
            execution_record["status"] = "completed"
            try:
                messages_dictified = [msg.dict() for msg in final_state['messages']]
                await upload_json_to_blob_storage(messages_dictified, f"states/test_state_messages_{execution_id}.json")
            except Exception as e:
                logger.error(f"Error uploading state messages to blob storage: {e}", exc_info=True)
            return final_response

        except Exception as e:
            logger.error(f"Error during agent run {execution_id}: {e}", exc_info=True)
            execution_record["status"] = "failed"
            execution_record["error_message"] = str(e)
            return AgentFinalResponse(response="I'm sorry, I'm having trouble processing your request. Please try again later.", delivery_platform=source, execution_notes=str(e), output_modality="text", file_links=[], generation_instructions=None)

        finally:
            execution_record["completed_at"] = datetime.utcnow()
            execution_record["duration_seconds"] = (execution_record["completed_at"] - start_time).total_seconds()
            await db_manager.db["execution_history"].update_one(
                {"execution_id": execution_id},
                {"$set": execution_record}
            )