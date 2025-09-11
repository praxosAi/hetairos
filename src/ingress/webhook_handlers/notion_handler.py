from fastapi import APIRouter, Request, HTTPException
from src.core.event_queue import event_queue
import json

router = APIRouter()

@router.post("/notion")
async def handle_notion_webhook(request: Request):
    """Handles incoming Notion webhooks."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Notion sends a challenge for URL verification
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Process other events
    event_type = data.get("event", {}).get("type")
    if not event_type:
        raise HTTPException(status_code=400, detail="Missing event type")

    # For now, we'll just enqueue the whole event
    # In a real-world scenario, you'd parse this more carefully
    event = {
        "source": "notion",
        "payload": data,
        "metadata": {
            "event_type": event_type
        }
    }

    await event_queue.enqueue_event(event)

    return {"status": "ok"}
