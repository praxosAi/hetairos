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

    @tool
    async def report_bug_to_developers(bug_description: str, additional_context: Optional[str] = None) -> ToolExecutionResponse:
        """
        Reports a bug to the Praxos development team via email.
        Use this when you encounter errors, unexpected behavior, or issues that need developer attention.

        Args:
            bug_description: Detailed description of the bug, including what happened and what was expected
            additional_context: Optional additional context like error messages, stack traces, or reproduction steps
        """
        try:
            dev_emails = ["Soheil@praxos.ai", "Masoud@praxos.ai", "lucas@praxos.ai"]
            subject = "Bug Report from Praxos Agent"

            body = f"""A bug has been reported by the Praxos AI agent:

                    Bug Description:
                    {bug_description}
                    """
            if additional_context:
                body += f"""
                Additional Context:
                {additional_context}
                """

            body += f"""
                    ---
                    Reported by: Agent on behalf of user {user_id}
                    Timestamp: Generated automatically
                    """

            await egress_service.send_response(
                {
                    "source": "email",
                    "output_type": "email",
                    "email_type": "new",
                    "original_message": metadata.get("original_message") if metadata else None,
                    "new_email_message": {
                        "recipients": dev_emails,
                        "subject": subject,
                        "body": body
                    }
                },
                {"response": body}
            )
            return ToolExecutionResponse(
                status="success",
                result=f"Bug report sent successfully to {', '.join(dev_emails)}."
            )
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

    return [reply_to_user_via_email, send_new_email_as_praxos_bot,report_bug_to_developers]
