import asyncio
import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from src.ingress.webhook_handlers import whatsapp_handler
from src.ingress.webhook_handlers import http_handler
from src.ingress.webhook_handlers import gmail_handler
from src.ingress.webhook_handlers import telegram_handler
from src.ingress.webhook_handlers import notion_handler
from src.ingress.webhook_handlers import outlook_handler
from src.ingress.webhook_handlers import imessage_handler
from src.ingress.webhook_handlers import google_calendar_handler
from src.ingress.webhook_handlers import google_drive_handler
from src.ingress.webhook_handlers import microsoft_calendar_handler
from src.ingress.webhook_handlers import onedrive_handler
from src.ingress.webhook_handlers import trello_handler
from src.ingress.webhook_handlers import dropbox_handler
from src.ingress.webhook_handlers import slack_handler
from src.core import suspended_event_queue
from src.utils.logging.base_logger import request_id_var, user_id_var, modality_var
from src.utils.redis_client import subscribe_to_channel
from src.utils.logging import setup_logger

# Check an environment variable to decide on log format
# In your deployment (e.g., Dockerfile or Kubernetes YAML), set JSON_LOGGING="true"

logger = setup_logger(__name__)

app = FastAPI(title="Hetairoi Agent Ingress")

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    # Generate a unique request ID for each incoming request
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    # Set default modality. This can be overridden in specific handlers.
    modality_var.set("http")

    logger.info(f"Request started: {request.method} {request.url.path}")

    response = await call_next(request)
    
    logger.info(f"Request finished: {response.status_code}")
    
    # Clean up context variables
    request_id_var.set('SYSTEM_LEVEL')
    user_id_var.set('SYSTEM_LEVEL')
    modality_var.set('SYSTEM_LEVEL')
    
    return response

# Mount the webhook handlers
# Messaging
app.include_router(whatsapp_handler.router, prefix="/webhooks")
app.include_router(telegram_handler.router, prefix="/webhooks")
app.include_router(slack_handler.router, prefix="/webhooks")
app.include_router(imessage_handler.router, prefix="/webhooks")

# Email
app.include_router(gmail_handler.router, prefix="/webhooks")
app.include_router(outlook_handler.router, prefix="/webhooks")

# Calendar
app.include_router(google_calendar_handler.router, prefix="/webhooks")
app.include_router(microsoft_calendar_handler.router, prefix="/webhooks")

# Storage/Drive
app.include_router(google_drive_handler.router, prefix="/webhooks")
app.include_router(onedrive_handler.router, prefix="/webhooks")
app.include_router(dropbox_handler.router, prefix="/webhooks")

# Productivity
app.include_router(notion_handler.router, prefix="/webhooks")
app.include_router(trello_handler.router, prefix="/webhooks")

# General HTTP ingress
app.include_router(http_handler.router, prefix="/ingress")

# Admin
app.include_router(suspended_event_queue.router, prefix="/admin/suspended-events")

@app.get("/")
async def root():
    return {"message": "Hetairoi Agent Ingress is running."}


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Cookie
from typing import Optional



def is_valid_jwt(token: str) -> bool:
    # TODO: verify signature, exp, aud, iss, etc.
    return bool(token and len(token) > 10)

def extract_jwt_from_ws(ws: WebSocket, cookie_name: str = "praxos_session") -> Optional[str]:
    # 1) Subprotocol (browser-friendly, no custom headers needed)
    proto = ws.headers.get("sec-websocket-protocol")
    if proto and is_valid_jwt(proto):
        return proto

    # 2) Cookie (auto-sent by browser on same origin)
    cookie = ws.cookies.get(cookie_name)
    if cookie and is_valid_jwt(cookie):
        return cookie

    # 3) Authorization header (for non-browser clients like wscat/curl)
    auth = ws.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if is_valid_jwt(token):
            return token

    return None



@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, praxos_session: Optional[str] = Cookie(default=None)):
    # Accept handshake first, and echo subprotocol if present (required by browsers)
    requested_proto = ws.headers.get("sec-websocket-protocol") or ""
    await ws.accept(subprotocol=requested_proto if requested_proto else None)

    # Extract JWT from subprotocol, cookie, or Authorization
    token = extract_jwt_from_ws(ws)
    if not token:
        logger.info("No token found, closing websocket")
        # optionally: await ws.send_text("unauthorized")
        await ws.close(code=1008)
        return

    # ---- your normal logic below ----
    pubsub = None
    try:
        channel = f"ws-out:{token}"  # ensure this stays reasonable length
        pubsub = await subscribe_to_channel(channel)

        async def redis_listener():
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=None
                )
                if msg:
                    data = msg["data"]
                    if isinstance(data, bytes):
                        try:
                            data = data.decode("utf-8", errors="replace")
                        except Exception:
                            data = str(data)
                    await ws.send_text(data)
                else:
                    # avoid busy loop when timeout=None yields no message
                    await asyncio.sleep(0.01)

        async def client_listener():
            while True:
                # drain client frames (optional: handle pings, simple cmds, etc.)
                await ws.receive_text()

        # Run both until one completes
        done, pending = await asyncio.wait(
            [asyncio.create_task(redis_listener()),
             asyncio.create_task(client_listener())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

    except WebSocketDisconnect:
        logger.info("WS disconnect token=%s", token[:8])
    except Exception:
        logger.exception("WS error token=%s", token[:8])
    finally:
        if pubsub:
            await pubsub.close()
        await ws.close()
        logger.info("WS closed token=%s", token[:8])
# @app.websocket("/ws")
# async def websocket_endpoint(ws: WebSocket):
#     # Accept handshake ONCE, immediately
#     await ws.accept()

#     # Auth: read token from query (or switch to cookie/subprotocol later)
#     # token = ws.query_params.get("token")
#     # if not token:
#     await ws.close(code=1008)  # policy violation / unauthorized
#     return

    # logger.info("WS accepted; token prefix=%s", token[:8])

    



# dump_routes(app)