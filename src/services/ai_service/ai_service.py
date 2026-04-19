import json
from langchain_google_genai import ChatGoogleGenerativeAI
from src.config.settings import settings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage,SystemMessage
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.utils.logging import setup_logger
from src.utils.file_msg_utils import build_payload_entry_from_inserted_id
from langchain.chat_models import init_chat_model
from src.services.ai_service.ai_service_models import *
from src.services.ai_service.prompts.caches import update_cache_ttl, get_planning_cache_name
from typing import Tuple
import asyncio
logger = setup_logger(__name__)
class AIService:
    def __init__(self, model_name: str = "gemini-3.1-pro-preview"):
        self.model_gemini_pro = ChatGoogleGenerativeAI(model=model_name, google_api_key=settings.GEMINI_API_KEY)
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id='internal_call')
        self.model_gpt_mini = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        self.model_gemini_flash = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=settings.GEMINI_API_KEY,   include_thoughts=True)
        self.model_gemini_flash_no_thinking = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=settings.GEMINI_API_KEY, thinking_level = 'minimal', include_thoughts=False)
        self.model_gemini_flash_lite = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", google_api_key=settings.GEMINI_API_KEY, include_thoughts=False)
    async def with_structured_output(self, schema: BaseModel, prompt: str):
        structured_llm = self.model_gemini_flash.with_structured_output(schema)
        return await structured_llm.ainvoke(prompt)


    async def boolean_call(self, prompt: str, think: bool = False) -> bool:
        if think:
            structured_llm = self.model_gemini_flash.with_structured_output(BooleanResponse)
        else:
            structured_llm = self.model_gemini_flash_no_thinking.with_structured_output(BooleanResponse)
        response = await structured_llm.ainvoke(prompt)
        logger.info(f"Boolean call response: {response}")
        return response.response

    async def normal_call(self, prompt: str):
        return await self.model_gemini_flash.ainvoke(prompt)

    async def short_call(self, prompt: str):
        short_prompt = f"{prompt} Please respond with only one or two words."
        return await self.model_gemini_flash.ainvoke(short_prompt)

    async def flash_call(self, prompt: str):
        return await self.model_gemini_flash.ainvoke(prompt)
    
    



    async def granular_planning(self, context: list[BaseMessage], user_integration_names: set[str], source: Optional[str] = None, stream_buffer: Optional['StreamBuffer'] = None) -> Tuple[GranularPlanningResponse, Optional[list[str]], Optional[str]]:
        # Default to no-op if not provided
        if stream_buffer is None:
            from src.core.stream_buffer import NoOpStreamBuffer
            stream_buffer = NoOpStreamBuffer()

        # Stream status update (no-op if NoOpStreamBuffer)
        await stream_buffer.write({
            "type": "status",
            "message": "Analyzing your request...",
            "stage": "planning",
            "display_as": "status"
        })

        # Get cache name from Redis
        cache_name = await get_planning_cache_name()
        planning_llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=settings.GEMINI_API_KEY, thinking_level = 'minimal', cached_content=cache_name, include_thoughts=True)

        """
        Enhanced planning call that returns specific tool function IDs needed for the task.
        This enables precise tool loading instead of all-or-nothing approach.
        """
        ### we now use caching for this. this further reduces latency of this call, as well as its cost.




        from src.utils.file_msg_utils import replace_media_with_placeholders

        # Replace media with placeholders
        msgs_with_placeholders = replace_media_with_placeholders(context)
        # sys_message = SystemMessage(content=planning_prompt)
        # messages = [sys_message] + msgs_with_placeholders
        messages = msgs_with_placeholders
        messages.append(HumanMessage(content='We know that the user has the following tools available to them: \n' + '\n'.join(list(user_integration_names))))
        if source:
            if source == 'websocket':
                source_note = (
                    "[PRAXOS SYSTEM NOTIFICATION]: This request arrived over the 'websocket' channel "
                    "(the in-app live chat UI). There is NO `reply_to_user_on_websocket` tool — replies "
                    "on this channel are streamed natively by the agent's text response, not by a tool call. "
                    "Therefore: do NOT include any `reply_to_user_on_*` tool in `required_tools` UNLESS the "
                    "user has explicitly asked you to reply on a DIFFERENT platform (e.g. 'text me on Telegram', "
                    "'email me the answer'). For a normal in-app reply, leave the messaging tools out entirely."
                )
            else:
                source_note = (
                    f"[PRAXOS SYSTEM NOTIFICATION]: This request arrived over the '{source}' channel. "
                    f"If a reply is needed and the user did not ask for delivery on a different platform, "
                    f"prefer `reply_to_user_on_{source}` (it will be auto-injected if you omit it, but listing "
                    f"it makes the plan explicit). Only select a different `reply_to_user_on_*` tool if the "
                    f"user explicitly asked to be replied on that other platform."
                               )
            messages.append(HumanMessage(content=source_note))
        logger.info('Calling granular_planning for precise tool selection')

        # structured_llm = planning_llm.with_structured_output(GranularPlanningResponse)
        response_raw = await planning_llm.ainvoke(messages)
        ## now, we must cast it
        planning = None
        for tool in response_raw.tool_calls:
            if tool['name'] == 'Create_Granular_Planning_Response':
                logger.info(f"Granular planning response created: {json.dumps(tool['args'],indent=2)}")
                planning = GranularPlanningResponse(**tool['args'])
                break

        # Validate the planning response
        if planning and planning.tooling_need and (not planning.required_tools or len(planning.required_tools) == 0):
            logger.warning(f"Malformed planning response detected: tooling_need=True but required_tools is empty. Retrying with hint.")
            logger.warning(f"Original planning response: {planning}")

            # Add a hint message and retry
            retry_hint = HumanMessage(content="IMPORTANT: The previous planning response indicated that tools are needed (tooling_need=True) but did not specify which tools in the required_tools list. Please provide the specific tool IDs that are needed for this task in the required_tools field. Be precise and list the exact tools required.")
            messages.append(retry_hint)

            # Retry the planning call, with a stronger llm.
            planning_llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=settings.GEMINI_API_KEY, cached_content=cache_name , include_thoughts=True)
            planning_llm = planning_llm.with_structured_output(GranularPlanningResponse)
            response_raw = await planning_llm.ainvoke(messages)
            for tool in response_raw.tool_calls:
                if tool['name'] == 'Create_Granular_Planning_Response':
                    planning = GranularPlanningResponse(**tool['args'])
                    break
            logger.info(f"Retry planning response: {planning}")

        logger.info(f"Granular planning response: {planning}")
        logger.info(f"Required tools: {[tool.value for tool in planning.required_tools] if planning and planning.required_tools else []}")
        ### this is fire and forget, we don't want to await it
        try:
            asyncio.create_task(update_cache_ttl())
        except Exception as e:
            logger.error(f"Error updating cache TTL: {e}")
        plan = None
        plan_str = ""
        required_tool_ids = None

        if planning:
            # Extract required tool IDs from enum to string list
            required_tool_ids = [tool.value for tool in planning.required_tools] if planning.required_tools else []

            # Filter out send_intermediate_message if it's the only tool
            if required_tool_ids == ["send_intermediate_message"]:
                logger.info("send_intermediate_message is the only tool selected. Removing it as output suffices for this case.")
                required_tool_ids = []
                planning.tooling_need = False
                planning.query_type = "conversational"

            # Auto-insert platform messaging tool for conversational queries
            # If no tools selected or only non-messaging tools, add source platform tool
            platform_tools = [tid for tid in required_tool_ids if tid.startswith('reply_to_user_on_')]
            if not platform_tools and planning.query_type == "conversational":
                # No platform tool selected - auto-insert based on source
                # Note: source will be extracted from context in tool factory
                logger.info("Conversational query with no platform tool - will auto-insert in tool factory")
                # Don't add to required_tool_ids here - tool factory handles it

            if platform_tools:
                logger.info(f"Platform messaging tools selected: {platform_tools}")

            logger.info('required tool ids are: ' + str(required_tool_ids))
            # Build plan string if plan/steps are provided
            plan_str = ""
            if planning.plan:
                plan_str += f"the plan is as follows: {planning.plan}. \n"
            if planning.steps:
                planning_lines = '\n'.join(planning.steps)
                plan_str += f"the steps are as follows: {planning_lines}. "
            if plan_str:
                plan_str = """the following initial plan has been suggested by the system. take the plan into account when generating the response, but do not feel bound by it. you can deviate from the plan if you think it's necessary.
                    In either case, make sure to use the appropriate tools that are provided to you for performing this task. Do not respond that you are doing a task, without actually doing it. instead, do the task, then send the user indication that you have done it, with any necessary result data.  \n\n""" + plan_str
                plan = planning
                logger.info(f"Added planning context to history: {plan_str}")

        # Stream tool selection update
        if required_tool_ids:
            tool_names = ", ".join(required_tool_ids[:3])
            if len(required_tool_ids) > 3:
                tool_names += f" and {len(required_tool_ids) - 3} more"

            await stream_buffer.write({
                "type": "status",
                "message": f"Loading tools: {tool_names}",
                "stage": "tool_loading",
                "display_as": "status"
            })
        
        return plan, required_tool_ids, plan_str

    async def multi_modal_by_doc_id(self, prompt: str, doc_id: str):
        logger.info(f"Fetching payload for doc_id: {doc_id}")
        payload,file_info =   await build_payload_entry_from_inserted_id(doc_id)
        if not payload:
            raise ValueError(f"Could not retrieve payload for doc_id: {doc_id}")
        logger.info(f"Retrieved payload for doc_id: {doc_id}, preparing messages for AI model.")
        messages = [HumanMessage(content=prompt), HumanMessage(content=[payload])]
        return await self.model_gemini_flash.ainvoke(messages)

    async def describe_file(self, inserted_id: str, force: bool = False) -> Optional[str]:
        """Generate (or return cached) a searchable description for a file and persist it to `documents.auto_description`.

        For audio/voice files the output is a verbatim transcript; for everything else it is a short
        (<= 40 words) factual description suitable for later retrieval. Idempotent: if auto_description
        already exists on the doc and force=False, returns the cached value without calling the model.

        Fire-and-forget safe: all exceptions are caught and logged; the method returns None on failure.
        """
        from src.utils.database import db_manager
        try:
            doc = await db_manager.get_document_by_id(inserted_id)
            if not doc:
                logger.warning(f"describe_file: document {inserted_id} not found")
                return None

            existing = doc.get("auto_description")
            if existing and not force:
                return existing

            file_type = doc.get("type", "file")
            file_name = doc.get("file_name", "unknown")

            if file_type in {"audio", "voice"}:
                instruction = (
                    "Transcribe this audio verbatim. If it is longer than ~500 words, transcribe the "
                    "first portion in full and summarize the remainder in one sentence. Return only the "
                    "transcript, no preamble."
                )
            elif file_type in {"image", "photo"}:
                instruction = (
                    f"In 40 words or fewer, describe what this image ({file_name}) depicts — subjects, "
                    f"setting, any legible text. Be specific enough that a later search could find it. "
                    f"Return only the description, no preamble."
                )
            elif file_type == "video":
                instruction = (
                    f"In 40 words or fewer, describe what this video ({file_name}) shows — subjects, "
                    f"setting, any spoken or on-screen text. Return only the description, no preamble."
                )
            else:
                instruction = (
                    f"In 40 words or fewer, describe what this file ({file_name}) contains — topic, "
                    f"type of content, any distinguishing details. Be specific enough that a later "
                    f"search could find it. Return only the description, no preamble."
                )

            payload, _ = await build_payload_entry_from_inserted_id(inserted_id)
            if not payload:
                logger.warning(f"describe_file: could not build payload for {inserted_id}")
                return None

            response = await self.model_gemini_flash_lite.ainvoke(
                [HumanMessage(content=instruction), HumanMessage(content=[payload])]
            )
            raw = getattr(response, "content", None)
            if isinstance(raw, list):
                parts = []
                for block in raw:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                description = "".join(parts).strip()
            else:
                description = (raw or "").strip()
            if not description:
                return None

            await db_manager.update_document_auto_description(inserted_id, description)
            logger.info(f"describe_file: generated auto_description for {inserted_id} ({file_type}): {description[:80]}")
            return description
        except Exception as e:
            logger.error(f"describe_file failed for {inserted_id}: {e}", exc_info=True)
            return None
    
    
ai_service = AIService()
    