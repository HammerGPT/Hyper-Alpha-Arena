"""
Scheduled task scheduler service
Used to manage WebSocket snapshot updates and other scheduled tasks
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Set, Callable, Optional, List
import logging
from datetime import date, datetime

from database.connection import SessionLocal
from database.models import Position, CryptoPrice

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Unified task scheduler"""
    
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None
        self._started = False
        self._account_connections: Dict[int, Set] = {}  # track account connections
        
    def start(self):
        """Start the scheduler"""
        if not self._started:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            self._started = True
            logger.info("Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self._started = False
            logger.info("Scheduler shutdown")
    
    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self._started and self.scheduler and self.scheduler.running
    
    def add_account_snapshot_task(self, account_id: int, interval_seconds: int = 10):
        """
        Add snapshot update task for account

        Args:
            account_id: Account ID
            interval_seconds: Update interval (seconds), default 10 seconds
        """
        if not self.is_running():
            self.start()
            
        job_id = f"snapshot_account_{account_id}"
        
        # Check if task already exists
        if self.scheduler.get_job(job_id):
            logger.debug(f"Snapshot task for account {account_id} already exists")
            return
        
        self.scheduler.add_job(
            func=self._execute_account_snapshot,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[account_id],
            id=job_id,
            replace_existing=True,
            max_instances=1,  # Avoid duplicate execution
            coalesce=True,    # Combine missed executions into one
            misfire_grace_time=5  # Allow 5 seconds grace time for late execution
        )
        
        logger.info(f"Added snapshot task for account {account_id}, interval {interval_seconds} seconds")
    
    def remove_account_snapshot_task(self, account_id: int):
        """
        Remove snapshot update task for account

        Args:
            account_id: Account ID
        """
        if not self.scheduler:
            return
            
        job_id = f"snapshot_account_{account_id}"
        
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed snapshot task for account {account_id}")
        except Exception as e:
            logger.debug(f"Failed to remove snapshot task for account {account_id}: {e}")
    
    
    def add_interval_task(self, task_func: Callable, interval_seconds: int, task_id: str, *args, **kwargs):
        """
        Add interval execution task

        Args:
            task_func: Function to execute
            interval_seconds: Execution interval (seconds)
            task_id: Task unique identifier
            *args, **kwargs: Parameters passed to task_func
        """
        if not self.is_running():
            self.start()
            
        self.scheduler.add_job(
            func=task_func,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        logger.info(f"Added interval task {task_id}: Execute every {interval_seconds} seconds")
    
    def remove_task(self, task_id: str):
        """
        Remove specified task

        Args:
            task_id: Task ID
        """
        if not self.scheduler:
            return
            
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"Removed task: {task_id}")
        except Exception as e:
            logger.debug(f"Failed to remove task {task_id}: {e}")

    def get_job_info(self) -> list:
        """Get all task information"""
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time,
                'func_name': job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
            })
        return jobs

    async def _execute_account_snapshot(self, account_id: int):
        """
        Internal method to execute account snapshot update

        Args:
            account_id: Account ID
        """
        start_time = datetime.now()
        try:
            # Dynamic import to avoid circular dependency
            from api.ws import manager, _send_snapshot_optimized

            # Check if account still has active connections
            if account_id not in manager.active_connections:
                # Account disconnected, remove task
                self.remove_account_snapshot_task(account_id)
                return

            # Execute optimized snapshot update
            db: Session = SessionLocal()
            try:
                # Send optimized snapshot update (reduced frequency for expensive data)
                # Note: For now, skip the async WebSocket update in sync scheduler context
                # This can be enhanced later to properly handle async operations
                logger.debug(f"Skipping WebSocket snapshot update for account {account_id} in sync context")

                # Save latest prices for account's positions (less frequently)
                if start_time.second % 30 == 0:  # Only every 30 seconds
                    self._save_position_prices(db, account_id)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Account {account_id} snapshot update failed: {e}")
        finally:
            execution_time = (datetime.now() - start_time).total_seconds()
            if execution_time > 5:  # Log if execution takes longer than 5 seconds
                logger.warning(f"Slow snapshot execution for account {account_id}: {execution_time:.2f}s")
    
    def _save_position_prices(self, db: Session, account_id: int):
        """
        Save latest prices for account's positions on the current date

        Args:
            db: Database session
            account_id: Account ID
        """
        try:
            # Get all account's positions
            positions = db.query(Position).filter(
                Position.account_id == account_id,
                Position.quantity > 0
            ).all()

            if not positions:
                logger.debug(f"Account {account_id} has no positions, skip price saving")
                return

            today = date.today()

            for position in positions:
                try:
                    # Check if crypto price already saved today
                    existing_price = db.query(CryptoPrice).filter(
                        CryptoPrice.symbol == position.symbol,
                        CryptoPrice.market == position.market,
                        CryptoPrice.price_date == today
                    ).first()

                    if existing_price:
                        logger.debug(f"crypto {position.symbol} price already exists for today, skip")
                        continue

                    # Get latest price
                    from services.market_data import get_last_price
                    current_price = get_last_price(position.symbol, position.market)

                    # Save price record
                    crypto_price = CryptoPrice(
                        symbol=position.symbol,
                        market=position.market,
                        price=current_price,
                        price_date=today
                    )

                    db.add(crypto_price)
                    db.commit()

                    logger.info(f"Saved crypto price: {position.symbol} {today} {current_price}")

                except Exception as e:
                    logger.error(f"Failed to save crypto {position.symbol} price: {e}")
                    db.rollback()
                    continue

        except Exception as e:
            logger.error(f"Failed to save account {account_id} position prices: {e}")
            db.rollback()


# Global scheduler instance
task_scheduler = TaskScheduler()


