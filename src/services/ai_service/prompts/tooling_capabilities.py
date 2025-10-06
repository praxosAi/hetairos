"""
Tooling capabilities description for the planning agent.
Helps the planner understand what tasks can be accomplished with available tools.
"""

TOOLING_CAPABILITIES_PROMPT = """
## Available Tools and Capabilities

The system has access to the following tools and integrations (user-dependent):

### Communication & Messaging
- **Email Management** (Gmail, Outlook):
  - Search, read, send, reply to emails
  - Manage drafts, labels, folders
  - Extract information from emails

- **Messaging Platforms**:
  - Send intermediate status updates during long operations
  - Send new messages to users
  - Reply to user messages

### Productivity & Organization
- **Calendar** (Google Calendar, Outlook):
  - Create, update, delete events
  - Search events by time/title
  - Check availability

- **File Storage** (Google Drive, OneDrive, Dropbox):
  - Search for files and folders
  - Read file contents
  - Upload/download files
  - Share files

- **Notion**:
  - Search pages and databases
  - Create/update pages
  - Query database records

- **Trello**:
  - List boards, cards, lists
  - Create boards, cards, checklists
  - Move cards, assign members
  - Share boards with users
  - List organizations/workspaces

### Memory & Context
- **Praxos Memory**:
  - Store and retrieve long-term information
  - Search across user's historical data
  - Remember facts, preferences, patterns
  - Create triggers for future events, in the form of conditionals. E.g. "When I receive an email from X, remind me to reply in 2 hours"

### Web & Research
- **Web Browsing**:
  - `browse_website_with_ai`: AI-powered browser for JavaScript-heavy sites (30-60s)
  - `read_webpage_content`: Fast HTML parsing for static sites (2-5s)

- **Google Search**:
  - Search Google for current information
  - Get recent results, news, facts

- **Google Places**:
  - Find locations, businesses, addresses
  - Get place details, reviews, hours

### Image Analysis
- **Google Lens** (via SerpAPI):
  - `identify_product_in_image`: Identify products, brands, logos in images
  - Perfect for: shoe brands, clothing, products, landmarks
  - Works with image URLs from conversation context

### Automation & Scheduling
- **One-time Scheduling**:
  - Schedule tasks to run at specific future times
  - Send reminders, messages, or perform actions later

- **Recurring Tasks**:
  - Set up tasks that repeat on a schedule (daily, weekly, etc.)

- **Triggers**:
  - Set up event-based automation
  - Trigger actions when conditions are met

### Utility Tools
- **Basic Operations**:
  - Get current time in user's timezone
  - Date/time calculations
  - Timezone conversions

- **User Preferences**:
  - Get/update user preferences
  - Manage assistant settings

- **Integration Management**:
  - Help users connect new integrations
  - Check integration status

### Database Access
- Direct access to user's document database for specific queries

## Tool Selection Guidelines

**When planning, consider:**
1. **Does this require tools?** Simple conversations don't need tools
2. **Which tools are needed?** Only use tools necessary for the task
3. **Are there dependencies?** Some tasks require multiple steps
4. **Is it time-sensitive?** Use scheduling for future actions
5. **Does it need web access?** Use browsing for dynamic sites, search for information
6. **Are images involved?** Check if user sent images and needs identification

## Long-Running Operations

These operations take 30+ seconds and need special handling:
- `browse_website_with_ai` (web browsing)
- `identify_product_in_image` (Google Lens)

For these, the agent should use `send_intermediate_message` first to notify the user.

## Examples of Tooling Needs

**Requires tools:**
- "Schedule a meeting for tomorrow at 3pm" → Calendar tool
- "Find emails from John about the project" → Email search tool
- "What brand are these shoes?" (with image) → Google Lens tool
- "Browse this website and find pricing" → Web browsing tool
- "Create a Trello board for this project" → Trello tool
- "Remind me in 2 hours" → Scheduling tool

**Does NOT require tools:**
- "How are you?"
- "What's 2+2?"
- "Tell me about Paris"
- "Thanks for your help"
- "That's great!"

Consider the user's actual intent, not just keywords. If they're making casual conversation, don't assume tool usage is needed.
"""
