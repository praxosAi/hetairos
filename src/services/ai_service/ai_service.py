

from langchain_google_genai import ChatGoogleGenerativeAI
from src.config.settings import settings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage,SystemMessage
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.utils.logging import setup_logger
from src.utils.file_msg_utils import build_payload_entry_from_inserted_id
from langchain.chat_models import init_chat_model
from src.services.ai_service.ai_service_models import *
from src.services.ai_service.prompts.tooling_capabilities import TOOLING_CAPABILITIES_PROMPT
from src.services.ai_service.prompts.granular_tooling_capabilities import GRANULAR_TOOLING_CAPABILITIES
from src.services.ai_service.prompts.caches import update_cache_ttl, PLANNING_CACHE_NAME
import asyncio
logger = setup_logger(__name__)
class AIService:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_gemini_pro = ChatGoogleGenerativeAI(model=model_name, google_api_key=settings.GEMINI_API_KEY)
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id='internal_call')
        self.model_gpt_mini = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        self.model_gemini_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=settings.GEMINI_API_KEY)
        self.model_gemini_flash_no_thinking = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=settings.GEMINI_API_KEY, thinking_budget=0)
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
    
    



    async def granular_planning(self, context: list[BaseMessage]) -> GranularPlanningResponse:
        planning_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=settings.GEMINI_API_KEY, thinking_budget=0, cached_content=PLANNING_CACHE_NAME)

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
        logger.info('Calling granular_planning for precise tool selection')

        # structured_llm = planning_llm.with_structured_output(GranularPlanningResponse)
        response_raw = await planning_llm.ainvoke(messages)

        ## now, we must cast it
        for tool in response_raw.tool_calls:
            if tool['name'] == 'Create_Granular_Planning_Response':
                response = GranularPlanningResponse(**tool['args'])
                break
        logger.info(f"Granular planning response: {response}")
        logger.info(f"Required tools: {[tool.value for tool in response.required_tools]}")
        try:
            asyncio.create_task(update_cache_ttl())
        except Exception as e:
            logger.error(f"Error updating cache TTL: {e}")
        return response

    async def multi_modal_by_doc_id(self, prompt: str, doc_id: str):
        logger.info(f"Fetching payload for doc_id: {doc_id}")
        payload =   await build_payload_entry_from_inserted_id(doc_id)
        if not payload:
            raise ValueError(f"Could not retrieve payload for doc_id: {doc_id}")
        logger.info(f"Retrieved payload for doc_id: {doc_id}, preparing messages for AI model.")
        messages = [HumanMessage(content=prompt), HumanMessage(content=[payload])]
        return await self.model_gemini_flash.ainvoke(messages)
    
    
ai_service = AIService()
    