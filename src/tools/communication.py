from typing import List, Dict, Optional
from langchain_core.tools import tool
from src.egress.service import egress_service
from src.tools.tool_types import ToolExecutionResponse

def create_bot_communication_tools(metadata: Optional[Dict] = None, user_id: str = None) -> List:
    """Creates tools for the bot to communicate with users on different platforms."""

    @tool 
    async def reply_to_user_via_email(body: str) -> ToolExecutionResponse:
        """
        Sends an email using the Praxos bot. this is specifically for replying to a user's email.
        """
        try:
            await egress_service.send_response({"source": "email", "output_type": "email", "email_type": "reply","original_message": metadata.get("original_message")}, {"response": body})
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))
        
    @tool
    async def send_new_email_as_praxos_bot(recipients: List[str], subject: str, body: str) -> ToolExecutionResponse:
        """
        Sends an email using the Praxos bot. this is specifically for sending a new email to someone, as yourself, the mypraxos assistant.
        """
        try:
            await egress_service.send_response({"source": "email", "output_type": "email", "email_type": "new","original_message": metadata.get("original_message"),"new_email_message": {"recipients": recipients, "subject": subject, "body": body}}, {"response": body})
            return ToolExecutionResponse(status="success", result="Email sent successfully.")
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    # @tool
    # async def send_whatsapp_message_as_praxos_bot(message: str) -> ToolExecutionResponse:
    #     """
    #     Sends a whatsapp message using the Praxos bot. this is specifically for sending the user a whatsapp message. we will handle the phone number for the user.
    #     """
    #     try:
    #         await egress_service.send_response({"source": "whatsapp", "output_type": "whatsapp",'user_id': str(user_id)}, {"response": message})
    #         return ToolExecutionResponse(status="success", result="Whatsapp message sent successfully.")
    #     except Exception as e:
    #         return ToolExecutionResponse(status="error", system_error=str(e))
            
    # @tool
    # async def send_telegram_message_as_praxos_bot(message: str) -> ToolExecutionResponse:
    #     """
    #     Sends a telegram message using the Praxos bot. this is specifically for sending the user a telegram message. we will handle the chat id for the user.
    #     """
    #     try:
    #         await egress_service.send_response({"source": "telegram", "output_type": "telegram",'user_id': str(user_id)}, {"response": message})
    #         return ToolExecutionResponse(status="success", result="Telegram message sent successfully.")
    #     except Exception as e:
    #         return ToolExecutionResponse(status="error", system_error=str(e))

    return [reply_to_user_via_email, send_new_email_as_praxos_bot]
