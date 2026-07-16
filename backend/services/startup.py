"""Application startup initialization service"""

import logging
import threading

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


def initialize_services():
    """Initialize all services"""
    try:
        # Start the scheduler
        print("Starting scheduler...")
        start_scheduler()
        print("Scheduler started")
        logger.info("Scheduler service started")

        # Refresh Hyperliquid symbol catalog + schedule periodic updates
        refresh_hyperliquid_symbols()
        schedule_symbol_refresh_task()

        # Refresh Binance symbol catalog + schedule periodic updates
        from services.binance_symbol_service import (
            refresh_binance_symbols,
            schedule_symbol_refresh_task as schedule_binance_symbol_refresh,
        )
        refresh_binance_symbols()
        schedule_binance_symbol_refresh()
        logger.info("[Binance] Symbol catalog refreshed and periodic refresh scheduled")

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

        # Use GlobalSamplingConfig.sampling_interval for market stream polling
        # This reduces API calls significantly (from 1.5s to user-configured interval)
        from database.connection import SessionLocal
        from database.models import GlobalSamplingConfig
        with SessionLocal() as db:
            global_config = db.query(GlobalSamplingConfig).first()
            # Default 18s, minimum 5s to prevent misconfiguration
            stream_interval = max(5, global_config.sampling_interval if global_config else 18)

        print(f"Starting market data stream (interval={stream_interval}s)...")
        start_market_stream(combined_symbols, interval_seconds=stream_interval)
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

        # Subscribe Program Trader to price updates (for scheduled triggers)
        from services.program_execution_service import program_execution_service

        def program_price_wrapper(event):
            """Wrapper to convert event format for program execution service"""
            symbol = event.get("symbol")
            price = event.get("price")
            event_time = event.get("event_time")
            if symbol and price:
                program_execution_service.on_price_update(symbol, float(price), event_time)

        subscribe_price_updates(program_price_wrapper)
        logger.info("Program execution service subscribed to price updates")

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
        import asyncio
        asyncio.create_task(hyperliquid_snapshot_service.start())
        logger.info("Hyperliquid snapshot service started (30-second interval)")

        # Start Binance account snapshot service (every 5 minutes)
        from services.binance_snapshot_service import binance_snapshot_service
        asyncio.create_task(binance_snapshot_service.start())
        logger.info("Binance snapshot service started (5-minute interval)")

        # Start K-line realtime collection service
        from services.kline_realtime_collector import realtime_collector
        asyncio.create_task(realtime_collector.start())
        logger.info("K-line realtime collection service started (1-minute interval)")

        # Start market flow data collector (trades, orderbook, OI/funding)
        from services.market_flow_collector import market_flow_collector, cleanup_old_market_flow_data
        print("Starting market flow collector...")
        market_flow_collector.start()
        print("Market flow collector started")
        logger.info("Market flow collector started (15-second aggregation)")

        # Start paper trading monitor (pending orders / liquidation / funding / snapshots)
        from paper_trading.monitor import paper_monitor
        asyncio.create_task(paper_monitor.start())
        logger.info("Paper trading monitor started (3-second interval)")

        # Add market flow data cleanup task (every 6 hours)
        task_scheduler.add_interval_task(
            task_func=cleanup_old_market_flow_data,
            interval_seconds=6 * 3600,  # 6 hours
            task_id="market_flow_data_cleanup"
        )
        logger.info("Market flow data cleanup task started (6-hour interval, 30-day retention)")

        # Start Binance data collector (REST API polling) - uses Binance Watchlist
        from services.exchanges.binance_collector import binance_collector
        from services.binance_symbol_service import get_selected_symbols as get_binance_selected_symbols
        binance_watchlist = get_binance_selected_symbols()
        print(f"Starting Binance data collector with Binance watchlist: {binance_watchlist}")
        binance_collector.start(symbols=binance_watchlist if binance_watchlist else ["BTC"])
        print("Binance data collector started")
        logger.info(f"[Binance] Data collector started with symbols: {binance_watchlist}")

        # Start Binance WebSocket collector (15-second Taker Volume aggregation)
        from services.exchanges.binance_ws_collector import binance_ws_collector
        binance_ws_collector.start(symbols=binance_watchlist if binance_watchlist else ["BTC"])
        print("Binance WebSocket collector started")
        logger.info(f"[Binance] WebSocket collector started with symbols: {binance_watchlist}")

        # Start Factor Computation Engine (if enabled)
        from config.settings import FACTOR_ENGINE_ENABLED
        if FACTOR_ENGINE_ENABLED:
            from services.factor_computation_service import factor_computation_service
            from services.factor_effectiveness_service import factor_effectiveness_service
            factor_computation_service.start()
            factor_effectiveness_service.start()
            logger.info("[FactorEngine] Factor computation + effectiveness services started")
        else:
            print("[FactorEngine] Disabled (set FACTOR_ENGINE_ENABLED=true to enable)")

        # Start News Collector Service (market intelligence)
        from services.news_collector_service import news_collector_service
        news_collector_service.start()
        task_scheduler.add_interval_task(
            task_func=news_collector_service.collect_all,
            interval_seconds=60,  # Check every 60s, per-source intervals respected internally
            task_id="news_collector"
        )
        print("News collector service started")
        logger.info("News collector service started (60s scheduler, per-source intervals)")

        # Start News AI Classification (batch job every 30 minutes)
        from services.news_ai_classifier import classify_pending_articles
        task_scheduler.add_interval_task(
            task_func=classify_pending_articles,
            interval_seconds=1800,  # 30 minutes
            task_id="news_ai_classifier"
        )
        logger.info("News AI classifier scheduled (30-min interval)")

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise


def shutdown_services():
    """Shut down all services"""
    try:
        from services.scheduler import stop_scheduler
        from services.hyperliquid_snapshot_service import hyperliquid_snapshot_service
        from services.kline_realtime_collector import realtime_collector
        import asyncio

        stop_strategy_manager()
        stop_market_stream()
        unsubscribe_price_updates(handle_price_update)
        hyperliquid_snapshot_service.stop()

        # Stop K-line realtime collector
        asyncio.create_task(realtime_collector.stop())

        # Stop market flow collector
        from services.market_flow_collector import market_flow_collector
        market_flow_collector.stop()

        # Stop Binance data collector
        from services.exchanges.binance_collector import binance_collector
        binance_collector.stop()

        # Stop Binance WebSocket collector
        from services.exchanges.binance_ws_collector import binance_ws_collector
        binance_ws_collector.stop()

        # Stop News Collector
        from services.news_collector_service import news_collector_service
        news_collector_service.stop()

        stop_scheduler()
        logger.info("All services have been shut down")

    except Exception as e:
        logger.error(f"Failed to shut down services: {e}")


async def startup_event():
    """FastAPI application startup event"""
    initialize_services()


async def shutdown_event():
    """FastAPI application shutdown event"""
    await shutdown_services()


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
