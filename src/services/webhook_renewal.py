"""
Webhook renewal service.

Per-user webhook subscriptions issued by Google (Gmail/Drive/Calendar),
Microsoft Graph, and Airtable carry hard TTL caps and must be re-issued
before they expire. This service runs an APScheduler job inside the
hetairos process, scans integrations whose webhooks expire soon, and
re-registers them in place.

Scope:
- Google Gmail watch (7d cap) → re-call users.watch
- Google Drive changes watch (7d cap) → create a new channel, drop the old
- Google Calendar events watch (30d cap) → create a new channel, drop the old
- Microsoft Graph subscriptions (variable) → PATCH /subscriptions/{id}
- Airtable webhooks (7d cap) → POST /webhooks/{id}/refresh

Providers without renewal needs (Notion, Dropbox, HubSpot, Slack, Discord,
Trello) are intentionally ignored.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.utils.database import db_manager
from src.utils.logging import setup_logger
from src.services.integration_service import integration_service

logger = setup_logger(__name__)

# Re-register when the existing subscription expires within this window.
RENEW_WHEN_LESS_THAN = timedelta(hours=24)
SCAN_INTERVAL_MINUTES = 60

# TTLs we ask for at renewal time. Each must stay under the provider's cap.
GOOGLE_DRIVE_TTL = timedelta(days=6)
GOOGLE_CALENDAR_TTL = timedelta(days=25)
MICROSOFT_TTL = timedelta(days=2, hours=22)  # MS messages cap at ~3d


def _parse_expiration(value: Any) -> Optional[datetime]:
    """Best-effort parse for the heterogeneous expiration shapes we store.

    Google Gmail stores epoch ms as string; Calendar/Drive/MS/Airtable use ISO 8601.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, str):
        if value.isdigit():
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        try:
            iso = value.replace("Z", "+00:00")
            return datetime.fromisoformat(iso)
        except ValueError:
            return None
    return None


def _expires_soon(expiration: Optional[datetime]) -> bool:
    if not expiration:
        return False
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=timezone.utc)
    return (expiration - datetime.now(timezone.utc)) <= RENEW_WHEN_LESS_THAN


