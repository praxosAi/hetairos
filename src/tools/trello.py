import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from src.integrations.trello.trello_client import TrelloIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_trello_tools(trello_client: TrelloIntegration) -> List:
    """Create a comprehensive suite of Trello-related tools for the LangGraph agent with multi-account support."""

    @tool
    async def list_trello_accounts() -> ToolExecutionResponse:
        """
        Lists all connected Trello accounts for the user.
        Use this first to see which Trello accounts are available.
        """
        try:
            accounts = trello_client.get_connected_accounts()
            return ToolExecutionResponse(
                status="success",
                result=json.dumps({"accounts": accounts})
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="list_trello_accounts",
                exception=e,
                integration="Trello"
            )

    @tool
    async def list_trello_organizations(account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Lists all Trello organizations/workspaces accessible to the user.
        Use this to discover available workspaces and their IDs.
        Returns organization IDs, names, and URLs.

        Args:
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info("Listing Trello organizations...")
        try:
            orgs = await trello_client.list_organizations(account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"organizations": orgs})
            )
            logger.info(f"Listed {len(orgs)} Trello organizations")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="list_trello_organizations",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error listing Trello organizations: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="list_trello_organizations",
                exception=e,
                integration="Trello"
            )

    @tool
    async def list_trello_boards(organization_id: Optional[str] = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Lists all Trello boards accessible to the user.
        Use this as the first step to understand the user's Trello workspace structure.
        Returns board IDs, names, URLs, and the organization they belong to.

        Args:
            organization_id: Optional organization/workspace ID to filter boards (returns all boards if not provided)
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Listing Trello boards for organization_id={organization_id}...")
        try:
            boards = await trello_client.list_boards(organization_id=organization_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"boards": boards})
            )
            logger.info(f"Listed {len(boards)} Trello boards")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error listing Trello boards: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_trello_board_details(board_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Gets detailed information about a specific Trello board.
        Use this to understand board structure including lists and settings.

        Args:
            board_id: The ID of the board to retrieve
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Getting Trello board details: {board_id}")
        try:
            board = await trello_client.get_board(board_id, account=account)
            lists = await trello_client.list_lists(board_id, account=account)
            result = {
                "board": board,
                "lists": lists
            }
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps(result)
            )
            logger.info(f"Retrieved board details for {board_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting Trello board details: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def list_trello_cards(board_id: str = None, list_id: str = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Lists all cards on a Trello board or in a specific list.
        Provide either board_id to get all cards on a board, or list_id to get cards in a specific list.

        Args:
            board_id: The ID of the board (optional if list_id is provided)
            list_id: The ID of the list (optional if board_id is provided)
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Listing Trello cards for board_id={board_id}, list_id={list_id}")
        try:
            cards = await trello_client.list_cards(board_id=board_id, list_id=list_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"cards": cards})
            )
            logger.info(f"Listed {len(cards)} Trello cards")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error listing Trello cards: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_trello_card(card_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Gets detailed information about a specific Trello card including description,
        due date, labels, checklists, and comments.

        Args:
            card_id: The ID of the card to retrieve
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Getting Trello card: {card_id}")
        try:
            card = await trello_client.get_card(card_id, account=account)
            checklists = await trello_client.get_checklists(card_id, account=account)
            result = {
                "card": card,
                "checklists": checklists
            }
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps(result)
            )
            logger.info(f"Retrieved card details for {card_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_card(
        list_id: str,
        name: str,
        description: str = "",
        due: Optional[str] = None,
        pos: str = "bottom",
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Creates a new card in a Trello list.

        Args:
            list_id: The ID of the list where the card should be created
            name: The name/title of the card
            description: The card description (optional)
            due: Due date in ISO 8601 format, e.g., "2024-12-31T23:59:59.000Z" (optional)
            pos: Position in list - "top", "bottom", or a positive number (default: "bottom")
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Creating Trello card: {name} in list {list_id}")
        try:
            card = await trello_client.create_card(
                list_id=list_id,
                name=name,
                description=description,
                due=due,
                pos=pos,
                account=account
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Created Trello card: {card['id']}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def update_trello_card(
        card_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        due: Optional[str] = None,
        due_complete: Optional[bool] = None,
        list_id: Optional[str] = None,
        account: Optional[str] = None
    ) -> ToolExecutionResponse:
        """
        Updates an existing Trello card. Only provide the fields you want to update.

        Args:
            card_id: The ID of the card to update
            name: New name for the card (optional)
            description: New description for the card (optional)
            due: New due date in ISO 8601 format (optional)
            due_complete: Whether the due date is complete (optional)
            list_id: Move the card to a different list by providing the new list ID (optional)
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Updating Trello card: {card_id}")
        try:
            card = await trello_client.update_card(
                card_id=card_id,
                name=name,
                description=description,
                due=due,
                due_complete=due_complete,
                list_id=list_id,
                account=account
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Updated Trello card: {card_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error updating Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def move_trello_card(card_id: str, list_id: str, pos: str = "bottom", account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Moves a Trello card to a different list.

        Args:
            card_id: The ID of the card to move
            list_id: The ID of the destination list
            pos: Position in the new list - "top", "bottom", or a positive number (default: "bottom")
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Moving Trello card {card_id} to list {list_id}")
        try:
            card = await trello_client.update_card(
                card_id=card_id,
                list_id=list_id,
                pos=pos,
                account=account
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Moved Trello card {card_id} to list {list_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error moving Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def add_trello_comment(card_id: str, text: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Adds a comment to a Trello card.

        Args:
            card_id: The ID of the card to comment on
            text: The comment text
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Adding comment to Trello card: {card_id}")
        try:
            comment = await trello_client.add_comment(card_id, text, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"comment": comment})
            )
            logger.info(f"Added comment to Trello card: {card_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error adding Trello comment: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def search_trello(query: str, model_types: str = "cards,boards", organization_ids: Optional[str] = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Searches Trello for cards, boards, and other items matching a query.

        Args:
            query: The search query
            model_types: Comma-separated types to search - "cards", "boards", "organizations" (default: "cards,boards")
            organization_ids: Optional comma-separated organization IDs to scope the search to specific workspaces
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Searching Trello for: {query}")
        try:
            types_list = [t.strip() for t in model_types.split(',')]
            orgs_list = [o.strip() for o in organization_ids.split(',')] if organization_ids else None
            results = await trello_client.search(query, types_list, orgs_list, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps(results)
            )
            logger.info(f"Trello search completed for query: {query}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error searching Trello: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_checklist(card_id: str, checklist_name: str, items: Optional[List[str]] = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Creates a checklist on a Trello card, optionally with initial items.

        Args:
            card_id: The ID of the card to add the checklist to
            checklist_name: Name of the checklist
            items: List of item names to add to the checklist (optional)
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Creating Trello checklist on card: {card_id}")
        try:
            checklist = await trello_client.create_checklist(card_id, checklist_name, account=account)

            # Add items if provided
            if items:
                for item_name in items:
                    await trello_client.add_checklist_item(checklist['id'], item_name, account=account)

            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"checklist": checklist})
            )
            logger.info(f"Created Trello checklist: {checklist['id']}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating Trello checklist: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_board(name: str, description: str = "", organization_id: Optional[str] = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Creates a new Trello board.

        Args:
            name: Name of the board
            description: Board description (optional)
            organization_id: ID of the organization/workspace to create the board in (optional, defaults to personal workspace)
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Creating Trello board: {name} in organization {organization_id}")
        try:
            board = await trello_client.create_board(name, description, organization_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"board": board})
            )
            logger.info(f"Created Trello board: {board['id']}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating Trello board: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_list(board_id: str, list_name: str, pos: str = "bottom", account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Creates a new list on a Trello board.

        Args:
            board_id: The ID of the board
            list_name: Name of the list
            pos: Position - "top", "bottom", or a positive number (default: "bottom")
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Creating Trello list: {list_name} on board {board_id}")
        try:
            trello_list = await trello_client.create_list(board_id, list_name, pos, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"list": trello_list})
            )
            logger.info(f"Created Trello list: {trello_list['id']}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating Trello list: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_board_members(board_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Gets all members of a Trello board. Use this to find member IDs for assigning cards.

        Args:
            board_id: The ID of the board
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Getting Trello board members: {board_id}")
        try:
            members = await trello_client.get_board_members(board_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"members": members})
            )
            logger.info(f"Retrieved {len(members)} board members")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting board members: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def assign_member_to_card(card_id: str, member_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Assigns a member to a Trello card. Use get_board_members to find the member_id first.

        Args:
            card_id: The ID of the card
            member_id: The ID of the member to assign
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Assigning member {member_id} to card {card_id}")
        try:
            result = await trello_client.add_member_to_card(card_id, member_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"result": result})
            )
            logger.info(f"Assigned member {member_id} to card {card_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error assigning member to card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def unassign_member_from_card(card_id: str, member_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Removes a member assignment from a Trello card.

        Args:
            card_id: The ID of the card
            member_id: The ID of the member to unassign
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Removing member {member_id} from card {card_id}")
        try:
            result = await trello_client.remove_member_from_card(card_id, member_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"result": result})
            )
            logger.info(f"Removed member {member_id} from card {card_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error removing member from card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_card_members(card_id: str, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Gets all members currently assigned to a Trello card.

        Args:
            card_id: The ID of the card
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Getting members for card {card_id}")
        try:
            members = await trello_client.get_card_members(card_id, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"members": members})
            )
            logger.info(f"Retrieved {len(members)} card members")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error getting card members: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def share_trello_board(board_id: str, email: str, full_name: Optional[str] = None, account: Optional[str] = None) -> ToolExecutionResponse:
        """
        Shares a Trello board with a user by inviting them via email address.
        The user will receive an email invitation to join the board.

        Args:
            board_id: The ID of the board to share
            email: Email address of the person to invite
            full_name: Optional full name of the person being invited
            account: Optional Trello account identifier. If not specified and user has only one Trello account, that account will be used.
        """
        logger.info(f"Sharing board {board_id} with {email}")
        try:
            result = await trello_client.invite_member_to_board(board_id, email, full_name, account=account)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"result": result})
            )
            logger.info(f"Successfully invited {email} to board {board_id}")
            return response
        except ValueError as e:
            return ErrorResponseBuilder.missing_parameter(
                operation="trello_operation",
                param_name="account",
                technical_details=str(e)
            )
        except Exception as e:
            logger.error(f"Error sharing board: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
        list_trello_accounts,
        list_trello_organizations,
        list_trello_boards,
        get_trello_board_details,
        list_trello_cards,
        get_trello_card,
        create_trello_card,
        update_trello_card,
        move_trello_card,
        add_trello_comment,
        search_trello,
        create_trello_checklist,
        create_trello_board,
        create_trello_list,
        get_board_members,
        assign_member_to_card,
        unassign_member_from_card,
        get_card_members,
        share_trello_board
    ]
