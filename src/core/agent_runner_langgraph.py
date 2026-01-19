import pytz
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple,Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage,ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
import json
from langgraph.prebuilt import ToolNode
from src.config.settings import settings
from src.core.context import UserContext
from src.tools.tool_factory import AgentToolsFactory
from src.services.conversation_manager import ConversationManager
from src.utils.database import db_manager
from src.services.integration_service import integration_service
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
# from src.core.callbacks.ToolMonitorCallback import ToolMonitorCallback
from src.core.callbacks.ImmediatePersistenceCallback import ImmediatePersistenceCallback
from src.core.nodes import call_model, generate_final_response, obtain_data, should_continue_router
from src.utils.file_msg_utils import generate_file_messages,get_conversation_history,process_media_output, generate_user_messages_parallel,update_history
logger = setup_logger(__name__)


def extract_text_from_chunk(content: Any) -> str:
    """Extract plain text from various message chunk content formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "".join(text_parts)
    return str(content) if content is not None else ""


def extract_thinking_from_chunk(chunk: Any) -> str:
    """Extract thinking/reasoning from chunk."""
    # Handle OpenAI/Azure reasoning content if available
    if hasattr(chunk, 'additional_kwargs'):
        thought = chunk.additional_kwargs.get("thought")
        if thought:
            return thought
            
    # Handle Gemini 2.0 Thinking format
    content = chunk.content
    if isinstance(content, list):
        thinking_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "thought":
                thinking_parts.append(part.get("thought", ""))
            # Some versions might use 'reasoning' or just a different dict key
            elif isinstance(part, dict) and part.get("type") == "reasoning":
                thinking_parts.append(part.get("reasoning", ""))
        return "".join(thinking_parts)
    
    # Check for dedicated reasoning_content field (newer LangChain)
    if hasattr(chunk, 'reasoning_content') and chunk.reasoning_content:
        return chunk.reasoning_content
        
    return ""


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
        # self.media_llm = self.llm
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


    
    async def run(self, user_context: UserContext, input: Dict, source: str, metadata: Optional[Dict] = None, stream_buffer: Optional['StreamBuffer'] = None) -> AgentFinalResponse:
        # Default to no-op buffer if not provided
        if stream_buffer is None:
            from src.core.stream_buffer import NoOpStreamBuffer
            stream_buffer = NoOpStreamBuffer()

        # Store buffer as instance variable for use throughout execution
        self.stream_buffer = stream_buffer

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

            from_message_prefix = "from " + source if source not in ["scheduled", "recurring", "triggered"] else ""
            message_prefix = f'message sent on date {current_time_user} by {user_context.user_record.get("first_name", "")} {user_context.user_record.get("last_name", "")} {from_message_prefix}: '

            # Prepare prefix metadata for storage
            prefix_metadata = {
                "message_timestamp": current_time_user,
                "first_name": user_context.user_record.get("first_name", ""),
                "last_name": user_context.user_record.get("last_name", ""),
                "source": source
            }

            # Determine message category based on source
            from src.core.models import MessageCategory
            if source in ["scheduled", "recurring", "triggered"]:
                msg_category = MessageCategory.SCHEDULED_OUTPUT.value
            else:
                msg_category = MessageCategory.CONVERSATION.value

            # Process input based on type
            if isinstance(input, list):
                # Grouped messages - use the parallel method
                history, has_media = await generate_user_messages_parallel(
                    conversation_manager=self.conversation_manager,
                    input_messages=input,
                    messages=history,
                    conversation_id=conversation_id,
                    base_message_prefix=message_prefix,
                    prefix_metadata=prefix_metadata,
                    message_category=msg_category,
                    user_context=user_context
                )
            elif isinstance(input, dict):
                # Single message - existing logic
                if input_text and source != 'browser_tool':
                    ### filter out flags, empty text, etc.
                    input_text = input_text.replace('/START_NEW','').replace('/start_new','').strip()
                    if not input_text:
                        input_text = "The user sent a message with no text. if there are also no files, indicate that the user sent an empty message."

                    # Merge prefix metadata with existing metadata
                    storage_metadata = {**metadata, **prefix_metadata}

                    # Store raw content without prefix
                    await self.conversation_manager.add_user_message(user_context.user_id, conversation_id, input_text, storage_metadata, msg_category)
                    # But use prefixed content for LLM history
                    history.append(HumanMessage(content=message_prefix + input_text))
                
                # Handle files for single message
                if input_files:
                    # Merge prefix metadata with file metadata
                    file_storage_metadata = {**metadata, **prefix_metadata}
                    history = await generate_file_messages(
                        conversation_manager=self.conversation_manager,
                        input_files=input_files,
                        messages=history,
                        conversation_id=conversation_id,
                        message_prefix=message_prefix,
                        prefix_metadata=file_storage_metadata,
                        message_category=msg_category
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
            conversational = True
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
                user_integration_names = await integration_service.get_user_integration_names(user_context.user_id)
                logger.info(f"User {user_context.user_id} has integrations: {user_integration_names}")
                plan, required_tool_ids, plan_str = await ai_service.granular_planning(history, user_integration_names, stream_buffer=self.stream_buffer)
                if plan and plan.query_type and plan.query_type == 'command':
                    conversational = False
            except Exception as e:
                logger.error(f"Error during granular planning call: {e}", exc_info=True)
                required_tool_ids = None  # Fallback to loading all tools
            if plan_str:
                await self.stream_buffer.write({
                    "type": "thinking_token",
                    "content": plan_str,
                    "display_as": "thinking"
                })
            tools = await self.tools_factory.create_tools(
                user_context,
                metadata,
                timezone_name,
                request_id=self.trace_id,
                required_tool_ids=required_tool_ids,
                conversation_manager=self.conversation_manager
            )

            # NEW: Type-driven parameter resolution
            resolution_context = None
            # if required_tool_ids and not minimal_tools:
            #     try:
            #         from src.core.kg_input_resolution import analyze_tools_for_query
            #         from src.core.praxos_client import PraxosClient

            #         # Create praxos client for KG queries
            #         praxos_client = PraxosClient(
            #             environment_name=f"user_{user_context.user_id}",
            #             api_key=settings.PRAXOS_API_KEY
            #         )

            #         # Analyze tools for parameter resolution
            #         resolution_context = await analyze_tools_for_query(
            #             tools=tools,
            #             required_tool_ids=required_tool_ids,
            #             user_query=input_text,
            #             praxos_client=praxos_client
            #         )

            #         logger.info(f"Parameter resolution analysis complete for {len(resolution_context)} tools")

            #     except Exception as e:
            #         logger.error(f"Error during parameter resolution analysis: {e}", exc_info=True)
            #         resolution_context = None
            logger.info(f"Loaded {len(tools)} tools based on planning")
            # Determine minimal_tools correctly based on planning outcome
            # If planning indicates tooling_need=True (conversational=False) or specific tools were required, it's not minimal
            minimal_tools = True
            if required_tool_ids and len(required_tool_ids) > 0:
                minimal_tools = False
            # Also check if planning indicated this is a command (not conversational)
            # even if no tools were specified after filtering (e.g., send_intermediate_message was removed)
            if not conversational:
                minimal_tools = False
                logger.info("Query classified as 'command', setting minimal_tools=False even if no tools specified after filtering")

            tool_executor = ToolNode(tools)
            if minimal_tools and conversational:
                ### this is a basic query
                self.llm = self.fast_llm

            if required_tool_ids is None and conversational:
                required_tool_ids = ['reply_to_user_on_' + source.lower()]  # Auto-insert platform messaging tool
            llm_with_tools = self.llm.bind_tools(tools)
            tool_descriptions = ""
            for i, tool in enumerate(tools):
                try:
                    tool_descriptions += f"{tool.name}: {tool.description}\n"
                except Exception as e:
                    logger.error(f"Error getting description for tool: {e}, for tool {str(tool)}", exc_info=True)
                    continue

            # Add resolution guidance to system prompt if available
            resolution_guidance = ""
            # if resolution_context:
            #     resolution_guidance = "\n\n**KNOWLEDGE GRAPH PARAMETER RESOLUTION:**\n"
            #     resolution_guidance += "Some tool parameters can be auto-filled from the knowledge graph:\n\n"
            #     for tool_name, tool_resolution in resolution_context.items():
            #         if tool_resolution["analysis"]["kg_resolvable_count"] > 0:
            #             resolution_guidance += tool_resolution["guidance"] + "\n"

            system_prompt = create_system_prompt(user_context, source, metadata, tool_descriptions, plan, resolution_guidance)

            workflow = StateGraph(AgentState)
            workflow.add_node("agent", call_model)
            workflow.add_node("router", should_continue_router)
            workflow.add_node("obtain_data", obtain_data)   # NEW
            workflow.add_node("action", tool_executor)
            workflow.add_node("finalize", generate_final_response)

            workflow.set_entry_point("agent")
            workflow.add_edge("agent", "router")
            workflow.add_edge("obtain_data", "action")  # obtain_data always drives a single tool turn
            workflow.add_edge("action", "router")
            workflow.add_edge("finalize", END)


                        
            app = workflow.compile()
            if input_text is None:
                input_text = "placeholder for empty input"
            graph_config = GraphConfig(
                llm_with_tools=llm_with_tools,
                structured_llm=self.structured_llm,
                system_prompt=system_prompt,
                initial_state_len=len(history),
                plan_str=plan_str,
                fast_llm = self.fast_llm,
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
                "reply_sent": False,  # Track if agent used messaging tools
                "reply_count": 0,  # Track number of messages sent
            }
            # --- END Graph Definition ---

            # Create tool monitoring callback
            # tool_monitor = ToolMonitorCallback(
            #     user_id=user_context.user_id,
            #     execution_id=execution_id
            # )
            
            # Create immediate persistence callback for tool outputs
            persistence_callback = ImmediatePersistenceCallback(
                conversation_manager=self.conversation_manager,
                conversation_id=conversation_id,
                user_id=user_context.user_id
            )

            ### for now, we remove it.
            # Always use streaming - buffer decides what to do with events
            final_state = await self._run_with_streaming(app, initial_state, callbacks=[persistence_callback])

            # Persist only NEW intermediate messages from this execution
            # new_messages = final_state['messages'][len(initial_state['messages']):]

            # await update_history( conversation_manager=self.conversation_manager, new_messages=new_messages, conversation_id=conversation_id, user_context=user_context, final_state=final_state)
            final_response = final_state['final_response']
            output_blobs = []
            ### this actually should be handled directly now.
            if not final_state.get('reply_sent'):
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

            # Clean up media bus for this conversation
            try:
                from src.core.media_bus import media_bus
                cleared_count = media_bus.clear_conversation(conversation_id)
                if cleared_count > 0:
                    logger.info(f"Cleared {cleared_count} media references from bus for conversation {conversation_id}")
            except Exception as e:
                logger.error(f"Error clearing media bus: {e}", exc_info=True)

    async def _run_with_streaming(
        self,
        app,
        initial_state: dict,
        callbacks: list = []
    ) -> dict:
        """Execute graph with streaming - writes to buffer"""
        final_state = None

        try:
            async for event in app.astream_events(
                initial_state,
                config={
                    "recursion_limit": 100,
                    "tool_iter_counter": 0,
                    "callbacks": callbacks
                },
                version="v2"
            ):
                # Parse event and write to buffer (buffer decides if it publishes)
                await self._handle_stream_event(event)

                # Capture final state
                if event.get("event") == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event["data"]["output"]

            # Signal stream completion
            await self.stream_buffer.write({
                "type": "stream_done",
                "display_as": "status"
            })

            return final_state

        except Exception as e:
            # Write error to buffer
            logger.error(f"Streaming error: {e}", exc_info=True)
            await self.stream_buffer.write({
                "type": "error",
                "message": str(e),
                "severity": "error",
                "recoverable": False
            })

            # Fallback to batch mode (non-streaming)
            logger.info("Falling back to batch mode after streaming error")
            return await app.ainvoke(
                initial_state,
                {
                    "recursion_limit": 100, 
                    "tool_iter_counter": 0,
                    "callbacks": callbacks
                }
            )

    async def _handle_stream_event(self, event: dict) -> None:
        """Parse LangGraph events and write to buffer"""
        event_type = event.get("event")

        try:
            if event_type == "on_chat_model_stream":
                # LLM token streaming - filter by node
                chunk = event["data"]["chunk"]
                
                # 1. Handle Tool Call Generation (Intent Streaming)
                if (hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks):
                    for tool_chunk in chunk.tool_call_chunks:
                        # Only stream start event if we have a name (start of call)
                        if tool_chunk.get("name"):
                            tool_name = tool_chunk["name"]
                            # Skip user-facing communication tools from technical stream
                            if tool_name.startswith('reply_to_user_'):
                                continue
                                
                            await self.stream_buffer.write({
                                "type": "tool_start",
                                "tool": tool_name,
                                "tool_call_id": tool_chunk.get("id"),
                                "display_as": "tool_call"
                            })
                    return

                # 2. Handle Thinking Tokens
                thinking_content = extract_thinking_from_chunk(chunk)
                if thinking_content:
                    await self.stream_buffer.write({
                        "type": "thinking_token",
                        "content": thinking_content,
                        "display_as": "thinking"
                    })

                # 3. Handle Text Generation (Content Streaming)
                # Robust text extraction to avoid technical metadata in the stream
                text_content = extract_text_from_chunk(chunk.content)
                
                if not text_content:
                    return

                node_name = event.get("metadata", {}).get("langgraph_node", "")

                if node_name == "agent":
                    # These are user-facing tokens
                    await self.stream_buffer.write({
                        "type": "message_token",
                        "content": text_content,
                        "display_as": "message"
                    })

            elif event_type == "on_chain_start":
                # Node execution start (for debugging)
                node_name = event.get("name", "")
                if node_name in ["agent", "router", "obtain_data", "action", "finalize"]:
                    await self.stream_buffer.write({
                        "type": "node_transition",
                        "node": node_name,
                        "phase": "start",
                        "display_as": "debug"  # Only show in debug mode
                    })

            elif event_type == "on_chain_end":
                # Node execution end (for debugging)
                node_name = event.get("name", "")
                if node_name in ["agent", "router", "obtain_data", "action", "finalize"]:
                    await self.stream_buffer.write({
                        "type": "node_transition",
                        "node": node_name,
                        "phase": "end",
                        "display_as": "debug"  # Only show in debug mode
                    })

            elif event_type == "on_tool_end":
                # Tool execution result - show friendly status, NOT raw output
                tool_name = event.get("name", "")
                
                # Extract output for frontend display
                output = event.get("data", {}).get("output")
                
                output_str = ""
                if hasattr(output, 'content'):
                    output_str = output.content
                elif isinstance(output, str):
                    output_str = output
                else:
                    output_str = str(output) if output is not None else ""
                
                # Don't stream raw tool results (like JSON from gmail_search)
                # Instead, show friendly status message
                friendly_name = tool_name.replace("_", " ").title()
                logger.info(f"Tool {tool_name} completed with output: {output_str}")
                await self.stream_buffer.write({
                    "type": "tool_status",
                    "tool": tool_name,
                    "message": f"✓ {friendly_name}",
                    "output": output_str,
                    "display_as": "status"
                })

        except Exception as e:
            logger.error(f"Error handling stream event: {e}", exc_info=True)