"""
Backfill script to sync existing user integrations to their knowledge graphs.
Run this once to populate KG with integration data for existing users.

Usage:
    python scripts/backfill_user_integrations_to_kg.py [--user-id USER_ID] [--dry-run]
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.utils.database import db_manager
from src.services.integration_service import integration_service
from src.core.praxos_client import PraxosClient
from src.utils.logging.base_logger import setup_logger
from bson import ObjectId

logger = setup_logger("backfill_integrations_to_kg")


async def backfill_user_integrations(user_id: str, dry_run: bool = False):
    """
    Backfill integrations for a single user.

    Args:
        user_id: User ID to backfill
        dry_run: If True, only log what would be done without making changes
    """
    try:
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Processing user {user_id}")

        # Get all integrations for this user
        integrations = await integration_service.get_user_integrations(user_id)

        if not integrations:
            logger.info(f"User {user_id} has no integrations")
            return {"user_id": user_id, "integrations_synced": 0}

        logger.info(f"Found {len(integrations)} integrations for user {user_id}")

        if dry_run:
            for integ in integrations:
                logger.info(f"[DRY RUN] Would sync: {integ.get('name')} (status: {integ.get('status')})")
            return {"user_id": user_id, "integrations_found": len(integrations), "dry_run": True}

        # Create praxos client for this user
        praxos_client = PraxosClient(
            environment_name=f"user_{user_id}",
            api_key=settings.PRAXOS_API_KEY
        )

        # Sync each integration to KG
        synced_count = 0
        failed_count = 0

        for integ in integrations:
            integration_name = integ.get('name')
            try:
                logger.info(f"Syncing integration: {integration_name}")

                result = await integration_service.sync_integration_to_kg(
                    user_id=user_id,
                    integration_name=integration_name,
                    integration_data=integ,
                    praxos_client=praxos_client
                )

                if 'error' in result:
                    logger.error(f"Failed to sync {integration_name}: {result['error']}")
                    failed_count += 1
                else:
                    logger.info(f"Successfully synced {integration_name}")
                    synced_count += 1

                # Small delay to avoid overwhelming services
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error syncing {integration_name} for user {user_id}: {e}")
                failed_count += 1

        logger.info(f"Completed backfill for user {user_id}: {synced_count} synced, {failed_count} failed")

        return {
            "user_id": user_id,
            "integrations_synced": synced_count,
            "integrations_failed": failed_count,
            "total": len(integrations)
        }

    except Exception as e:
        logger.error(f"Error backfilling user {user_id}: {e}")
        return {"user_id": user_id, "error": str(e)}


async def backfill_all_users(dry_run: bool = False, limit: int = None):
    """
    Backfill integrations for all users in the system.

    Args:
        dry_run: If True, only log what would be done
        limit: Optional limit on number of users to process
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting backfill for all users (limit={limit})")

    try:
        # Get all unique user IDs from integrations collection
        pipeline = [
            {"$group": {"_id": "$user_id"}},
            {"$project": {"user_id": "$_id", "_id": 0}}
        ]

        if limit:
            pipeline.append({"$limit": limit})

        user_ids = await db_manager.db["integrations"].aggregate(pipeline).to_list(length=None)

        logger.info(f"Found {len(user_ids)} users with integrations")

        results = []
        for user_doc in user_ids:
            user_id = str(user_doc['user_id'])

            result = await backfill_user_integrations(user_id, dry_run=dry_run)
            results.append(result)

            # Delay between users to avoid overwhelming services
            await asyncio.sleep(0.5)

        # Summary statistics
        total_users = len(results)
        total_synced = sum(r.get('integrations_synced', 0) for r in results)
        total_failed = sum(r.get('integrations_failed', 0) for r in results)

        logger.info(f"\n{'='*60}")
        logger.info(f"BACKFILL COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Users processed: {total_users}")
        logger.info(f"Integrations synced: {total_synced}")
        logger.info(f"Integrations failed: {total_failed}")
        logger.info(f"{'='*60}\n")

        return {
            "total_users": total_users,
            "total_synced": total_synced,
            "total_failed": total_failed,
            "results": results
        }

    except Exception as e:
        logger.error(f"Error in backfill_all_users: {e}", exc_info=True)
        raise


async def main():
    """Main entry point for the backfill script"""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill user integrations to knowledge graph")
    parser.add_argument("--user-id", help="Backfill a specific user (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode - don't make changes")
    parser.add_argument("--limit", type=int, help="Limit number of users to process")

    args = parser.parse_args()

    logger.info("Starting integration KG backfill script")

    if args.user_id:
        # Backfill single user
        result = await backfill_user_integrations(args.user_id, dry_run=args.dry_run)
        logger.info(f"Result: {result}")
    else:
        # Backfill all users
        result = await backfill_all_users(dry_run=args.dry_run, limit=args.limit)

    logger.info("Backfill script completed")


if __name__ == "__main__":
    asyncio.run(main())
