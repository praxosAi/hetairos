

from langchain_google_genai import ChatGoogleGenerativeAI
from src.config.settings import settings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.utils.logging import setup_logger
from src.utils.file_msg_utils import build_payload_entry_from_inserted_id
from langchain.chat_models import init_chat_model
from src.services.ai_service.ai_service_models import *
logger = setup_logger(__name__)
class AIService:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_gemini_pro = ChatGoogleGenerativeAI(model=model_name, google_api_key=settings.GEMINI_API_KEY)
        llm = init_chat_model("gpt-4o", model_provider="openai")
        from src.utils.portkey_headers_isolation import create_port_key_headers
        portkey_headers , portkey_gateway_url = create_port_key_headers(trace_id='internal_call')
        self.model_gpt_mini = init_chat_model("@azureopenai/gpt-5-mini", api_key=settings.PORTKEY_API_KEY, base_url=portkey_gateway_url, default_headers=portkey_headers, model_provider="openai")
        self.model_gemini_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=settings.GEMINI_API_KEY)
    
    async def with_structured_output(self, schema: BaseModel, prompt: str):
        structured_llm = self.model_gemini_flash.with_structured_output(schema)
        return await structured_llm.ainvoke(prompt)


    async def boolean_call(self, prompt: str) -> bool:
        structured_llm = self.model_gemini_flash.with_structured_output(BooleanResponse)
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
    
    
    async def multi_modal_by_doc_id(self, prompt: str, doc_id: str):
        logger.info(f"Fetching payload for doc_id: {doc_id}")
        payload =   await build_payload_entry_from_inserted_id(doc_id)
        if not payload:
            raise ValueError(f"Could not retrieve payload for doc_id: {doc_id}")
        logger.info(f"Retrieved payload for doc_id: {doc_id}, preparing messages for AI model.")
        messages = [HumanMessage(content=prompt), HumanMessage(content=[payload])]
        return await self.model_gemini_flash.ainvoke(messages)
ai_service = AIService()
    