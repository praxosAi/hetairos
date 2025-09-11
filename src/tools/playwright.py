from typing import List
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import (
    create_async_playwright_browser,
)


# This global instance will be managed by the AgentToolsFactory
# to ensure a single browser is used across all tools.
async_browser = create_async_playwright_browser()

def create_playwright_tools() -> List:
    """
    Creates and returns a list of Playwright browser tools.
    """
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)
    tools = toolkit.get_tools()
    return tools
