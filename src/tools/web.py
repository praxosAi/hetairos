import time
import unicodedata
from urllib.parse import urlparse, urlunparse
import requests
from requests.utils import requote_uri
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

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

def create_web_tools() -> list:
    return [read_webpage_content]
