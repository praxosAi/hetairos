import logging
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timedelta
from src.integrations.base_integration import BaseIntegration
from src.services.integration_service import integration_service
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class TrelloIntegration(BaseIntegration):
    """Trello integration client for managing boards, lists, and cards."""

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.api_key: Optional[str] = None
        self.token: Optional[str] = None
        self.base_url = "https://api.trello.com/1"

    async def authenticate(self) -> bool:
        """Fetches the Trello API key and token from integration service."""
        token_info = await integration_service.get_integration_token(self.user_id, 'trello')
        if not token_info or 'access_token' not in token_info:
            logger.error(f"Failed to retrieve Trello token for user {self.user_id}")
            return False

        # Get API key from environment (this is the app's key, not user-specific)
        import os
        self.api_key = os.getenv('TRELLO_API_KEY')
        if not self.api_key:
            logger.error("TRELLO_API_KEY not found in environment")
            return False

        self.token = token_info['access_token']
        logger.info(f"Successfully authenticated Trello for user {self.user_id}")
        return True

    async def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
        """Makes an authenticated request to the Trello API."""
        if not self.api_key or not self.token:
            raise Exception("Trello client not authenticated")

        url = f"{self.base_url}/{endpoint}"
        request_params = {'key': self.api_key, 'token': self.token}
        if params:
            request_params.update(params)

        async with httpx.AsyncClient() as client:
            if method.upper() == 'GET':
                response = await client.get(url, params=request_params)
            elif method.upper() == 'POST':
                response = await client.post(url, params=request_params, json=data)
            elif method.upper() == 'PUT':
                response = await client.put(url, params=request_params, json=data)
            elif method.upper() == 'DELETE':
                response = await client.delete(url, params=request_params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.text else {}

    async def fetch_recent_data(self, since: datetime = None) -> List[Dict]:
        """Fetches recently updated cards across all boards."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        boards = await self.list_boards()
        recent_cards = []

        for board in boards:
            cards = await self.list_cards(board['id'])
            for card in cards:
                # Filter by date modified
                date_last_activity = datetime.fromisoformat(card.get('dateLastActivity', '').replace('Z', '+00:00'))
                if date_last_activity >= since:
                    recent_cards.append({
                        'id': card['id'],
                        'name': card['name'],
                        'desc': card.get('desc', ''),
                        'url': card['url'],
                        'board_id': board['id'],
                        'board_name': board['name'],
                        'list_id': card.get('idList'),
                        'due': card.get('due'),
                        'due_complete': card.get('dueComplete', False),
                        'labels': card.get('labels', []),
                        'dateLastActivity': card.get('dateLastActivity')
                    })

        return recent_cards

    async def get_member_info(self) -> Dict[str, Any]:
        """Gets information about the authenticated member."""
        return await self._make_request('GET', 'members/me')

    async def list_organizations(self) -> List[Dict[str, Any]]:
        """Lists all organizations/workspaces accessible to the authenticated user."""
        orgs = await self._make_request('GET', 'members/me/organizations')
        return [{'id': o['id'], 'name': o['name'], 'displayName': o['displayName'], 'url': o.get('url')} for o in orgs]

    async def list_boards(self, organization_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all boards accessible to the authenticated user, optionally filtered by organization."""
        if organization_id:
            boards = await self._make_request('GET', f'organizations/{organization_id}/boards')
        else:
            boards = await self._make_request('GET', 'members/me/boards')
        return [{'id': b['id'], 'name': b['name'], 'url': b['url'], 'closed': b.get('closed', False), 'idOrganization': b.get('idOrganization')} for b in boards]

    async def get_board(self, board_id: str) -> Dict[str, Any]:
        """Gets details about a specific board."""
        return await self._make_request('GET', f'boards/{board_id}')

    async def create_board(self, name: str, description: str = "", id_organization: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new board, optionally in a specific organization/workspace."""
        data = {
            'name': name,
            'desc': description
        }
        if id_organization:
            data['idOrganization'] = id_organization
        return await self._make_request('POST', 'boards', data=data)

    async def list_lists(self, board_id: str) -> List[Dict[str, Any]]:
        """Lists all lists on a board."""
        return await self._make_request('GET', f'boards/{board_id}/lists')

    async def create_list(self, board_id: str, name: str, pos: str = 'bottom') -> Dict[str, Any]:
        """Creates a new list on a board."""
        return await self._make_request('POST', 'lists', data={
            'name': name,
            'idBoard': board_id,
            'pos': pos
        })

    async def list_cards(self, board_id: str = None, list_id: str = None) -> List[Dict[str, Any]]:
        """Lists all cards on a board or in a specific list."""
        if list_id:
            return await self._make_request('GET', f'lists/{list_id}/cards')
        elif board_id:
            return await self._make_request('GET', f'boards/{board_id}/cards')
        else:
            raise ValueError("Either board_id or list_id must be provided")

    async def get_card(self, card_id: str) -> Dict[str, Any]:
        """Gets details about a specific card."""
        return await self._make_request('GET', f'cards/{card_id}')

    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
        due: Optional[str] = None,
        labels: Optional[List[str]] = None,
        members: Optional[List[str]] = None,
        pos: str = 'bottom'
    ) -> Dict[str, Any]:
        """Creates a new card in a list."""
        data = {
            'idList': list_id,
            'name': name,
            'desc': description,
            'pos': pos
        }

        if due:
            data['due'] = due
        if labels:
            data['idLabels'] = ','.join(labels)
        if members:
            data['idMembers'] = ','.join(members)

        return await self._make_request('POST', 'cards', data=data)

    async def update_card(
        self,
        card_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        due: Optional[str] = None,
        due_complete: Optional[bool] = None,
        list_id: Optional[str] = None,
        pos: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates an existing card."""
        data = {}

        if name is not None:
            data['name'] = name
        if description is not None:
            data['desc'] = description
        if due is not None:
            data['due'] = due
        if due_complete is not None:
            data['dueComplete'] = due_complete
        if list_id is not None:
            data['idList'] = list_id
        if pos is not None:
            data['pos'] = pos

        return await self._make_request('PUT', f'cards/{card_id}', data=data)

    async def delete_card(self, card_id: str) -> Dict[str, Any]:
        """Deletes a card."""
        return await self._make_request('DELETE', f'cards/{card_id}')

    async def add_comment(self, card_id: str, text: str) -> Dict[str, Any]:
        """Adds a comment to a card."""
        return await self._make_request('POST', f'cards/{card_id}/actions/comments', data={'text': text})

    async def search(self, query: str, model_types: List[str] = None, id_organizations: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Searches Trello for cards, boards, etc.

        Args:
            query: Search query
            model_types: Types to search (e.g., ['cards', 'boards', 'organizations'])
            id_organizations: Optional list of organization IDs to scope the search
        """
        params = {'query': query}
        if model_types:
            params['modelTypes'] = ','.join(model_types)
        if id_organizations:
            params['idOrganizations'] = ','.join(id_organizations)

        return await self._make_request('GET', 'search', params=params)

    async def get_board_labels(self, board_id: str) -> List[Dict[str, Any]]:
        """Gets all labels defined on a board."""
        return await self._make_request('GET', f'boards/{board_id}/labels')

    async def create_label(self, board_id: str, name: str, color: str) -> Dict[str, Any]:
        """Creates a new label on a board."""
        return await self._make_request('POST', 'labels', data={
            'name': name,
            'color': color,
            'idBoard': board_id
        })

    async def add_label_to_card(self, card_id: str, label_id: str) -> Dict[str, Any]:
        """Adds a label to a card."""
        return await self._make_request('POST', f'cards/{card_id}/idLabels', data={'value': label_id})

    async def get_checklists(self, card_id: str) -> List[Dict[str, Any]]:
        """Gets all checklists on a card."""
        return await self._make_request('GET', f'cards/{card_id}/checklists')

    async def create_checklist(self, card_id: str, name: str) -> Dict[str, Any]:
        """Creates a new checklist on a card."""
        return await self._make_request('POST', 'checklists', data={
            'idCard': card_id,
            'name': name
        })

    async def add_checklist_item(self, checklist_id: str, name: str, checked: bool = False) -> Dict[str, Any]:
        """Adds an item to a checklist."""
        return await self._make_request('POST', f'checklists/{checklist_id}/checkItems', data={
            'name': name,
            'checked': checked
        })

    async def get_board_members(self, board_id: str) -> List[Dict[str, Any]]:
        """Gets all members of a board."""
        return await self._make_request('GET', f'boards/{board_id}/members')

    async def add_member_to_card(self, card_id: str, member_id: str) -> Dict[str, Any]:
        """Assigns a member to a card."""
        return await self._make_request('POST', f'cards/{card_id}/idMembers', data={'value': member_id})

    async def remove_member_from_card(self, card_id: str, member_id: str) -> Dict[str, Any]:
        """Removes a member from a card."""
        return await self._make_request('DELETE', f'cards/{card_id}/idMembers/{member_id}')

    async def get_card_members(self, card_id: str) -> List[Dict[str, Any]]:
        """Gets all members assigned to a card."""
        return await self._make_request('GET', f'cards/{card_id}/members')

    async def invite_member_to_board(self, board_id: str, email: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Invites a member to a board by email address."""
        data = {}
        if full_name:
            data['fullName'] = full_name
        return await self._make_request('PUT', f'boards/{board_id}/members', params={'email': email}, data=data)
