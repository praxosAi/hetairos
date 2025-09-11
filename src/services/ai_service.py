

from langchain_google_genai import ChatGoogleGenerativeAI
from src.config.settings import settings
from pydantic import BaseModel
from src.utils.logging import setup_logger
logger = setup_logger(__name__)
class AIService:
    def __init__(self, model_name: str = "gemini-2.5-pro-latest"):
        self.model = ChatGoogleGenerativeAI(model=model_name, google_api_key=settings.GOOGLE_API_KEY)

    async def with_structured_output(self, schema: BaseModel, prompt: str):
        structured_llm = self.model.with_structured_output(schema)
        return await structured_llm.ainvoke(prompt)

    async def normal_call(self, prompt: str):
        return await self.model.ainvoke(prompt)

    async def short_call(self, prompt: str):
        short_prompt = f"{prompt} Please respond with only one or two words."
        return await self.model.ainvoke(short_prompt)

ai_service = AIService()
