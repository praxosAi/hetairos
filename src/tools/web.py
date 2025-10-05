import time
import unicodedata
from urllib.parse import urlparse, urlunparse
import requests
from requests.utils import requote_uri
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from typing import Optional
from src.config.settings import settings

logger = setup_logger(__name__)

def _normalize_and_encode_url(url: str) -> str:
    """
    Normalize Unicode (NFC) and percent-encode safely without double-encoding.
    """
    try:
        parsed = urlparse(url)

        # Normalize path and query to NFC (Greek/Cyrillic can be NFD if copy-pasted)
        norm_path = unicodedata.normalize("NFC", parsed.path or "")
        norm_query = unicodedata.normalize("NFC", parsed.query or "")

        # Rebuild a normalized but still-unquoted URL first
        norm_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            norm_path,
            parsed.params,
            norm_query,
            parsed.fragment
        ))

        # Safely percent-encode the whole thing without double-encoding
        return requote_uri(norm_url)
    except Exception as e:
        logger.warning(f"URL normalization failed for {url}: {e}; using original")
        return url

@tool
def read_webpage_content(url: str) -> ToolExecutionResponse:
    """
    Reads textual content from a webpage, robust to Unicode (Greek/Cyrillic) URLs.
    """
    urls_to_try = [
        url,                      # as-is (requests can handle Unicode)
        _normalize_and_encode_url(url),  # normalized + safely quoted
    ]

    user_agents = [
        # Wikimedia is fine with generic desktop UAs; include one good UA.
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
    ]

    last_error = None
    timeout = 20

    for attempt_url in urls_to_try:
        for user_agent in user_agents:
            try:
                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    # Let requests decide Accept-Encoding (brotli/gzip)
                    'Accept-Language': 'en-US,en;q=0.9,el;q=0.8',
                    'Connection': 'keep-alive',
                }

                logger.info(f"Fetching: {attempt_url}")
                resp = requests.get(attempt_url, headers=headers, timeout=timeout, allow_redirects=True)
                resp.raise_for_status()

                # Help BS4 with correct decoding
                if not resp.encoding:
                    resp.encoding = resp.apparent_encoding

                # Use lxml if available; it’s more forgiving than html.parser
                soup = BeautifulSoup(resp.text, 'lxml')

                # Strip scripts/styles
                for tag in soup(['script', 'style', 'noscript']):
                    tag.decompose()

                text = soup.get_text(separator='\n')
                # Clean up extra blank lines
                lines = [ln.strip() for ln in text.splitlines()]
                text = '\n'.join([ln for ln in lines if ln])

                # Cap very long pages
                max_length = 10000
                if len(text) > max_length:
                    text = text[:max_length] + "\n\n... (content truncated)"

                return ToolExecutionResponse(status="success", result=text)

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"HTTP error on {attempt_url}: {e}")
                time.sleep(0.4)
            except Exception as e:
                last_error = e
                logger.warning(f"Parsing error on {attempt_url}: {e}")

    logger.error(f"All attempts failed for URL {url}. Last error: {last_error}")
    return ToolExecutionResponse(
        status="error",
        system_error=str(last_error),
        user_message=f"Failed to retrieve the page after multiple strategies. Last error: {last_error}"
    )

def create_browser_tool(request_id):
    """
    Creates the AI browser tool with access to the agent's LLM.
    This must be called with the agent's LLM to share context.
    """
    # Configure browser-use and playwright loggers to use JSON formatting
    import logging
    from src.utils.logging import setup_logger

    # Configure browser-use and playwright loggers with JSON formatting
    browser_use_logger = setup_logger("browser_use", level=logging.INFO)
    playwright_logger = setup_logger("playwright", level=logging.INFO)

    # Prevent propagation to avoid duplicate logs
    browser_use_logger.propagate = False
    playwright_logger.propagate = False
    @tool
    async def browse_website_with_ai(task: str, max_steps: Optional[int] = 30) -> ToolExecutionResponse:
        """
        Uses an AI-powered browser to interact with dynamic websites (JavaScript, forms, navigation).
        This tool can handle complex web interactions that simple HTML parsing cannot.
        Use this for websites with JavaScript content, forms, modals, or multi-step navigation.

        IMPORTANT: This operation takes 30-60 seconds. ALWAYS use send_intermediate_message FIRST
        to notify the user you're starting this task.

        Args:
            task: Natural language description of what to do (e.g., "Find pricing information", "Extract product details"), and on what website, if it's a specific one.
            max_steps: Maximum number of browser actions to take (default: 10)

        Examples:
            - "Navigate to the pricing page and extract all plan details"
            - "Search for 'laptop' and extract the top 5 results"
            - "Find the contact email on this site"
        """
        logger.info(f"AI browser request:  task: {task}")

        try:
            # Import browser-use here to avoid import-time dependencies
            from browser_use import Agent, ChatOpenAI
            portkey_headers = {'x-portkey-api-key': settings.PORTKEY_API_KEY,
                'x-portkey-provider': 'azure-openai',
                'x-portkey-trace-id': f"{request_id}_browseruse"}
            portkey_llm =  ChatOpenAI(model='@azureopenai/gpt-5-mini',default_headers=portkey_headers,base_url='https://api.portkey.ai/v1',api_key=settings.PORTKEY_API_KEY)

            browser_agent = Agent(
                task=task,
                llm=portkey_llm,
                use_vision=True,
                # browser=Browser(use_cloud=True),  # Uses Browser-Use cloud for the browser
            )

            # Execute the browsing task
            result = await browser_agent.run(max_steps=max_steps)


            return ToolExecutionResponse(
                status="success",
                result=str(result)
            )

        except Exception as e:
            logger.error(f"AI browser error for {task}: {e}", exc_info=True)
            return ToolExecutionResponse(
                status="error",
                system_error=str(e),
                user_message="Failed to browse the website. The site may be inaccessible or the task too complex."
            )

    return browse_website_with_ai

def create_web_tools(request_id:str) -> list:
    """
    Create web tools. If llm is provided, includes AI browser tool.

    Args:
        llm: Optional LLM instance for AI browsing capabilities
    """
    tools = [read_webpage_content]

    if request_id is not None:
        # Add AI browser tool with shared LLM
        tools.append(create_browser_tool(request_id))

    return tools
