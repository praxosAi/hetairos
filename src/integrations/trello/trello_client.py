import asyncio
import httpx
import os
from typing import List, Dict, Any, Optional, Tuple
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
        self.tokens: Dict[str, str] = {}
        self.connected_accounts: List[str] = []
        self.base_url = "https://api.trello.com/1"

    async def authenticate(self) -> bool:
        """
        Authenticates all connected Trello accounts for the user.
        Each account gets its own token stored.
        """
        logger.info(f"Authenticating all Trello accounts for user {self.user_id}")

        # Get API key from environment (shared across all accounts)
        self.api_key = os.getenv('TRELLO_API_KEY')
        if not self.api_key:
            logger.error("TRELLO_API_KEY not found in environment")
            return False

        integration_records = await integration_service.get_all_integrations_for_user_by_name(
            self.user_id, 'trello'
        )

        if not integration_records:
            logger.warning(f"No Trello integrations found for user {self.user_id}")
            return False

        auth_tasks = [
            self._authenticate_one_account(record)
            for record in integration_records if record
        ]

        results = await asyncio.gather(*auth_tasks)
        return any(results)

    async def _authenticate_one_account(self, integration_record: Dict) -> bool:
        """Authenticates a single Trello account and stores its token."""
        account_id = integration_record.get('connected_account')  # Username or email
        integration_id = integration_record.get('_id')

        try:
            token_info = await integration_service.get_integration_token(
                self.user_id, 'trello', integration_id=integration_id
            )

            if not token_info or 'access_token' not in token_info:
                logger.error(f"Failed to retrieve token for Trello account {account_id}")
                return False

            # Store token for this account
            self.tokens[account_id] = token_info['access_token']
            if account_id not in self.connected_accounts:
                self.connected_accounts.append(account_id)

            logger.info(f"Successfully authenticated Trello account {account_id}")
            return True

        except Exception as e:
            logger.error(f"Trello authentication failed for account {account_id}: {e}")
            return False

    def get_connected_accounts(self) -> List[str]:
        """Returns a list of successfully authenticated Trello accounts."""
        return self.connected_accounts

    def _get_token_for_account(self, account: Optional[str] = None) -> Tuple[str, str]:
        """
        Retrieves the Trello token and resolved account identifier.
        Handles default logic for single-account users.
        """
        if account:
            token = self.tokens.get(account)
            if not token:
                raise ValueError(
                    f"Account '{account}' is not authenticated. "
                    f"Available accounts: {self.connected_accounts}"
                )
            return token, account

        if len(self.connected_accounts) == 1:
            default_account = self.connected_accounts[0]
            return self.tokens[default_account], default_account

        if len(self.connected_accounts) == 0:
            raise Exception("No authenticated Trello accounts found for this user.")

        raise ValueError(
            f"Multiple Trello accounts exist. Specify which account to use with "
            f"the 'account' parameter. Available accounts: {self.connected_accounts}"
        )

    async def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Makes an authenticated request to the Trello API for a specific account."""
        if not self.api_key:
            raise Exception("Trello API key not initialized")

        token, resolved_account = self._get_token_for_account(account)

        url = f"{self.base_url}/{endpoint}"
        request_params = {'key': self.api_key, 'token': token}
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

    async def fetch_recent_data(self, *, account: Optional[str] = None, since: Optional[datetime] = None) -> List[Dict]:
        """Fetches recently updated cards across all boards for a specific Trello account."""
        _, resolved_account = self._get_token_for_account(account)

        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        logger.info(f"Fetching recent cards for Trello account {resolved_account} since {since}")

        boards = await self.list_boards(account=resolved_account)
        recent_cards = []

        for board in boards:
            cards = await self.list_cards(board_id=board['id'], account=resolved_account)
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
                        'dateLastActivity': card.get('dateLastActivity'),
                        'account': resolved_account
                    })

        return recent_cards

    async def get_member_info(self, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Gets information about the authenticated member for a specific Trello account."""
        return await self._make_request('GET', 'members/me', account=account)

    async def list_organizations(self, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all organizations/workspaces accessible to a specific Trello account."""
        orgs = await self._make_request('GET', 'members/me/organizations', account=account)
        return [{'id': o['id'], 'name': o['name'], 'displayName': o['displayName'], 'url': o.get('url')} for o in orgs]

    async def list_boards(self, organization_id: Optional[str] = None, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all boards accessible to a specific Trello account, optionally filtered by organization."""
        if organization_id:
            boards = await self._make_request('GET', f'organizations/{organization_id}/boards', account=account)
        else:
            boards = await self._make_request('GET', 'members/me/boards', account=account)
        return [{'id': b['id'], 'name': b['name'], 'url': b['url'], 'closed': b.get('closed', False), 'idOrganization': b.get('idOrganization')} for b in boards]

    async def get_board(self, board_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Gets details about a specific board for a specific Trello account."""
        return await self._make_request('GET', f'boards/{board_id}', account=account)

    async def create_board(self, name: str, description: str = "", id_organization: Optional[str] = None, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new board for a specific Trello account, optionally in a specific organization/workspace."""
        data = {
            'name': name,
            'desc': description
        }
        if id_organization:
            data['idOrganization'] = id_organization
        return await self._make_request('POST', 'boards', data=data, account=account)

    async def list_lists(self, board_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all lists on a board for a specific Trello account."""
        return await self._make_request('GET', f'boards/{board_id}/lists', account=account)

    async def create_list(self, board_id: str, name: str, pos: str = 'bottom', *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new list on a board for a specific Trello account."""
        return await self._make_request('POST', 'lists', data={
            'name': name,
            'idBoard': board_id,
            'pos': pos
        }, account=account)

    async def list_cards(self, board_id: str = None, list_id: str = None, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all cards on a board or in a specific list for a specific Trello account."""
        if list_id:
            return await self._make_request('GET', f'lists/{list_id}/cards', account=account)
        elif board_id:
            return await self._make_request('GET', f'boards/{board_id}/cards', account=account)
        else:
            raise ValueError("Either board_id or list_id must be provided")

    async def get_card(self, card_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Gets details about a specific card for a specific Trello account."""
        return await self._make_request('GET', f'cards/{card_id}', account=account)

    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
        due: Optional[str] = None,
        labels: Optional[List[str]] = None,
        members: Optional[List[str]] = None,
        pos: str = 'bottom',
        *,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new card in a list for a specific Trello account."""
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

        return await self._make_request('POST', 'cards', data=data, account=account)

    async def update_card(
        self,
        card_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        due: Optional[str] = None,
        due_complete: Optional[bool] = None,
        list_id: Optional[str] = None,
        pos: Optional[str] = None,
        *,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates an existing card for a specific Trello account."""
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

        return await self._make_request('PUT', f'cards/{card_id}', data=data, account=account)

    async def delete_card(self, card_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Deletes a card for a specific Trello account."""
        return await self._make_request('DELETE', f'cards/{card_id}', account=account)

    async def add_comment(self, card_id: str, text: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Adds a comment to a card for a specific Trello account."""
        return await self._make_request('POST', f'cards/{card_id}/actions/comments', data={'text': text}, account=account)

    async def search(self, query: str, model_types: List[str] = None, id_organizations: Optional[List[str]] = None, *, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Searches Trello for cards, boards, etc. for a specific Trello account.

        Args:
            query: Search query
            model_types: Types to search (e.g., ['cards', 'boards', 'organizations'])
            id_organizations: Optional list of organization IDs to scope the search
            account: Optional account identifier
        """
        params = {'query': query}
        if model_types:
            params['modelTypes'] = ','.join(model_types)
        if id_organizations:
            params['idOrganizations'] = ','.join(id_organizations)

        return await self._make_request('GET', 'search', params=params, account=account)

    async def get_board_labels(self, board_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all labels defined on a board for a specific Trello account."""
        return await self._make_request('GET', f'boards/{board_id}/labels', account=account)

    async def create_label(self, board_id: str, name: str, color: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new label on a board for a specific Trello account."""
        return await self._make_request('POST', 'labels', data={
            'name': name,
            'color': color,
            'idBoard': board_id
        }, account=account)

    async def add_label_to_card(self, card_id: str, label_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Adds a label to a card for a specific Trello account."""
        return await self._make_request('POST', f'cards/{card_id}/idLabels', data={'value': label_id}, account=account)

    async def get_checklists(self, card_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all checklists on a card for a specific Trello account."""
        return await self._make_request('GET', f'cards/{card_id}/checklists', account=account)

    async def create_checklist(self, card_id: str, name: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new checklist on a card for a specific Trello account."""
        return await self._make_request('POST', 'checklists', data={
            'idCard': card_id,
            'name': name
        }, account=account)

    async def add_checklist_item(self, checklist_id: str, name: str, checked: bool = False, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Adds an item to a checklist for a specific Trello account."""
        return await self._make_request('POST', f'checklists/{checklist_id}/checkItems', data={
            'name': name,
            'checked': checked
        }, account=account)

    async def get_board_members(self, board_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all members of a board for a specific Trello account."""
        return await self._make_request('GET', f'boards/{board_id}/members', account=account)

    async def add_member_to_card(self, card_id: str, member_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Assigns a member to a card for a specific Trello account."""
        return await self._make_request('POST', f'cards/{card_id}/idMembers', data={'value': member_id}, account=account)

    async def remove_member_from_card(self, card_id: str, member_id: str, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Removes a member from a card for a specific Trello account."""
        return await self._make_request('DELETE', f'cards/{card_id}/idMembers/{member_id}', account=account)

    async def get_card_members(self, card_id: str, *, account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all members assigned to a card for a specific Trello account."""
        return await self._make_request('GET', f'cards/{card_id}/members', account=account)

    async def invite_member_to_board(self, board_id: str, email: str, full_name: Optional[str] = None, *, account: Optional[str] = None) -> Dict[str, Any]:
        """Invites a member to a board by email address for a specific Trello account."""
        data = {}
        if full_name:
            data['fullName'] = full_name
        return await self._make_request('PUT', f'boards/{board_id}/members', params={'email': email}, data=data, account=account)
