import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account
from database.snapshot_connection import SnapshotSessionLocal
from database.snapshot_models import HyperliquidAccountSnapshot
from services.hyperliquid_environment import get_hyperliquid_client

logger = logging.getLogger(__name__)


class HyperliquidSnapshotService:
    """Service to periodically snapshot Hyperliquid account states"""

    def __init__(self, interval_seconds: int = 30):
        self.interval_seconds = interval_seconds
        self.running = False

    async def start(self):
        """Start snapshot service"""
        self.running = True
        logger.info(f"[HYPERLIQUID SNAPSHOT] Service started, interval={self.interval_seconds}s")

        while self.running:
            try:
                await self.take_snapshots()
            except Exception as e:
                logger.error(f"[HYPERLIQUID SNAPSHOT] Error: {e}", exc_info=True)

            await asyncio.sleep(self.interval_seconds)

    async def take_snapshots(self):
        """Take snapshots for all active Hyperliquid accounts"""
        # Use main DB to get accounts (read-only)
        main_db = SessionLocal()
        # Use snapshot DB to store snapshots
        snapshot_db = SnapshotSessionLocal()

        try:
            # PostgreSQL handles concurrent access natively

            # Find all accounts with Hyperliquid enabled
            accounts = main_db.query(Account).filter(
                Account.hyperliquid_enabled == "true",
                Account.is_active == "true"
            ).all()

            if not accounts:
                return

            snapshot_count = 0
            for account in accounts:
                try:
                    await self._take_account_snapshot(account, main_db, snapshot_db)
                    snapshot_count += 1
                except Exception as e:
                    logger.error(
                        f"[HYPERLIQUID SNAPSHOT] Failed for account {account.id} ({account.name}): {e}",
                        exc_info=True
                    )

            snapshot_db.commit()
            logger.debug(f"[HYPERLIQUID SNAPSHOT] Took {snapshot_count} snapshots")

        except Exception as e:
            logger.error(f"[HYPERLIQUID SNAPSHOT] Error: {e}", exc_info=True)
            snapshot_db.rollback()
        finally:
            main_db.close()
            snapshot_db.close()

    async def _take_account_snapshot(self, account: Account, main_db: Session, snapshot_db: Session):
        """Take snapshot for a single Hyperliquid account"""
        environment = account.hyperliquid_environment
        if not environment:
            logger.warning(f"[HYPERLIQUID SNAPSHOT] Account {account.id} has no environment set")
            return

        try:
            # Use existing API to get Hyperliquid client and account state
            client = get_hyperliquid_client(main_db, account.id)
            account_state = client.get_account_state(main_db)

            # Create snapshot record in snapshot database
            snapshot = HyperliquidAccountSnapshot(
                account_id=account.id,
                environment=environment,
                wallet_address=client.wallet_address,
                total_equity=account_state["total_equity"],
                available_balance=account_state["available_balance"],
                used_margin=account_state["used_margin"],
                maintenance_margin=account_state.get("maintenance_margin", 0),
                trigger_event="scheduled",
                snapshot_data=None  # Can store full JSON if needed
            )

            snapshot_db.add(snapshot)

            logger.debug(
                f"[HYPERLIQUID SNAPSHOT] Account {account.id} ({account.name}): "
                f"equity=${account_state['total_equity']:.2f}, "
                f"available=${account_state['available_balance']:.2f}, "
                f"used=${account_state['used_margin']:.2f}"
            )

        except Exception as e:
            logger.error(
                f"[HYPERLIQUID SNAPSHOT] Failed to get account state for account {account.id}: {e}",
                exc_info=True
            )

    def stop(self):
        """Stop snapshot service"""
        self.running = False
        logger.info("[HYPERLIQUID SNAPSHOT] Service stopped")


# Global instance
hyperliquid_snapshot_service = HyperliquidSnapshotService(interval_seconds=30)