class WebhookRenewalService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        self.scheduler.add_job(
            self.renew_all,
            IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES),
            id="webhook_renewal",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
        self.scheduler.start()
        logger.info(
            f"Webhook renewal scheduler started "
            f"(interval={SCAN_INTERVAL_MINUTES}m, threshold={RENEW_WHEN_LESS_THAN})"
        )

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("Webhook renewal scheduler stopped")

    async def renew_all(self):
        cursor = db_manager.db["integrations"].find(
            {"webhook_info": {"$exists": True, "$ne": None}}
        )
        renewed = 0
        failed = 0
        async for integration in cursor:
            for service, expiry in self._expiring_services(integration):
                try:
                    ok = await self._renew(integration, service, expiry)
                except Exception as e:
                    logger.error(
                        f"Renewal threw for integration={integration.get('_id')} service={service}: {e}",
                        exc_info=True,
                    )
                    ok = False
                if ok:
                    renewed += 1
                else:
                    failed += 1
        if renewed or failed:
            logger.info(f"Webhook renewal pass complete: renewed={renewed}, failed={failed}")

    def _expiring_services(self, integration: Dict[str, Any]) -> List[tuple]:
        """Yield (service_key, expiration_dt) tuples that need renewal."""
        out: List[tuple] = []
        webhook_info = integration.get("webhook_info") or {}
        name = integration.get("name")

        # Google services live on the workspace integration; Microsoft on its own
        for key in ("gmail", "drive", "calendar", "outlook", "onedrive"):
            entry = webhook_info.get(key)
            if not entry:
                continue
            # Disambiguate "calendar" — google_provider stores a Google Calendar
            # watch under .calendar, microsoft_provider stores Outlook Calendar
            # under .calendar too. Use the integration name to route correctly.
            if key == "calendar" and name and name not in ("google", "microsoft", "google_calendar", "outlook"):
                continue
            expiry = _parse_expiration(entry.get("webhook_expiration"))
            if _expires_soon(expiry):
                out.append((key, expiry))

        airtable = webhook_info.get("airtable") or {}
        for hook in airtable.get("webhooks", []) or []:
            expiry = _parse_expiration(hook.get("expiration_time"))
            if _expires_soon(expiry):
                out.append((f"airtable:{hook.get('webhook_id')}", expiry))

        return out

    async def _renew(self, integration: Dict[str, Any], service: str, current_expiry: datetime) -> bool:
        integration_id = str(integration["_id"])
        user_id = str(integration["user_id"])
        name = integration.get("name")

        logger.info(
            f"Renewing webhook integration={integration_id} user={user_id} name={name} "
            f"service={service} current_expiry={current_expiry.isoformat() if current_expiry else 'unknown'}"
        )

        if service == "gmail":
            return await self._renew_gmail(user_id, name, integration_id)
        if service == "drive":
            return await self._renew_google_drive(user_id, name, integration_id, integration)
        if service == "calendar":
            if name and name.startswith("microsoft") or name == "outlook":
                return await self._renew_microsoft(user_id, integration_id, integration, "calendar")
            return await self._renew_google_calendar(user_id, name, integration_id, integration)
        if service in ("outlook", "onedrive"):
            return await self._renew_microsoft(user_id, integration_id, integration, service)
        if service.startswith("airtable:"):
            webhook_id = service.split(":", 1)[1]
            return await self._renew_airtable(user_id, integration_id, integration, webhook_id)

        logger.warning(f"Unknown webhook service for renewal: {service}")
        return False

    # ---------- Google ----------

    async def _google_access_token(self, user_id: str, name: str) -> Optional[str]:
        # create_google_credentials handles refresh + persistence
        creds = await integration_service.create_google_credentials(user_id, name or "google")
        if not creds or not creds.token:
            logger.error(f"No Google credentials available for user {user_id}, integration {name}")
            return None
        return creds.token

    async def _renew_gmail(self, user_id: str, name: Optional[str], integration_id: str) -> bool:
        access_token = await self._google_access_token(user_id, name or "gmail")
        if not access_token:
            return False

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        if not project_id:
            logger.error("GOOGLE_CLOUD_PROJECT_ID not set; cannot renew Gmail watch")
            return False

        watch_request = {
            "topicName": f"projects/{project_id}/topics/gmail-webhook",
            "labelIds": ["INBOX"],
            "labelFilterAction": "include",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/watch",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=watch_request,
            )
            if response.status_code != 200:
                logger.error(f"Gmail re-watch failed: {response.status_code} - {response.text}")
                return False
            data = response.json()

        await integration_service.update_integration(integration_id, {
            "webhook_info.gmail.webhook_id": data.get("historyId"),
            "webhook_info.gmail.webhook_expiration": data.get("expiration"),
            "webhook_info.gmail.webhook_setup_at": datetime.now(timezone.utc).isoformat(),
        })
        return True

    async def _renew_google_drive(self, user_id: str, name: Optional[str], integration_id: str, integration: Dict[str, Any]) -> bool:
        access_token = await self._google_access_token(user_id, name or "google_drive")
        if not access_token:
            return False

        # Drive channels can't be extended in place — open a fresh channel and
        # rely on TTL to retire the old one.
        channel_id = f"drive-webhook-{integration_id}-{uuid.uuid4()}"
        new_expiry = datetime.now(timezone.utc) + GOOGLE_DRIVE_TTL
        watch_request = {
            "id": channel_id,
            "type": "web_hook",
            "address": "https://hooks.praxos.ai/webhooks/google-drive",
            "expiration": int(new_expiry.timestamp() * 1000),
        }
        page_token = await integration_service.get_drive_page_token(user_id, integration.get("connected_account")) or "1"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://www.googleapis.com/drive/v3/changes/watch",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=watch_request,
                params={"pageToken": page_token, "supportsAllDrives": "true"},
            )
            if response.status_code != 200:
                logger.error(f"Drive re-watch failed: {response.status_code} - {response.text}")
                return False
            data = response.json()

        await integration_service.update_integration(integration_id, {
            "webhook_info.drive.webhook_id": data.get("id"),
            "webhook_info.drive.webhook_resource_id": data.get("resourceId"),
            "webhook_info.drive.webhook_expiration": new_expiry.isoformat(),
            "webhook_info.drive.webhook_setup_at": datetime.now(timezone.utc).isoformat(),
        })
        return True

    async def _renew_google_calendar(self, user_id: str, name: Optional[str], integration_id: str, integration: Dict[str, Any]) -> bool:
        access_token = await self._google_access_token(user_id, name or "google_calendar")
        if not access_token:
            return False

        watch_request = {
            "id": f"calendar-webhook-{integration_id}-{uuid.uuid4()}",
            "type": "web_hook",
            "address": "https://hooks.praxos.ai/webhooks/google-calendar",
            "params": {"ttl": str(int(GOOGLE_CALENDAR_TTL.total_seconds()))},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events/watch",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=watch_request,
            )
            if response.status_code != 200:
                logger.error(f"Calendar re-watch failed: {response.status_code} - {response.text}")
                return False
            data = response.json()

        await integration_service.update_integration(integration_id, {
            "webhook_info.calendar.webhook_id": data.get("id"),
            "webhook_info.calendar.webhook_resource_id": data.get("resourceId"),
            "webhook_info.calendar.webhook_expiration": data.get("expiration"),
            "webhook_info.calendar.webhook_setup_at": datetime.now(timezone.utc).isoformat(),
        })
        return True

    # ---------- Microsoft ----------

    async def _microsoft_access_token(self, user_id: str) -> Optional[str]:
        # Reuse the integration helper's refresh path
        from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
        graph = MicrosoftGraphIntegration(user_id)
        if not await graph.authenticate():
            logger.error(f"Failed to authenticate Microsoft for user {user_id}")
            return None
        return graph.access_token

    async def _renew_microsoft(self, user_id: str, integration_id: str, integration: Dict[str, Any], service_key: str) -> bool:
        access_token = await self._microsoft_access_token(user_id)
        if not access_token:
            return False

        webhook_info = integration.get("webhook_info", {}).get(service_key, {})
        subscription_id = webhook_info.get("subscription_id")
        if not subscription_id:
            logger.warning(f"No subscription_id for MS {service_key} on integration {integration_id}")
            return False

        new_expiry = datetime.now(timezone.utc) + MICROSOFT_TTL
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"expirationDateTime": new_expiry.isoformat().replace("+00:00", "Z")},
            )
            if response.status_code not in (200, 204):
                logger.error(f"MS {service_key} renewal failed: {response.status_code} - {response.text}")
                return False

        await integration_service.update_integration(integration_id, {
            f"webhook_info.{service_key}.webhook_expiration": new_expiry.isoformat().replace("+00:00", "Z"),
        })
        return True

    # ---------- Airtable ----------

    async def _renew_airtable(self, user_id: str, integration_id: str, integration: Dict[str, Any], webhook_id: str) -> bool:
        token_info = await integration_service.get_integration_token(user_id, "airtable")
        if not token_info or not token_info.get("access_token"):
            logger.error(f"No Airtable token for user {user_id}")
            return False
        access_token = token_info["access_token"]

        airtable_info = (integration.get("webhook_info") or {}).get("airtable") or {}
        hooks = airtable_info.get("webhooks", []) or []
        target = next((h for h in hooks if h.get("webhook_id") == webhook_id), None)
        if not target:
            logger.warning(f"Airtable webhook {webhook_id} not found on integration {integration_id}")
            return False

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.airtable.com/v0/bases/{target['base_id']}/webhooks/{webhook_id}/refresh",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                logger.error(f"Airtable refresh failed for {webhook_id}: {response.status_code} - {response.text}")
                return False
            data = response.json()

        new_expiration = data.get("expirationTime")
        if new_expiration:
            updated_hooks = [
                {**h, "expiration_time": new_expiration} if h.get("webhook_id") == webhook_id else h
                for h in hooks
            ]
            await integration_service.update_integration(integration_id, {
                "webhook_info.airtable.webhooks": updated_hooks,
            })
        return True


webhook_renewal_service = WebhookRenewalService()
