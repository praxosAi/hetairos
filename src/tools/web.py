import time
import unicodedata
from urllib.parse import urlparse, urlunparse
import requests
from requests.utils import requote_uri
from bs4 import BeautifulSoup
from langchain_core.tools import tool, InjectedToolCallId
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger
from typing import Annotated, Optional
from src.config.settings import settings

logger = setup_logger(__name__)


@tool
def google_search(query: str) -> ToolExecutionResponse:
    """
    Search Google for information and recent results.

    Args:
        query: Search query string

    Returns:
        ToolExecutionResponse with search results

    Examples:
        - "latest news about AI"
        - "weather in New York"
        - "who is the CEO of Tesla"
    """
    try:
        if not query or not query.strip():
            return ErrorResponseBuilder.invalid_parameter(
                operation="google_search",
                param_name="query",
                param_value=query,
                expected_format="Non-empty search query string"
            )

        logger.info(f"Google search: {query}")

        from langchain_google_community import GoogleSearchAPIWrapper

        search = GoogleSearchAPIWrapper()
        result = search.run(query)

        # GoogleSearchAPIWrapper returns a string
        if not result or not result.strip():
            return ToolExecutionResponse(
                status="success",
                result="No search results found for this query."
            )

        return ToolExecutionResponse(status="success", result=result)

    except Exception as e:
        logger.error(f"Error in Google search: {e}", exc_info=True)
        return ErrorResponseBuilder.from_exception(
            operation="google_search",
            exception=e,
            integration="Google Search",
            context={"query": query}
        )


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
    return ErrorResponseBuilder.from_exception(
        operation="read_webpage_content",
        exception=last_error if isinstance(last_error, Exception) else Exception(str(last_error)),
        context={"url": url}
    )

def create_browser_tool(request_id, user_id, metadata):
    """
    Creates the AI browser tool that publishes tasks to the browser_tasks queue.
    The hetairos-browser service will process the task and return results via the events queue.
    """
    @tool
    async def browse_website_with_ai(task: str, tool_call_id: Annotated[str, InjectedToolCallId], max_steps: Optional[int] = 30) -> ToolExecutionResponse:
        """
        Uses an AI-powered browser to interact with dynamic websites (JavaScript, forms, navigation).
        This tool can handle complex web interactions that simple HTML parsing cannot.
        Use this for websites with JavaScript content, forms, modals, or multi-step navigation.

        This operation takes between 30 seconds to 5 minutes and is processed asynchronously.
        You will be notified with the results in this conversation once the task is complete.

        Args:
            task: Natural language description of what to do (e.g., "Find pricing information", "Extract product details"), and on what website, if it's a specific one.
            max_steps: Maximum number of browser actions to take (default: 10)

        Examples:
            - "Navigate to the pricing page and extract all plan details"
            - "Search for 'laptop' and extract the top 5 results"
            - "Find the contact email on this site"
        """
        logger.info(f"Publishing browser task to queue: {task}")

        try:
            from azure.servicebus.aio import ServiceBusClient
            from azure.servicebus import ServiceBusMessage
            import json

            # Create task message for browser_tasks queue
            browser_task = {
                "user_id": user_id,
                "task": task,
                "max_steps": max_steps,
                "metadata": {
                    "conversation_id": metadata.get("conversation_id"),
                    "source": metadata.get("source"),
                    "message_id": metadata.get("message_id"),
                    "tool_call_id": tool_call_id
                },
                "logging_context": {
                    "user_id": user_id,
                    "request_id": request_id,
                    "modality": metadata.get("source", "unknown")
                }
            }

            # Publish to browser_tasks queue
            async with ServiceBusClient.from_connection_string(
                settings.AZURE_SERVICEBUS_CONNECTION_STRING
            ) as client:
                sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_BROWSER_TASKS_QUEUE)
                async with sender:
                    message = ServiceBusMessage(json.dumps(browser_task))
                    await sender.send_messages(message)

            logger.info(f"Browser task published successfully")

            return ToolExecutionResponse(
                status="success",
                result=f"Browser task has been queued and will be processed shortly. You will receive the results automatically in this conversation."
            )

        except Exception as e:
            logger.error(f"Failed to publish browser task: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="browse_website_with_ai",
                exception=e,
                integration="browser_use",
                context={"task": task}
            )

    return browse_website_with_ai

@tool
def google_search(query: str) -> ToolExecutionResponse:
    """
    Searches Google for information using the Google Search API.
    Returns top search results with titles, snippets, and URLs.

    Args:
        query: The search query string

    Examples:
        - "latest news about AI"
        - "weather in New York"
        - "Python programming tutorials"
    """
    try:
        from langchain_google_community import GoogleSearchAPIWrapper

        logger.info(f"Executing Google search for query: {query}")
        search = GoogleSearchAPIWrapper()
        results = search.run(query)

        return ToolExecutionResponse(
            status="success",
            result=results
        )

    except ImportError as e:
        logger.error(f"Failed to import Google Search API wrapper: {e}", exc_info=True)
        return ErrorResponseBuilder.from_exception(
            operation="google_search",
            exception=e,
            integration="google_search_api",
            context={"query": query, "error": "Google Search API dependencies not installed"}
        )
    except Exception as e:
        logger.error(f"Google search failed for query '{query}': {e}", exc_info=True)
        return ErrorResponseBuilder.from_exception(
            operation="google_search",
            exception=e,
            integration="google_search_api",
            context={"query": query}
        )

def create_web_tools(request_id: str, user_id: str, metadata: dict) -> list:
    """
    Create web tools including google_search and AI browser tool.

    Args:
        request_id: Request ID for tracing
        user_id: User ID
        metadata: Request metadata including conversation_id, source, etc.
    """
    tools = [google_search, read_webpage_content]

    if request_id is not None:
        # Add AI browser tool that publishes to queue
        tools.append(create_browser_tool(request_id, user_id, metadata))

    return tools
