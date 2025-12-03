"""Application startup initialization service"""

import logging
import threading
import asyncio

from services.auto_trader import (
    place_ai_driven_crypto_order,
    place_random_crypto_order,
    AUTO_TRADE_JOB_ID,
    AI_TRADE_JOB_ID
)
from services.scheduler import start_scheduler, setup_market_tasks, task_scheduler
from services.market_stream import start_market_stream, stop_market_stream
from services.market_events import subscribe_price_updates, unsubscribe_price_updates
from services.asset_snapshot_service import handle_price_update
from services.trading_strategy import start_strategy_manager, stop_strategy_manager
from services.hyperliquid_symbol_service import (
    refresh_hyperliquid_symbols,
    schedule_symbol_refresh_task,
    build_market_stream_symbols,
)

logger = logging.getLogger(__name__)

# Track WebSocket initialization status
_websocket_initialized = False


async def initialize_hyperliquid_websocket():
    """
    Initialize Hyperliquid WebSocket connections for real-time data.
    
    This dramatically reduces API quota consumption by using WebSocket
    for price data instead of HTTP polling.
    
    WebSocket connections do NOT count toward address-based rate limits.
    """
    global _websocket_initialized
    
    print(">>> initialize_hyperliquid_websocket() called")
    
    if _websocket_initialized:
        print(">>> Hyperliquid WebSocket already initialized")
        logger.info("Hyperliquid WebSocket already initialized")
        return
    
    try:
        from services.hyperliquid_websocket import (
            start_websocket_manager,
            get_websocket_manager,
        )
        
        # Initialize WebSocket for mainnet
        print(">>> Initializing Hyperliquid WebSocket for mainnet...")
        logger.info("Initializing Hyperliquid WebSocket for mainnet...")
        mainnet_manager = await start_websocket_manager("mainnet")
        
        if mainnet_manager.is_connected:
            # Subscribe to all mid prices (real-time price streaming)
            await mainnet_manager.subscribe_all_mids()
            print(">>> ✅ Hyperliquid mainnet WebSocket connected and subscribed to allMids")
            logger.info("✅ Hyperliquid mainnet WebSocket connected and subscribed to allMids")
        else:
            print(">>> ⚠️ Failed to connect Hyperliquid mainnet WebSocket")
            logger.warning("⚠️ Failed to connect Hyperliquid mainnet WebSocket")
        
        # Initialize WebSocket for testnet
        print(">>> Initializing Hyperliquid WebSocket for testnet...")
        logger.info("Initializing Hyperliquid WebSocket for testnet...")
        testnet_manager = await start_websocket_manager("testnet")
        
        if testnet_manager.is_connected:
            await testnet_manager.subscribe_all_mids()
            print(">>> ✅ Hyperliquid testnet WebSocket connected and subscribed to allMids")
            logger.info("✅ Hyperliquid testnet WebSocket connected and subscribed to allMids")
        else:
            print(">>> ⚠️ Failed to connect Hyperliquid testnet WebSocket")
            logger.warning("⚠️ Failed to connect Hyperliquid testnet WebSocket")
        
        _websocket_initialized = True
        print(">>> Hyperliquid WebSocket initialization complete")
        logger.info("Hyperliquid WebSocket initialization complete")
        
    except ImportError as e:
        print(f">>> WebSocket module not available: {e}")
        logger.warning(f"WebSocket module not available: {e}. Using HTTP fallback for prices.")
    except Exception as e:
        print(f">>> Failed to initialize Hyperliquid WebSocket: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"Failed to initialize Hyperliquid WebSocket: {e}")
        logger.warning("Falling back to HTTP polling for price data (higher API quota usage)")


def initialize_services():
    """Initialize all services"""
    try:
        # Start the scheduler
        print("Starting scheduler...")
        start_scheduler()
        print("Scheduler started")
        logger.info("Scheduler service started")

        # Initialize Hyperliquid WebSocket for real-time price data
        # This MUST be done early to reduce API quota consumption
        # Note: WebSocket initialization is deferred to startup_event() which runs in async context
        print("Hyperliquid WebSocket will be initialized in async startup event")
        logger.info("Hyperliquid WebSocket initialization deferred to async startup")

        # Refresh Hyperliquid symbol catalog + schedule periodic updates
        refresh_hyperliquid_symbols()
        schedule_symbol_refresh_task()

        # Set up market-related scheduled tasks
        setup_market_tasks()
        logger.info("Market scheduled tasks have been set up")

        # Add price cache cleanup task (every 2 minutes)
        from services.price_cache import clear_expired_prices
        task_scheduler.add_interval_task(
            task_func=clear_expired_prices,
            interval_seconds=120,  # Clean every 2 minutes
            task_id="price_cache_cleanup"
        )
        logger.info("Price cache cleanup task started (2-minute interval)")

        # Start market data stream
        # NOTE: Paper trading snapshot service disabled - using Hyperliquid snapshots only
        combined_symbols = build_market_stream_symbols()
        print("Starting market data stream...")
        start_market_stream(combined_symbols, interval_seconds=1.5)
        print("Market data stream started")
        # subscribe_price_updates(handle_price_update)  # DISABLED: Paper trading snapshot
        # print("Asset snapshot handler subscribed")
        logger.info("Market data stream initialized")

        # Subscribe strategy manager to price updates
        from services.trading_strategy import handle_price_update as strategy_price_update

        def strategy_price_wrapper(event):
            """Wrapper to convert event format for strategy manager"""
            symbol = event.get("symbol")
            price = event.get("price")
            event_time = event.get("event_time")
            if symbol and price:
                strategy_price_update(symbol, float(price), event_time)

        subscribe_price_updates(strategy_price_wrapper)
        logger.info("Strategy manager subscribed to price updates")

        # Start AI trading strategy manager
        print("Starting strategy manager...")
        start_strategy_manager()
        print("Strategy manager started")

        # Start asset curve broadcast task (every 60 seconds)
        from services.scheduler import start_asset_curve_broadcast
        start_asset_curve_broadcast()
        logger.info("Asset curve broadcast task started (60-second interval)")

        # Start Hyperliquid account snapshot service (every 30 seconds)
        from services.hyperliquid_snapshot_service import hyperliquid_snapshot_service
        asyncio.create_task(hyperliquid_snapshot_service.start())
        logger.info("Hyperliquid snapshot service started (30-second interval)")

        # Start K-line realtime collection service
        from services.kline_realtime_collector import realtime_collector
        asyncio.create_task(realtime_collector.start())
        logger.info("K-line realtime collection service started (1-minute interval)")

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise


async def shutdown_hyperliquid_websocket():
    """Shutdown Hyperliquid WebSocket connections"""
    global _websocket_initialized
    
    try:
        from services.hyperliquid_websocket import stop_all_websocket_managers
        
        logger.info("Shutting down Hyperliquid WebSocket connections...")
        await stop_all_websocket_managers()
        _websocket_initialized = False
        logger.info("Hyperliquid WebSocket connections closed")
        
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Error shutting down Hyperliquid WebSocket: {e}")


def shutdown_services():
    """Shut down all services"""
    try:
        from services.scheduler import stop_scheduler
        from services.hyperliquid_snapshot_service import hyperliquid_snapshot_service
        from services.kline_realtime_collector import realtime_collector

        stop_strategy_manager()
        stop_market_stream()
        unsubscribe_price_updates(handle_price_update)
        hyperliquid_snapshot_service.stop()

        # Stop K-line realtime collector
        asyncio.create_task(realtime_collector.stop())

        # Stop Hyperliquid WebSocket connections
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(shutdown_hyperliquid_websocket())
            else:
                loop.run_until_complete(shutdown_hyperliquid_websocket())
        except RuntimeError:
            asyncio.run(shutdown_hyperliquid_websocket())

        stop_scheduler()
        logger.info("All services have been shut down")

    except Exception as e:
        logger.error(f"Failed to shut down services: {e}")


async def startup_event():
    """FastAPI application startup event"""
    initialize_services()
    
    # Ensure WebSocket is initialized in async context
    await initialize_hyperliquid_websocket()


async def shutdown_event():
    """FastAPI application shutdown event"""
    # Shutdown WebSocket first
    await shutdown_hyperliquid_websocket()
    shutdown_services()


def schedule_auto_trading(interval_seconds: int = 300, max_ratio: float = 0.2, use_ai: bool = True) -> None:
    """Schedule automatic trading tasks
    
    Args:
        interval_seconds: Interval between trading attempts
        max_ratio: Maximum portion of portfolio to use per trade
        use_ai: If True, use AI-driven trading; if False, use random trading
    """
    from services.auto_trader import (
        place_ai_driven_crypto_order,
        place_random_crypto_order,
        AUTO_TRADE_JOB_ID,
        AI_TRADE_JOB_ID
    )

    def execute_trade():
        try:
            if use_ai:
                place_ai_driven_crypto_order(max_ratio)
            else:
                place_random_crypto_order(max_ratio)
            logger.info("Initial auto-trading execution completed")
        except Exception as e:
            logger.error(f"Error during initial auto-trading execution: {e}")

    if use_ai:
        task_func = place_ai_driven_crypto_order
        job_id = AI_TRADE_JOB_ID
        logger.info("Scheduling AI-driven crypto trading")
    else:
        task_func = place_random_crypto_order
        job_id = AUTO_TRADE_JOB_ID
        logger.info("Scheduling random crypto trading")

    # Schedule the recurring task
    task_scheduler.add_interval_task(
        task_func=task_func,
        interval_seconds=interval_seconds,
        task_id=job_id,
        max_ratio=max_ratio,
    )
    
    # Execute the first trade immediately in a separate thread to avoid blocking
    initial_trade = threading.Thread(target=execute_trade, daemon=True)
    initial_trade.start()
