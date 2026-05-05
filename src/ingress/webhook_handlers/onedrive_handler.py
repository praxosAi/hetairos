from fastapi import APIRouter, Request, HTTPException, Response
from src.core.event_queue import event_queue
from src.services.integration_service import integration_service
from src.services.user_service import user_service
from src.utils.logging.base_logger import setup_logger, user_id_var, modality_var, request_id_var
from src.config.settings import settings
from src.core.praxos_client import PraxosClient
from src.utils.database import db_manager
from src.integrations.microsoft.graph_client import MicrosoftGraphIntegration
from datetime import datetime, timezone
import json

router = APIRouter()
logger = setup_logger(__name__)


async def _evaluate_drive_item(
    *,
    user_id,
    user_record,
    subscription_id: str,
    change: dict,
    item: dict,
    is_new: bool,
    previous_name=None,
    shared_with_me: bool = False,
):
    """Evaluate a single driveItem change against trigger-ingestor and emit
    triggered events when rules fire.

    Builds the onedrive adapter envelope shape:
        raw_payload = {"source": "onedrive",
                       "event_type": "driveItem.<changeType>",
                       "payload": {"change": {...}, "driveItem": {...}}}
    and passes the raw driveItem additionally via adapter_kwargs['fetched_item']
    (the adapter prefers the kwarg over payload.driveItem).
    """
    item_id = item.get("id") if item else change.get("itemId") or change.get("id")
    change_type = change.get("changeType", "updated")

    raw_payload = {
        "source": "onedrive",
        "event_type": f"driveItem.{change_type}",
        "payload": {
            "change": change,
            "driveItem": item or {},
        },
    }

    adapter_kwargs = {"is_new": bool(is_new), "shared_with_me": bool(shared_with_me)}
    if item:
        adapter_kwargs["fetched_item"] = item
    if previous_name:
        adapter_kwargs["previous_name"] = previous_name

    praxos_client = PraxosClient(
        user_id=str(user_record["_id"]),
        environment_id=str(user_record["environment_id"]),
    )

    logger.info(f"Evaluating triggers for OneDrive item {item_id}")
    event_eval_result = await praxos_client.eval_event(
        raw_payload, "onedrive", adapter_kwargs=adapter_kwargs,
    )

    if not event_eval_result.get("trigger"):
        logger.info(f"Evaluation found no trigger for OneDrive item {item_id}.")
        return

    logger.info(f"Trigger fired for OneDrive item {item_id}")
    for rule_id, action_data in event_eval_result.get("fired_rule_actions_details", {}).items():
        if isinstance(action_data, str):
            action_data = json.loads(action_data)

        rule_details = await db_manager.get_trigger_by_rule_id(rule_id)
        if not rule_details:
            logger.error(
                f"No trigger details found in DB for rule_id {rule_id}. "
                "Trigger may be inactive, deleted, or flawed."
            )
            continue

        # Flat description for COMMAND text
        item_summary = {
            "subscription_id": subscription_id,
            "change_type": change_type,
            "item_id": item_id,
            "name": item.get("name") if item else None,
            "size": item.get("size") if item else None,
            "mime_type": (item.get("file") or {}).get("mimeType") if item else None,
            "parent_folder": (item.get("parentReference") or {}).get("name") if item else None,
            "last_modified": item.get("lastModifiedDateTime") if item else None,
            "is_new": is_new,
            "previous_name": previous_name,
            "shared_with_me": shared_with_me,
        }

        COMMAND = ""
        COMMAND += f"Previously, on {rule_details.get('created_at')}, the user set up the following trigger: {rule_details.get('trigger_text')}. \n\n "
        COMMAND += f"Now, upon detecting a OneDrive file change at {datetime.now(timezone.utc)}, we believe that the trigger has been activated. \n\n "
        for action in action_data:
            COMMAND += "The following action was marked as a triggering candidate: " + action.get("simple_sentence", "") + ". \n"
            COMMAND += "The action has the following details, as parsed by the Praxos system: " + json.dumps(action, default=str) + ". \n\n"
        COMMAND += "Based on the above, please proceed to execute the action(s) specified in the trigger, if they are valid, match the user request, and are safe to perform. If you are unsure about any action, please ask the user for confirmation before proceeding. \n\n The event (OneDrive file change) that triggered this action is as follows: "

        normalized_payload = {
            "text": COMMAND + json.dumps(item_summary, indent=2, default=str),
        }

        ingestion_event = {
            "user_id": str(user_id),
            "source": "triggered",
            "payload": normalized_payload,
            "logging_context": {
                "user_id": user_id_var.get(),
                "request_id": str(request_id_var.get()),
                "modality": "triggered",
            },
            "metadata": {
                "ingest_type": "onedrive_webhook_triggered",
                "source": "onedrive",
                "webhook_event": True,
                "change_type": change_type,
                "subscription_id": subscription_id,
                "item_id": item_id,
                "conversation_id": rule_details.get("conversation_id"),
            },
        }
        if not ingestion_event["metadata"].get("conversation_id"):
            ingestion_event["metadata"].pop("conversation_id", None)

        await event_queue.publish(ingestion_event)
        logger.info(f"Published triggered event for OneDrive item {item_id} based on rule {rule_id}")


