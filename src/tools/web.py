import time
import unicodedata
import socket
from ipaddress import ip_address, ip_network
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

# Blocked IP ranges for SSRF protection
BLOCKED_IP_RANGES = [
    ip_network('10.0.0.0/8'),       # Private Class A
    ip_network('172.16.0.0/12'),    # Private Class B
    ip_network('192.168.0.0/16'),   # Private Class C
    ip_network('127.0.0.0/8'),      # Loopback
    ip_network('169.254.0.0/16'),   # Link-local (AWS/Azure metadata)
    ip_network('::1/128'),          # IPv6 loopback
    ip_network('fe80::/10'),        # IPv6 link-local
    ip_network('fc00::/7'),         # IPv6 unique local
]

def validate_url_for_ssrf(url: str) -> None:
    """
    Validates URL to prevent SSRF attacks.

    Blocks:
    - Non-HTTP(S) protocols (file://, ftp://, gopher://, etc.)
    - Private/internal IP addresses (RFC 1918)
    - Localhost and loopback addresses
    - Cloud metadata endpoints (169.254.169.254)
    - Link-local addresses

    Args:
        url: URL to validate

    Raises:
        ValueError: If URL is blocked for security reasons
    """
    try:
        parsed = urlparse(url)

        # Step 1: Only allow HTTP/HTTPS
        if parsed.scheme not in ['http', 'https']:
            raise ValueError(
                f"Protocol not allowed: {parsed.scheme}. "
                f"Only http:// and https:// URLs are permitted."
            )

        # Step 2: Extract hostname
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL must contain a valid hostname")

        # Step 3: Block localhost variations
        localhost_names = [
            'localhost', 'localhost.localdomain',
            '0.0.0.0', '0000', '0x0', '0177.0.0.1',
            'localhost6', 'ip6-localhost', 'ip6-loopback'
        ]
        if hostname.lower() in localhost_names:
            raise ValueError(
                f"Access to localhost is blocked for security reasons"
            )

        # Step 4: Resolve hostname to IP address
        try:
            ip_str = socket.gethostbyname(hostname)
            ip = ip_address(ip_str)
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {hostname}")
        except ValueError as e:
            raise ValueError(f"Invalid IP address format: {e}")

        # Step 5: Check against blocked IP ranges
        for blocked_range in BLOCKED_IP_RANGES:
            if ip in blocked_range:
                raise ValueError(
                    f"Access denied: {hostname} ({ip}) is in a blocked network range. "
                    f"Access to internal/private networks is not permitted for security reasons."
                )

        # Step 6: Additional check for cloud metadata endpoint
        if str(ip) == '169.254.169.254':
            raise ValueError(
                "Access to cloud metadata endpoint (169.254.169.254) is blocked"
            )

        logger.info(f"URL validated for SSRF protection: {url} -> {hostname} ({ip})")

    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Error validating URL {url}: {e}")
        raise ValueError(f"URL validation failed: {e}")


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
    Only allows access to public internet URLs (blocks internal networks for security).
    """
    # SSRF Protection: Validate URL before any requests
    try:
        validate_url_for_ssrf(url)
    except ValueError as e:
        logger.warning(f"SSRF protection blocked URL: {url} - {e}")
        return ToolExecutionResponse(
            status="error",
            result=f"Cannot access this URL for security reasons: {str(e)}"
        )

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
                # Disable redirects to validate redirect targets
                resp = requests.get(attempt_url, headers=headers, timeout=timeout, allow_redirects=False)

                # Handle redirects manually with validation
                if resp.status_code in [301, 302, 303, 307, 308]:
                    redirect_url = resp.headers.get('Location')
                    if redirect_url:
                        # Validate redirect target
                        try:
                            validate_url_for_ssrf(redirect_url)
                            # Follow redirect
                            resp = requests.get(redirect_url, headers=headers, timeout=timeout, allow_redirects=False)
                        except ValueError as e:
                            logger.warning(f"Blocked redirect to: {redirect_url} - {e}")
                            raise ValueError(f"Redirect blocked: {e}")

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
            max_steps: Maximum number of browser actions to take (default: 30)

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
                "max_steps": min(max(max_steps, 20), 100),
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

def create_web_tools(request_id: str, user_id: str, metadata: dict, tool_registry) -> list:
    """
    Create web tools including google_search and AI browser tool.

    Args:
        request_id: Request ID for tracing
        user_id: User ID
        metadata: Request metadata including conversation_id, source, etc.
        tool_registry: Tool registry for applying YAML descriptions
    """
    tools = [google_search, read_webpage_content]

    if request_id is not None:
        # Add AI browser tool that publishes to queue
        tools.append(create_browser_tool(request_id, user_id, metadata))

    tool_registry.apply_descriptions_to_tools(tools)
    return tools
