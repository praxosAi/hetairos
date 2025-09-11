import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

@tool
def read_webpage_content(url: str) -> ToolExecutionResponse:
    """
    Reads the textual content of a webpage from a given URL.

    Args:
        url: The URL of the webpage to read.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

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
        logger.error(f"Error fetching URL {url}: {e}")
        return ToolExecutionResponse(status="error", system_error=str(e), user_message=f"Failed to retrieve the webpage. Please check the URL.")
    except Exception as e:
        logger.error(f"Error parsing webpage {url}: {e}")
        return ToolExecutionResponse(status="error", system_error=str(e), user_message="An error occurred while parsing the webpage.")

def create_web_tools() -> list:
    """Creates web-related tools."""
    return [read_webpage_content]