@router.post("/onedrive")
async def handle_onedrive_webhook(request: Request):
    """
    Handles incoming OneDrive webhook notifications.

    Microsoft Graph sends notifications when files/folders change in OneDrive.
    Reference: https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/using-webhooks

    IMPORTANT: OneDrive webhooks only support "updated" changeType and contain
    NO file details. We must call the Delta API (`/me/drive/root/delta`) to get
    actual changed driveItems, then pass each one to the trigger-ingestor.
    """
    try:
        # Handle validation request
        validation_token = request.query_params.get("validationToken")
        if validation_token:
            logger.info("Responding to OneDrive webhook validation request")
            return Response(content=validation_token, media_type="text/plain", status_code=200)

        # Process notification
        body = await request.json()
        logger.info("Received OneDrive webhook notification")

        for notification in body.get("value", []):
            # Validate client state
            client_state = notification.get("clientState")
            expected_state = settings.ONEDRIVE_VALIDATION_TOKEN
            if client_state != expected_state:
                logger.warning(f"Invalid clientState in OneDrive notification: {client_state}")
                continue

            subscription_id = notification.get("subscriptionId")
            change_type = notification.get("changeType")  # Only "updated" supported
            resource = notification.get("resource")
            logger.info(f"OneDrive change detected: {change_type} on {resource}")

            # Find integration (we need connected_account for the delta cursor)
            integration_record = await integration_service.get_integration_by_subscription_id(
                subscription_id, "onedrive",
            )
            if not integration_record:
                logger.warning(
                    f"No OneDrive integration found for subscription ID: {subscription_id}"
                )
                continue

            user_id = integration_record.get("user_id")
            connected_account = integration_record.get("connected_account")
            if not user_id:
                logger.warning(
                    f"OneDrive integration {integration_record.get('_id')} has no user_id"
                )
                continue

            user_record = user_service.get_user_by_id(user_id)
            if not user_record:
                logger.error(f"User not found for ID {user_id}")
                continue

            user_id_var.set(str(user_id))
            modality_var.set("onedrive_webhook")

            # Authenticate with Microsoft Graph
            graph_integration = MicrosoftGraphIntegration(str(user_id))
            if not await graph_integration.authenticate():
                logger.error(f"Failed to authenticate Microsoft Graph for user {user_id}")
                continue

            # Read the saved delta cursor (None on first run)
            delta_link = None
            if connected_account:
                try:
                    delta_link = await integration_service.get_onedrive_delta_link(
                        str(user_id), connected_account,
                    )
                except Exception as e:
                    logger.warning(f"Could not load saved OneDrive delta link: {e}")

            # Walk the delta pages, collecting changed driveItems
            changed_items = []
            new_delta_link = None
            current_url_or_link = delta_link  # None means start fresh
            try:
                while True:
                    page = await graph_integration.get_drive_delta(current_url_or_link)
                    for item in page.get("value", []):
                        changed_items.append(item)
                    next_link = page.get("@odata.nextLink")
                    if next_link:
                        current_url_or_link = next_link
                        continue
                    new_delta_link = page.get("@odata.deltaLink")
                    break
            except Exception as e:
                logger.error(f"Error walking OneDrive delta pages: {e}", exc_info=True)
                continue

            logger.info(
                f"OneDrive delta returned {len(changed_items)} changed items "
                f"for user {user_id}"
            )

            # Evaluate each changed item against trigger-ingestor.
            # NOTE: without a local snapshot we cannot determine `is_new` /
            # `previous_name`; we infer is_new from delta_link being None
            # (first sync) being False, and from `deleted` facet for trash.
            for item in changed_items:
                # Tombstone: deleted facet present
                if item.get("deleted") is not None:
                    change = {
                        "subscriptionId": subscription_id,
                        "changeType": "deleted",
                        "resource": resource,
                        "removed": True,
                        "itemId": item.get("id"),
                    }
                    try:
                        await _evaluate_drive_item(
                            user_id=user_id,
                            user_record=user_record,
                            subscription_id=subscription_id,
                            change=change,
                            item=item,
                            is_new=False,
                        )
                    except Exception as e:
                        logger.error(f"Error evaluating tombstone item {item.get('id')}: {e}", exc_info=True)
                    continue

                # Skip pure folders (the adapter ignores them too, but we
                # avoid the round-trip).
                if item.get("folder") and not item.get("file"):
                    continue

                change = {
                    "subscriptionId": subscription_id,
                    "changeType": change_type or "updated",
                    "resource": resource,
                    "removed": False,
                }
                try:
                    await _evaluate_drive_item(
                        user_id=user_id,
                        user_record=user_record,
                        subscription_id=subscription_id,
                        change=change,
                        item=item,
                        # Best-effort: treat created==modified when timestamps
                        # are equal as a "new" item.
                        is_new=(
                            item.get("createdDateTime") is not None
                            and item.get("createdDateTime") == item.get("lastModifiedDateTime")
                        ),
                        shared_with_me=bool(item.get("remoteItem")),
                    )
                except Exception as e:
                    logger.error(f"Error evaluating drive item {item.get('id')}: {e}", exc_info=True)

            # Persist the new delta cursor so the next webhook only returns
            # newer changes.
            if new_delta_link and connected_account:
                try:
                    await integration_service.set_onedrive_delta_link(
                        str(user_id), connected_account, new_delta_link,
                    )
                except Exception as e:
                    logger.warning(f"Could not persist OneDrive delta link: {e}")

            logger.info(
                f"Processed OneDrive webhook for user {user_id}, "
                f"change_type: {change_type}, items: {len(changed_items)}"
            )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing OneDrive webhook: {e}", exc_info=True)
        return {"status": "ok"}  # Always return OK to acknowledge webhook