# Convenience functions
def start_scheduler():
    """Start global scheduler"""
    task_scheduler.start()


def stop_scheduler():
    """Stop global scheduler"""
    task_scheduler.shutdown()


def add_account_snapshot_job(account_id: int, interval_seconds: int = 10):
    """Convenience function to add snapshot task for account"""
    task_scheduler.add_account_snapshot_task(account_id, interval_seconds)


def remove_account_snapshot_job(account_id: int):
    """Convenience function to remove account snapshot task"""
    task_scheduler.remove_account_snapshot_task(account_id)


# Legacy compatibility functions
def add_user_snapshot_job(user_id: int, interval_seconds: int = 10):
    """Legacy function - now redirects to account-based function"""
    # For backward compatibility, assume this is account_id
    add_account_snapshot_job(user_id, interval_seconds)


def remove_user_snapshot_job(user_id: int):
    """Legacy function - now redirects to account-based function"""
    # For backward compatibility, assume this is account_id
    remove_account_snapshot_job(user_id)


def setup_market_tasks():
    """Set up crypto market-related scheduled tasks"""
    # Crypto markets run 24/7, no specific market open/close times needed
    logger.info("Crypto markets run 24/7 - no market hours tasks needed")


def _ensure_market_data_ready() -> None:
    """Prefetch required market data before enabling trading tasks"""
    try:
        from services.trading_commands import AI_TRADING_SYMBOLS
        from services.market_data import get_last_price

        missing_symbols: List[str] = []

        for symbol in AI_TRADING_SYMBOLS:
            try:
                price = get_last_price(symbol, "CRYPTO")
                if price is None or price <= 0:
                    missing_symbols.append(symbol)
                    logger.warning(f"Prefetch returned invalid price for {symbol}: {price}")
                else:
                    logger.debug(f"Prefetched market data for {symbol}: {price}")
            except Exception as fetch_err:
                missing_symbols.append(symbol)
                logger.warning(f"Failed to prefetch price for {symbol}: {fetch_err}")

        if missing_symbols:
            raise RuntimeError(
                "Market data not ready for symbols: " + ", ".join(sorted(set(missing_symbols)))
            )

    except Exception as err:
        logger.error(f"Market data readiness check failed: {err}")
        raise


def reset_auto_trading_job():
    """Reset the auto trading job after account configuration changes"""
    try:
        # Import constants from auto_trader module
        from services.auto_trader import AI_TRADE_JOB_ID
        from services.trading_commands import place_ai_driven_crypto_order
        
        # Define interval (3 minutes)
        AI_TRADE_INTERVAL_SECONDS = 180
        
        # Ensure market data is ready before scheduling trading tasks
        _ensure_market_data_ready()

        # Ensure scheduler is started
        if not task_scheduler.is_running():
            task_scheduler.start()
            logger.info("Started scheduler for auto trading job reset")

        # Remove existing auto trading job if it exists
        if task_scheduler.scheduler and task_scheduler.scheduler.get_job(AI_TRADE_JOB_ID):
            task_scheduler.remove_task(AI_TRADE_JOB_ID)
            logger.info(f"Removed existing auto trading job: {AI_TRADE_JOB_ID}")
        
        # Re-add the auto trading job with updated configuration
        task_scheduler.add_interval_task(
            task_func=lambda: place_ai_driven_crypto_order(max_ratio=0.2),
            interval_seconds=AI_TRADE_INTERVAL_SECONDS,
            task_id=AI_TRADE_JOB_ID
        )
        
        logger.info(f"Auto trading job reset successfully - interval: {AI_TRADE_INTERVAL_SECONDS}s")

    except Exception as e:
        logger.error(f"Failed to reset auto trading job: {e}")
        raise


def start_asset_curve_broadcast():
    """Start asset curve broadcast task - broadcasts every 60 seconds"""
    import asyncio
    from api.ws import broadcast_asset_curve_update

    def broadcast_all_timeframes():
        """Broadcast asset curve updates for all timeframes"""
        try:
            # Create event loop for async tasks
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Broadcast updates for all timeframes
            loop.run_until_complete(broadcast_asset_curve_update("5m"))
            loop.run_until_complete(broadcast_asset_curve_update("1h"))
            loop.run_until_complete(broadcast_asset_curve_update("1d"))

            logger.debug("Broadcasted asset curve updates for all timeframes")

        except Exception as e:
            logger.error(f"Failed to broadcast asset curve updates: {e}")
        finally:
            try:
                loop.close()
            except:
                pass

    try:
        # Ensure scheduler is running
        if not task_scheduler.is_running():
            task_scheduler.start()
            logger.info("Started scheduler for asset curve broadcast")

        # Add broadcast task (every 60 seconds)
        ASSET_CURVE_BROADCAST_JOB_ID = "asset_curve_broadcast"
        BROADCAST_INTERVAL_SECONDS = 60

        # Remove existing job if it exists
        if task_scheduler.scheduler and task_scheduler.scheduler.get_job(ASSET_CURVE_BROADCAST_JOB_ID):
            task_scheduler.remove_task(ASSET_CURVE_BROADCAST_JOB_ID)
            logger.info(f"Removed existing asset curve broadcast job")

        # Add the broadcast job
        task_scheduler.add_interval_task(
            task_func=broadcast_all_timeframes,
            interval_seconds=BROADCAST_INTERVAL_SECONDS,
            task_id=ASSET_CURVE_BROADCAST_JOB_ID
        )

        logger.info(f"Asset curve broadcast job started - interval: {BROADCAST_INTERVAL_SECONDS}s")

    except Exception as e:
        logger.error(f"Failed to start asset curve broadcast: {e}")
        raise