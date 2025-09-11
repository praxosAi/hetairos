from datetime import datetime
import pytz
from langchain_core.tools import tool

def create_basic_tools() -> list:
    """Create basic information tools"""
    
    @tool
    def get_current_time() -> str:
        """Returns the current time in EST timezone."""
        est = pytz.timezone('America/New_York')
        return "the current date and time, in NYC, is: " + datetime.now(est).strftime('%Y-%m-%d %H:%M:%S %Z%z')
    
    return [get_current_time]
