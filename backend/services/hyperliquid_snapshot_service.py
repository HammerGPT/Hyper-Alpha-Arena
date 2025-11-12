import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, HyperliquidWallet
from database.snapshot_connection import SnapshotSessionLocal
from database.snapshot_models import HyperliquidAccountSnapshot
from services.hyperliquid_environment import get_hyperliquid_client, get_global_trading_mode
from api.ws import broadcast_arena_asset_update, manager

logger = logging.getLogger(__name__)


class HyperliquidSnapshotService:
    """Service to periodically snapshot Hyperliquid account states"""

    def __init__(self, interval_seconds: int = 300):
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

            # Get global trading mode to determine which wallets to snapshot
            global_environment = get_global_trading_mode(main_db)
            if not global_environment:
                logger.debug("[HYPERLIQUID SNAPSHOT] No global trading mode set, skipping")
                return

            # Find all active AI accounts that have a wallet configured for the current environment
            # Using JOIN to ensure only accounts with wallets are processed
            accounts = main_db.query(Account).join(
                HyperliquidWallet,
                Account.id == HyperliquidWallet.account_id
            ).filter(
                Account.is_active == "true",
                Account.account_type == "AI",
                HyperliquidWallet.environment == global_environment,
                HyperliquidWallet.is_active == "true"
            ).distinct().all()

            if not accounts:
                logger.debug(f"[HYPERLIQUID SNAPSHOT] No accounts with {global_environment} wallets found")
                return

            snapshot_count = 0
            accounts_payload = []
            total_available = 0.0
            total_used = 0.0
            total_equity = 0.0

            for account in accounts:
                try:
                    account_data = await self._take_account_snapshot(account, global_environment, main_db, snapshot_db)
                    if account_data:
                        snapshot_count += 1
                        accounts_payload.append({
                            "account_id": account.id,
                            "account_name": account.name,
                            "model": account.model,
                            "available_cash": round(account_data["available_balance"], 2),
                            "frozen_cash": round(account_data["used_margin"], 2),
                            "positions_value": round(account_data["used_margin"], 2),  # For Hyperliquid, positions_value = used_margin
                            "total_assets": round(account_data["total_equity"], 2),
                        })
                        total_available += account_data["available_balance"]
                        total_used += account_data["used_margin"]
                        total_equity += account_data["total_equity"]
                except Exception as e:
                    logger.error(
                        f"[HYPERLIQUID SNAPSHOT] Failed for account {account.id} ({account.name}): {e}",
                        exc_info=True
                    )

            snapshot_db.commit()
            logger.debug(f"[HYPERLIQUID SNAPSHOT] Took {snapshot_count} snapshots for {global_environment}")

            # Broadcast arena asset update to WebSocket clients
            if accounts_payload and manager.has_connections():
                from datetime import datetime, timezone
                update_payload = {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "totals": {
                        "available_cash": round(total_available, 2),
                        "frozen_cash": round(total_used, 2),
                        "positions_value": round(total_used, 2),
                        "total_assets": round(total_equity, 2),
                    },
                    "symbols": {},  # Hyperliquid positions are tracked separately
                    "accounts": accounts_payload,
                }
                try:
                    manager.schedule_task(broadcast_arena_asset_update(update_payload))
                    logger.debug(f"[HYPERLIQUID SNAPSHOT] Broadcasted arena asset update for {len(accounts_payload)} accounts")
                except Exception as broadcast_err:
                    logger.debug(f"[HYPERLIQUID SNAPSHOT] Failed to broadcast arena asset update: {broadcast_err}")

        except Exception as e:
            logger.error(f"[HYPERLIQUID SNAPSHOT] Error: {e}", exc_info=True)
            snapshot_db.rollback()
        finally:
            main_db.close()
            snapshot_db.close()

    async def _take_account_snapshot(self, account: Account, environment: str, main_db: Session, snapshot_db: Session):
        """Take snapshot for a single Hyperliquid account

        Returns:
            dict: Account state data with keys: total_equity, available_balance, used_margin
            None: If snapshot failed
        """
        if not environment:
            logger.warning(f"[HYPERLIQUID SNAPSHOT] No environment provided for account {account.id}")
            return None

        try:
            # Use existing API to get Hyperliquid client and account state
            # Pass environment explicitly to ensure correct wallet is used
            client = get_hyperliquid_client(main_db, account.id, override_environment=environment)
            account_state = client.get_account_state(main_db)
            try:
                # Fetch positions to refresh caches for UI consumers
                client.get_positions(main_db)
            except Exception as pos_err:
                logger.warning(f"[HYPERLIQUID SNAPSHOT] Failed to refresh positions for account {account.id}: {pos_err}")

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

            return account_state

        except Exception as e:
            logger.error(
                f"[HYPERLIQUID SNAPSHOT] Failed to get account state for account {account.id}: {e}",
                exc_info=True
            )
            return None

    def stop(self):
        """Stop snapshot service"""
        self.running = False
        logger.info("[HYPERLIQUID SNAPSHOT] Service stopped")


# Global instance
hyperliquid_snapshot_service = HyperliquidSnapshotService(interval_seconds=300)
