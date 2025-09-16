import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
from urllib.parse import quote, urlparse, urlunparse
import time

logger = setup_logger(__name__)

def _encode_url_properly(url: str) -> str:
    """
    Properly encode URLs with non-ASCII characters.
    Some servers need specific encoding handling for Greek, Cyrillic, etc.
    """
    try:
        # Parse the URL
        parsed = urlparse(url)
        
        # Quote the path component to handle non-ASCII characters
        # Use safe characters that are typically allowed in URLs
        encoded_path = quote(parsed.path.encode('utf-8'), safe='/-._~!$&\'()*+,;=:@')
        
        # Quote query parameters if present
        encoded_query = quote(parsed.query.encode('utf-8'), safe='=-&') if parsed.query else parsed.query
        
        # Reconstruct the URL
        encoded_parsed = parsed._replace(path=encoded_path, query=encoded_query)
        return urlunparse(encoded_parsed)
    except Exception as e:
        logger.warning(f"URL encoding failed for {url}: {e}, using original")
        return url

@tool
def read_webpage_content(url: str) -> ToolExecutionResponse:
    """
    Reads the textual content of a webpage from a given URL.
    Handles Unicode characters in URLs properly for sites with Greek, Cyrillic, etc.

    Args:
        url: The URL of the webpage to read.
    """
    # Try multiple URL encoding strategies for better compatibility
    urls_to_try = [
        url,  # Original URL
        _encode_url_properly(url),  # Properly encoded URL
    ]
    
    # Also try with different user agents for sites that are picky
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    last_error = None
    
    for attempt_url in urls_to_try:
        for user_agent in user_agents:
            try:
                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9,el;q=0.8,gr;q=0.7',  # Include Greek language
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                logger.info(f"Trying URL: {attempt_url} with User-Agent: {user_agent[:50]}...")
                response = requests.get(attempt_url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
                
                # Success! Process the content
                soup = BeautifulSoup(response.content, 'html.parser')

                # Remove script and style elements
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()

                # Get text and clean it up
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)

                # Truncate for very long pages
                max_length = 10000
                if len(text) > max_length:
                    text = text[:max_length] + "\n\n... (content truncated)"

                return ToolExecutionResponse(status="success", result=text)
                
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"Failed attempt with URL {attempt_url} and UA {user_agent[:30]}: {e}")
                time.sleep(0.5)  # Brief pause between attempts
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"Parsing error for {attempt_url}: {e}")
                continue
    
    # If we get here, all attempts failed
    logger.error(f"All attempts failed for URL {url}. Last error: {last_error}")
    return ToolExecutionResponse(
        status="error", 
        system_error=str(last_error), 
        user_message=f"Failed to retrieve the webpage after trying multiple methods. The page might be unavailable or require special access. Last error: {last_error}"
    )

def create_web_tools() -> list:
    """Creates web-related tools."""
    return [read_webpage_content]
