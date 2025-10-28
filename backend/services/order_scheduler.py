"""
Order scheduling service
Background task for periodically processing pending orders
"""

import asyncio
import threading
import time
import logging
from typing import Optional

from database.connection import SessionLocal
from .order_matching import process_all_pending_orders

logger = logging.getLogger(__name__)


class OrderScheduler:
    """Order scheduler"""
    
    def __init__(self, interval_seconds: int = 5):
        """
        Initialize the order scheduler

        Args:
            interval_seconds: Check interval (seconds)
        """
        self.interval_seconds = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Order scheduler is already running")
            return
        
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"Order scheduler started, check interval: {self.interval_seconds} seconds")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.running:
            return
        
        self.running = False
        self._stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)
        
        logger.info("Order scheduler stopped")
    
    def _run_scheduler(self):
        """Scheduler main loop"""
        logger.info("Order scheduler started running")
        
        while self.running and not self._stop_event.is_set():
            try:
                # Process orders
                self._process_orders()
                
                # Wait for next execution
                if self._stop_event.wait(timeout=self.interval_seconds):
                    break
                    
            except Exception as e:
                logger.error(f"Order scheduler execution error: {e}")
                # Wait briefly after error to avoid rapid looping
                time.sleep(1)
        
        logger.info("Order scheduler main loop ended")
    
    def _process_orders(self):
        """Process pending orders"""
        db = SessionLocal()
        try:
            executed_count, total_checked = process_all_pending_orders(db)
            
            if total_checked > 0:
                logger.debug(f"Order processing: checked {total_checked}, executed {executed_count}")
            
        except Exception as e:
            logger.error(f"Error processing orders: {e}")
        finally:
            db.close()
    
    def process_orders_once(self):
        """Manually execute order processing once"""
        if not self.running:
            logger.warning("Order scheduler not running, cannot process orders")
            return
        
        try:
            self._process_orders()
            logger.info("Manual order processing completed")
        except Exception as e:
            logger.error(f"Manual order processing failed: {e}")


# Global scheduler instance
order_scheduler = OrderScheduler(interval_seconds=5)


def start_order_scheduler():
    """Start global order scheduler"""
    order_scheduler.start()


def stop_order_scheduler():
    """Stop global order scheduler"""
    order_scheduler.stop()


def get_scheduler_status():
    """Get scheduler status"""
    return {
        "running": order_scheduler.running,
        "interval_seconds": order_scheduler.interval_seconds,
        "thread_alive": order_scheduler.thread.is_alive() if order_scheduler.thread else False
    }