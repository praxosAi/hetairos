import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from src.integrations.trello.trello_client import TrelloIntegration
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

def create_trello_tools(trello_client: TrelloIntegration) -> List:
    """Create a comprehensive suite of Trello-related tools for the LangGraph agent."""

    @tool
    async def list_trello_boards() -> ToolExecutionResponse:
        """
        Lists all Trello boards accessible to the user.
        Use this as the first step to understand the user's Trello workspace structure.
        Returns board IDs, names, and URLs.
        """
        logger.info("Listing Trello boards...")
        try:
            boards = await trello_client.list_boards()
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"boards": boards})
            )
            logger.info(f"Listed {len(boards)} Trello boards")
            return response
        except Exception as e:
            logger.error(f"Error listing Trello boards: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_trello_board_details(board_id: str) -> ToolExecutionResponse:
        """
        Gets detailed information about a specific Trello board.
        Use this to understand board structure including lists and settings.

        Args:
            board_id: The ID of the board to retrieve
        """
        logger.info(f"Getting Trello board details: {board_id}")
        try:
            board = await trello_client.get_board(board_id)
            lists = await trello_client.list_lists(board_id)
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
        except Exception as e:
            logger.error(f"Error getting Trello board details: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def list_trello_cards(board_id: str = None, list_id: str = None) -> ToolExecutionResponse:
        """
        Lists all cards on a Trello board or in a specific list.
        Provide either board_id to get all cards on a board, or list_id to get cards in a specific list.

        Args:
            board_id: The ID of the board (optional if list_id is provided)
            list_id: The ID of the list (optional if board_id is provided)
        """
        logger.info(f"Listing Trello cards for board_id={board_id}, list_id={list_id}")
        try:
            cards = await trello_client.list_cards(board_id=board_id, list_id=list_id)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"cards": cards})
            )
            logger.info(f"Listed {len(cards)} Trello cards")
            return response
        except Exception as e:
            logger.error(f"Error listing Trello cards: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_trello_card(card_id: str) -> ToolExecutionResponse:
        """
        Gets detailed information about a specific Trello card including description,
        due date, labels, checklists, and comments.

        Args:
            card_id: The ID of the card to retrieve
        """
        logger.info(f"Getting Trello card: {card_id}")
        try:
            card = await trello_client.get_card(card_id)
            checklists = await trello_client.get_checklists(card_id)
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
        except Exception as e:
            logger.error(f"Error getting Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_card(
        list_id: str,
        name: str,
        description: str = "",
        due: Optional[str] = None,
        pos: str = "bottom"
    ) -> ToolExecutionResponse:
        """
        Creates a new card in a Trello list.

        Args:
            list_id: The ID of the list where the card should be created
            name: The name/title of the card
            description: The card description (optional)
            due: Due date in ISO 8601 format, e.g., "2024-12-31T23:59:59.000Z" (optional)
            pos: Position in list - "top", "bottom", or a positive number (default: "bottom")
        """
        logger.info(f"Creating Trello card: {name} in list {list_id}")
        try:
            card = await trello_client.create_card(
                list_id=list_id,
                name=name,
                description=description,
                due=due,
                pos=pos
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Created Trello card: {card['id']}")
            return response
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
        list_id: Optional[str] = None
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
        """
        logger.info(f"Updating Trello card: {card_id}")
        try:
            card = await trello_client.update_card(
                card_id=card_id,
                name=name,
                description=description,
                due=due,
                due_complete=due_complete,
                list_id=list_id
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Updated Trello card: {card_id}")
            return response
        except Exception as e:
            logger.error(f"Error updating Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def move_trello_card(card_id: str, list_id: str, pos: str = "bottom") -> ToolExecutionResponse:
        """
        Moves a Trello card to a different list.

        Args:
            card_id: The ID of the card to move
            list_id: The ID of the destination list
            pos: Position in the new list - "top", "bottom", or a positive number (default: "bottom")
        """
        logger.info(f"Moving Trello card {card_id} to list {list_id}")
        try:
            card = await trello_client.update_card(
                card_id=card_id,
                list_id=list_id,
                pos=pos
            )
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"card": card})
            )
            logger.info(f"Moved Trello card {card_id} to list {list_id}")
            return response
        except Exception as e:
            logger.error(f"Error moving Trello card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def add_trello_comment(card_id: str, text: str) -> ToolExecutionResponse:
        """
        Adds a comment to a Trello card.

        Args:
            card_id: The ID of the card to comment on
            text: The comment text
        """
        logger.info(f"Adding comment to Trello card: {card_id}")
        try:
            comment = await trello_client.add_comment(card_id, text)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"comment": comment})
            )
            logger.info(f"Added comment to Trello card: {card_id}")
            return response
        except Exception as e:
            logger.error(f"Error adding Trello comment: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def search_trello(query: str, model_types: str = "cards,boards") -> ToolExecutionResponse:
        """
        Searches Trello for cards, boards, and other items matching a query.

        Args:
            query: The search query
            model_types: Comma-separated types to search - "cards", "boards", "organizations" (default: "cards,boards")
        """
        logger.info(f"Searching Trello for: {query}")
        try:
            types_list = [t.strip() for t in model_types.split(',')]
            results = await trello_client.search(query, types_list)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps(results)
            )
            logger.info(f"Trello search completed for query: {query}")
            return response
        except Exception as e:
            logger.error(f"Error searching Trello: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_checklist(card_id: str, checklist_name: str, items: Optional[List[str]] = None) -> ToolExecutionResponse:
        """
        Creates a checklist on a Trello card, optionally with initial items.

        Args:
            card_id: The ID of the card to add the checklist to
            checklist_name: Name of the checklist
            items: List of item names to add to the checklist (optional)
        """
        logger.info(f"Creating Trello checklist on card: {card_id}")
        try:
            checklist = await trello_client.create_checklist(card_id, checklist_name)

            # Add items if provided
            if items:
                for item_name in items:
                    await trello_client.add_checklist_item(checklist['id'], item_name)

            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"checklist": checklist})
            )
            logger.info(f"Created Trello checklist: {checklist['id']}")
            return response
        except Exception as e:
            logger.error(f"Error creating Trello checklist: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_board(name: str, description: str = "") -> ToolExecutionResponse:
        """
        Creates a new Trello board.

        Args:
            name: Name of the board
            description: Board description (optional)
        """
        logger.info(f"Creating Trello board: {name}")
        try:
            board = await trello_client.create_board(name, description)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"board": board})
            )
            logger.info(f"Created Trello board: {board['id']}")
            return response
        except Exception as e:
            logger.error(f"Error creating Trello board: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def create_trello_list(board_id: str, list_name: str, pos: str = "bottom") -> ToolExecutionResponse:
        """
        Creates a new list on a Trello board.

        Args:
            board_id: The ID of the board
            list_name: Name of the list
            pos: Position - "top", "bottom", or a positive number (default: "bottom")
        """
        logger.info(f"Creating Trello list: {list_name} on board {board_id}")
        try:
            trello_list = await trello_client.create_list(board_id, list_name, pos)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"list": trello_list})
            )
            logger.info(f"Created Trello list: {trello_list['id']}")
            return response
        except Exception as e:
            logger.error(f"Error creating Trello list: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_board_members(board_id: str) -> ToolExecutionResponse:
        """
        Gets all members of a Trello board. Use this to find member IDs for assigning cards.

        Args:
            board_id: The ID of the board
        """
        logger.info(f"Getting Trello board members: {board_id}")
        try:
            members = await trello_client.get_board_members(board_id)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"members": members})
            )
            logger.info(f"Retrieved {len(members)} board members")
            return response
        except Exception as e:
            logger.error(f"Error getting board members: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def assign_member_to_card(card_id: str, member_id: str) -> ToolExecutionResponse:
        """
        Assigns a member to a Trello card. Use get_board_members to find the member_id first.

        Args:
            card_id: The ID of the card
            member_id: The ID of the member to assign
        """
        logger.info(f"Assigning member {member_id} to card {card_id}")
        try:
            result = await trello_client.add_member_to_card(card_id, member_id)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"result": result})
            )
            logger.info(f"Assigned member {member_id} to card {card_id}")
            return response
        except Exception as e:
            logger.error(f"Error assigning member to card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def unassign_member_from_card(card_id: str, member_id: str) -> ToolExecutionResponse:
        """
        Removes a member assignment from a Trello card.

        Args:
            card_id: The ID of the card
            member_id: The ID of the member to unassign
        """
        logger.info(f"Removing member {member_id} from card {card_id}")
        try:
            result = await trello_client.remove_member_from_card(card_id, member_id)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"result": result})
            )
            logger.info(f"Removed member {member_id} from card {card_id}")
            return response
        except Exception as e:
            logger.error(f"Error removing member from card: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def get_card_members(card_id: str) -> ToolExecutionResponse:
        """
        Gets all members currently assigned to a Trello card.

        Args:
            card_id: The ID of the card
        """
        logger.info(f"Getting members for card {card_id}")
        try:
            members = await trello_client.get_card_members(card_id)
            response = ToolExecutionResponse(
                status="success",
                result=json.dumps({"members": members})
            )
            logger.info(f"Retrieved {len(members)} card members")
            return response
        except Exception as e:
            logger.error(f"Error getting card members: {e}", exc_info=True)
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [
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
        get_card_members
    ]
