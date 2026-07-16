from datetime import datetime, timezone
import logging
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
from dotenv import load_dotenv

from decimal import Decimal

# Load environment variables from .env file
load_dotenv()

from database.connection import engine, Base, SessionLocal
from database.models import TradingConfig, User, Account, SystemConfig, AccountAssetSnapshot
from services.asset_curve_calculator import invalidate_asset_curve_cache
from config.settings import DEFAULT_TRADING_CONFIGS
from version import __version__

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hyper Alpha Arena API",
    version=__version__,
    description="Cryptocurrency perpetual contract trading platform with AI-powered decision making"
)

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Trading API is running",
        "version": __version__
    }

# Manual frontend rebuild endpoint
@app.post("/api/rebuild-frontend")
async def rebuild_frontend():
    """Manually trigger frontend rebuild"""
    try:
        build_frontend()
        return {"status": "success", "message": "Frontend rebuild triggered"}
    except Exception as e:
        return {"status": "error", "message": f"Frontend rebuild failed: {str(e)}"}

# CORS: allow same-origin and user-configured origins
_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# Frontend file watcher
frontend_watcher_thread = None
runtime_monitor_thread = None
runtime_monitor_running = False
last_build_time = 0

THREAD_WARNING_THRESHOLDS = (200, 400, 800, 1200)
AI_QUEUE_WARNING_THRESHOLDS = (8, 16, 32)
RUNTIME_MONITOR_INTERVAL_SECONDS = int(os.getenv("RUNTIME_MONITOR_INTERVAL_SECONDS", "300"))


def _get_current_thread_count() -> int:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Threads:"):
                    return int(line.split()[1])
    except Exception:
        return -1
    return -1


def _start_runtime_monitor():
    """Log warning-only threshold crossings for thread growth and AI queue buildup."""
    global runtime_monitor_thread, runtime_monitor_running

    if runtime_monitor_running:
        return

    def monitor_loop():
        from services.ai_stream_service import get_ai_runtime_stats

        thread_level = 0
        task_queue_level = 0
        bg_queue_level = 0

        def get_threshold_level(value: int, thresholds: tuple[int, ...]) -> int:
            level = 0
            for idx, threshold in enumerate(thresholds, start=1):
                if value >= threshold:
                    level = idx
                else:
                    break
            return level

        while runtime_monitor_running:
            try:
                thread_count = _get_current_thread_count()
                ai_stats = get_ai_runtime_stats()

                next_thread_level = get_threshold_level(thread_count, THREAD_WARNING_THRESHOLDS) if thread_count >= 0 else 0
                if next_thread_level > thread_level:
                    threshold = THREAD_WARNING_THRESHOLDS[next_thread_level - 1]
                    logger.warning(
                        "[RuntimeMonitor] Thread count crossed threshold: threads=%s threshold=%s ai_running=%s ai_task_queue=%s ai_bg_queue=%s",
                        thread_count,
                        threshold,
                        ai_stats["running_tasks"],
                        ai_stats["task_queue"],
                        ai_stats["background_queue"],
                    )
                thread_level = next_thread_level

                next_task_queue_level = get_threshold_level(ai_stats["task_queue"], AI_QUEUE_WARNING_THRESHOLDS)
                if next_task_queue_level > task_queue_level:
                    threshold = AI_QUEUE_WARNING_THRESHOLDS[next_task_queue_level - 1]
                    logger.warning(
                        "[RuntimeMonitor] AI task queue crossed threshold: queue=%s threshold=%s running=%s workers=%s threads=%s",
                        ai_stats["task_queue"],
                        threshold,
                        ai_stats["running_tasks"],
                        ai_stats["task_max_workers"],
                        ai_stats["task_threads"],
                    )
                task_queue_level = next_task_queue_level

                next_bg_queue_level = get_threshold_level(ai_stats["background_queue"], AI_QUEUE_WARNING_THRESHOLDS)
                if next_bg_queue_level > bg_queue_level:
                    threshold = AI_QUEUE_WARNING_THRESHOLDS[next_bg_queue_level - 1]
                    logger.warning(
                        "[RuntimeMonitor] AI background queue crossed threshold: queue=%s threshold=%s workers=%s threads=%s",
                        ai_stats["background_queue"],
                        threshold,
                        ai_stats["background_max_workers"],
                        ai_stats["background_threads"],
                    )
                bg_queue_level = next_bg_queue_level

            except Exception as e:
                print(f"[runtime-monitor] non-fatal monitor error: {e}", flush=True)

            time.sleep(RUNTIME_MONITOR_INTERVAL_SECONDS)

    runtime_monitor_running = True
    runtime_monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="runtime-monitor")
    runtime_monitor_thread.start()

def build_frontend():
    """Build frontend and copy to static directory"""
    global last_build_time
    current_time = time.time()

    # Prevent rapid rebuilds (minimum 5 seconds between builds)
    if current_time - last_build_time < 5:
        return

    try:
        print("Frontend files changed, rebuilding...")
        frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
        static_dir = os.path.join(os.path.dirname(__file__), "static")

        # Build frontend
        result = subprocess.run(
            ["pnpm", "build"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            # Copy to static directory
            dist_dir = os.path.join(frontend_dir, "dist")
            if os.path.exists(dist_dir):
                # Clear static directory
                if os.path.exists(static_dir):
                    import shutil
                    shutil.rmtree(static_dir)

                # Copy dist to static
                shutil.copytree(dist_dir, static_dir)
                print("Frontend rebuilt and deployed successfully")
                last_build_time = current_time
            else:
                print("ERROR: Frontend dist directory not found after build")
        else:
            print(f"ERROR: Frontend build failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("ERROR: Frontend build timed out")
    except Exception as e:
        print(f"ERROR: Frontend build failed: {e}")

def watch_frontend_files():
    """Watch frontend files for changes"""
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
    if not os.path.exists(frontend_dir):
        return

    # Simple file watcher using modification times
    file_times = {}
    watch_extensions = {'.tsx', '.ts', '.jsx', '.js', '.css', '.html', '.json'}

    def get_file_times():
        times = {}
        for root, dirs, files in os.walk(frontend_dir):
            # Skip node_modules and dist directories
            dirs[:] = [d for d in dirs if d not in ['node_modules', 'dist', '.git']]

            for file in files:
                if any(file.endswith(ext) for ext in watch_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        times[file_path] = os.path.getmtime(file_path)
                    except OSError:
                        pass
        return times

    file_times = get_file_times()

    while True:
        try:
            time.sleep(2)  # Check every 2 seconds
            current_times = get_file_times()

            # Check for changes
            changed = False
            for file_path, mtime in current_times.items():
                if file_path not in file_times or file_times[file_path] != mtime:
                    changed = True
                    break

            # Check for deleted files
            if not changed:
                for file_path in file_times:
                    if file_path not in current_times:
                        changed = True
                        break

            if changed:
                file_times = current_times
                build_frontend()

        except Exception as e:
            print(f"Frontend watcher error: {e}")
            time.sleep(5)

@app.on_event("startup")
def on_startup():
    global frontend_watcher_thread

    # Start frontend file watcher in background thread
    frontend_watcher_thread = threading.Thread(target=watch_frontend_files, daemon=True)
    frontend_watcher_thread.start()
    print("Frontend file watcher started")

    _start_runtime_monitor()
    print("Runtime monitor started")

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Run all migrations (idempotent - safe to run every startup)
    try:
        from database.migration_manager import run_all_migrations
        run_all_migrations()
    except Exception as e:
        print(f"[startup] Migration error (non-fatal): {e}")

    # Run schema validator to auto-fix missing columns
    try:
        from database.schema_validator import validate_and_sync_schema
        validate_and_sync_schema()
    except Exception as e:
        print(f"[startup] Schema validation error (non-fatal): {e}")

    # Seed trading configs if empty
    db: Session = SessionLocal()
    try:
        # Ensure AI decision log table has snapshot columns (backfill on existing installs)
        try:
            # PostgreSQL-compatible column check
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'ai_decision_logs'
            """))
            columns = {row[0] for row in result}

            if "prompt_snapshot" not in columns:
                db.execute(text("ALTER TABLE ai_decision_logs ADD COLUMN prompt_snapshot TEXT"))
            if "reasoning_snapshot" not in columns:
                db.execute(text("ALTER TABLE ai_decision_logs ADD COLUMN reasoning_snapshot TEXT"))
            if "decision_snapshot" not in columns:
                db.execute(text("ALTER TABLE ai_decision_logs ADD COLUMN decision_snapshot TEXT"))
            db.commit()
        except Exception as migration_err:
            db.rollback()
            print(f"[startup] Failed to ensure AI decision log snapshot columns: {migration_err}")

        # Ensure global_sampling_configs has sampling_depth column (for existing installs)
        try:
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'global_sampling_configs'
            """))
            columns = {row[0] for row in result}

            if "sampling_depth" not in columns:
                db.execute(text("ALTER TABLE global_sampling_configs ADD COLUMN sampling_depth INTEGER NOT NULL DEFAULT 10"))
                print("[startup] Added sampling_depth column to global_sampling_configs")
            db.commit()
        except Exception as migration_err:
            db.rollback()
            print(f"[startup] Failed to ensure global_sampling_configs.sampling_depth: {migration_err}")

        # Ensure crypto_klines has exchange column (for multi-exchange support)
        try:
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'crypto_klines'
            """))
            columns = {row[0] for row in result}

            if "exchange" not in columns:
                print("[startup] Adding exchange column to crypto_klines table...")
                # Add exchange column with default value
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    ADD COLUMN exchange VARCHAR(20) NOT NULL DEFAULT 'hyperliquid'
                """))
                # Create index on exchange field
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_klines_exchange ON crypto_klines(exchange)
                """))
                # Drop old unique constraint (without exchange)
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    DROP CONSTRAINT IF EXISTS crypto_klines_symbol_market_period_timestamp_key
                """))
                print("[startup] Successfully added exchange column to crypto_klines")
            db.commit()
        except Exception as migration_err:
            db.rollback()
            print(f"[startup] Failed to ensure crypto_klines.exchange: {migration_err}")

        # Ensure crypto_klines has environment column (for testnet/mainnet isolation)
        try:
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'crypto_klines'
            """))
            columns = {row[0] for row in result}

            if "environment" not in columns:
                print("[startup] Adding environment column to crypto_klines table...")
                # Add environment column with default value
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    ADD COLUMN environment VARCHAR(20) NOT NULL DEFAULT 'mainnet'
                """))

                # Update all existing records to 'mainnet' (they were from mainnet API)
                db.execute(text("""
                    UPDATE crypto_klines SET environment = 'mainnet' WHERE environment IS NULL
                """))

                # Drop old unique constraints if exist
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    DROP CONSTRAINT IF EXISTS crypto_klines_exchange_symbol_market_period_timestamp_key
                """))
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    DROP CONSTRAINT IF EXISTS uq_crypto_klines_unique
                """))

                # Create new unique constraint including environment
                db.execute(text("""
                    ALTER TABLE crypto_klines
                    ADD CONSTRAINT crypto_klines_exchange_symbol_market_period_timestamp_environment_key
                    UNIQUE (exchange, symbol, market, period, timestamp, environment)
                """))

                # Create performance indexes
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_klines_environment ON crypto_klines(environment)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_klines_symbol_period_env ON crypto_klines(symbol, period, environment)
                """))

                print("[startup] Successfully added environment column to crypto_klines")
            db.commit()
        except Exception as migration_err:
            db.rollback()
            print(f"[startup] Failed to ensure crypto_klines.environment: {migration_err}")

        if db.query(TradingConfig).count() == 0:
            for cfg in DEFAULT_TRADING_CONFIGS.values():
                db.add(
                    TradingConfig(
                        version="v1",
                        market=cfg.market,
                        min_commission=cfg.min_commission,
                        commission_rate=cfg.commission_rate,
                        exchange_rate=cfg.exchange_rate,
                        min_order_quantity=cfg.min_order_quantity,
                        lot_size=cfg.lot_size,
                    )
                )
            db.commit()

        # Ensure default user exists
        default_user = db.query(User).filter(User.username == "default").first()
        if not default_user:
            default_user = User(
                username="default",
                email=None,
                password_hash=None,
                is_active="true"
            )
            db.add(default_user)
            db.commit()
            db.refresh(default_user)
        
        # No default account creation - users must create their own accounts

    finally:
        db.close()

    # ============================================================
    # Upgrade: Initialize Hyperliquid trading mode config & fix NULL environment data
    # ============================================================
    # This ensures:
    # 1. New installations have hyperliquid_trading_mode config initialized
    # 2. Existing installations with NULL ai_decision_logs.hyperliquid_environment get fixed
    # 3. Fixes ModelChat empty data issue for GitHub users
    # ============================================================
    db = SessionLocal()
    try:
        # Step 1: Initialize hyperliquid_trading_mode config if missing
        config = db.query(SystemConfig).filter(
            SystemConfig.key == "hyperliquid_trading_mode"
        ).first()

        if not config:
            config = SystemConfig(
                key="hyperliquid_trading_mode",
                value="testnet",
                description="Global Hyperliquid trading environment: 'testnet' or 'mainnet'. Controls which network all AI Traders connect to."
            )
            db.add(config)
            db.commit()
            print("✓ [Upgrade] Initialized global hyperliquid_trading_mode to 'testnet'")
        else:
            print(f"✓ [Upgrade] Global hyperliquid_trading_mode already configured: {config.value}")

        # Step 2: One-time migration - fix NULL hyperliquid_environment in ai_decision_logs
        # Check if there are any NULL records
        null_count = db.execute(text("""
            SELECT COUNT(*) FROM ai_decision_logs WHERE hyperliquid_environment IS NULL
        """)).scalar()

        if null_count > 0:
            print(f"⚠ [Upgrade] Found {null_count} ai_decision_logs with NULL hyperliquid_environment, fixing...")

            # Update all NULL records to 'testnet' (safe default)
            updated = db.execute(text("""
                UPDATE ai_decision_logs
                SET hyperliquid_environment = 'testnet'
                WHERE hyperliquid_environment IS NULL
            """))
            db.commit()

            print(f"✓ [Upgrade] Updated {null_count} records from NULL to 'testnet' (ModelChat fix)")
        else:
            print("✓ [Upgrade] No NULL hyperliquid_environment records found, data is clean")

    except Exception as e:
        db.rollback()
        print(f"✗ [Upgrade] Hyperliquid environment upgrade failed: {e}")
        # Non-fatal - continue startup
    finally:
        db.close()

    # Ensure prompt templates exist
    db = SessionLocal()
    try:
        from services.prompt_initializer import seed_prompt_templates
        seed_prompt_templates(db)
    finally:
        db.close()
    
    # Initialize system log collector
    from services.system_logger import setup_system_logger
    setup_system_logger()

    # Load and apply global sampling configuration (use watchlist if available)
    try:
        from database.models import GlobalSamplingConfig
        from services.sampling_pool import sampling_pool
        from services.trading_commands import AI_TRADING_SYMBOLS
        from services.hyperliquid_symbol_service import get_selected_symbols as get_hyperliquid_selected_symbols

        db = SessionLocal()
        try:
            symbols = get_hyperliquid_selected_symbols() or AI_TRADING_SYMBOLS
            global_config = db.query(GlobalSamplingConfig).first()
            if global_config and global_config.sampling_depth:
                for symbol in symbols:
                    sampling_pool.set_max_samples(symbol, global_config.sampling_depth)
                print(f"✓ Sampling pool configured: depth={global_config.sampling_depth} for {len(symbols)} symbols")
            else:
                print(f"⚠ No global sampling config found, using default depth={sampling_pool.default_max_samples} for {len(symbols)} symbols")
        finally:
            db.close()
    except Exception as e:
        print(f"✗ Failed to load global sampling config: {e}")

    # Clean up any leftover backfill tasks from previous runs
    try:
        from database.models import KlineCollectionTask
        db = SessionLocal()
        try:
            # Delete all running and pending backfill tasks
            deleted_count = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.status.in_(['running', 'pending'])
            ).delete(synchronize_session=False)
            db.commit()
            if deleted_count > 0:
                print(f"✓ Cleaned up {deleted_count} leftover backfill tasks")
        finally:
            db.close()
    except Exception as e:
        print(f"⚠ Failed to clean up backfill tasks: {e}")

    # Initialize all services (scheduler, market data tasks, auto trading, etc.)
    print("About to initialize services...")
    from services.startup import initialize_services
    initialize_services()
    print("Services initialization completed")

    # Warmup numba JIT compilation for pandas_ta indicators
    # This prevents timeout on first indicator calculation
    def warmup_numba():
        try:
            from services.technical_indicators import calculate_indicator
            from database.connection import SessionLocal
            db = SessionLocal()
            try:
                print("[startup] Warming up numba JIT compilation...")
                calculate_indicator(db, "BTC", "BOLL", "1h")
                print("[startup] Numba warmup completed")
            finally:
                db.close()
        except Exception as e:
            print(f"[startup] Numba warmup failed (non-fatal): {e}")

    # Run warmup in background thread to not block startup
    threading.Thread(target=warmup_numba, daemon=True).start()


@app.on_event("startup")
async def restore_bot_webhooks():
    """Restore Telegram webhook and register adapter after container restart."""
    try:
        from services.telegram_bot_service import restore_telegram_webhook, get_telegram_adapter
        from services.bot_adapter import register_adapter
        from services.bot_service import get_decrypted_bot_token
        from database.connection import SessionLocal
        from database.models import BotConfig

        await restore_telegram_webhook()

        # Register Telegram adapter if connected
        db = SessionLocal()
        try:
            config = db.query(BotConfig).filter(
                BotConfig.platform == "telegram",
                BotConfig.status == "connected"
            ).first()
            if config:
                token = get_decrypted_bot_token(db, "telegram")
                if token:
                    adapter = get_telegram_adapter()
                    await adapter.start(token)
                    register_adapter(adapter)
                    print(f"[startup] Telegram adapter registered")
        finally:
            db.close()
    except Exception as e:
        print(f"[startup] Telegram webhook restore failed (non-fatal): {e}")


@app.on_event("startup")
async def restore_discord_gateway():
    """Restore Discord Gateway connection and register adapter after container restart."""
    try:
        from database.connection import SessionLocal
        from database.models import BotConfig
        from services.bot_service import get_decrypted_bot_token
        from services.discord_bot_service import start_discord_gateway, get_discord_adapter
        from services.bot_adapter import register_adapter
        from api.bot_routes import _process_discord_message_internal
        import asyncio

        db = SessionLocal()
        try:
            config = db.query(BotConfig).filter(
                BotConfig.platform == "discord",
                BotConfig.status == "connected"
            ).first()

            if not config:
                return

            token = get_decrypted_bot_token(db, "discord")
            if not token:
                return

            # Register Discord adapter
            adapter = get_discord_adapter()
            await adapter.start(token)
            register_adapter(adapter)
            print(f"[startup] Discord adapter registered")

            async def handle_discord_message(user_id: int, username: str, display_name: str, text: str) -> str:
                return await _process_discord_message_internal(user_id, username, display_name, text)

            asyncio.create_task(start_discord_gateway(token, handle_discord_message))
            print(f"[startup] Discord Gateway restore initiated for @{config.bot_username}")
        finally:
            db.close()
    except Exception as e:
        print(f"[startup] Discord Gateway restore failed (non-fatal): {e}")


@app.on_event("startup")
async def startup_hyper_insight_wallet_runtime():
    """Start Hyper Insight wallet runtime service."""
    try:
        from services.hyper_insight_wallet_service import hyper_insight_wallet_service
        await hyper_insight_wallet_service.startup()
        print("[startup] Hyper Insight wallet runtime initialized")
    except Exception as e:
        print(f"[startup] Hyper Insight wallet runtime failed (non-fatal): {e}")


@app.on_event("shutdown")
def on_shutdown():
    global runtime_monitor_running
    runtime_monitor_running = False

    # Shutdown all services (scheduler, market data tasks, auto trading, etc.)
    from services.startup import shutdown_services
    shutdown_services()


@app.on_event("shutdown")
async def shutdown_discord_gateway():
    """Stop Discord Gateway on shutdown."""
    try:
        from services.discord_bot_service import stop_discord_gateway
        await stop_discord_gateway()
    except Exception as e:
        print(f"[shutdown] Discord Gateway stop failed (non-fatal): {e}")


@app.on_event("shutdown")
async def shutdown_hyper_insight_wallet_runtime():
    """Stop Hyper Insight wallet runtime service."""
    try:
        from services.hyper_insight_wallet_service import hyper_insight_wallet_service
        await hyper_insight_wallet_service.shutdown()
    except Exception as e:
        print(f"[shutdown] Hyper Insight wallet runtime stop failed (non-fatal): {e}")


# API routes
from api.market_data_routes import router as market_data_router
from api.order_routes import router as order_router
from api.account_routes import router as account_router
from api.config_routes import router as config_router
from api.ranking_routes import router as ranking_router
from api.crypto_routes import router as crypto_router
from api.arena_routes import router as arena_router
from api.system_log_routes import router as system_log_router
from api.prompt_routes import router as prompt_router
from api.sampling_routes import router as sampling_router
from api.hyperliquid_action_routes import router as hyperliquid_action_router
from api.hyperliquid_routes import router as hyperliquid_router
from api.user_routes import router as user_router
from api.kline_routes import router as kline_router
from api.kline_analysis_routes import router as kline_analysis_router
from api.market_flow_routes import router as market_flow_router
from api.signal_routes import router as signal_router
from api.market_regime_routes import router as market_regime_router
from api.analytics_routes import router as analytics_router
from api.trader_data_routes import router as trader_data_router
from api.prompt_backtest_routes import router as prompt_backtest_router
from api.system_routes import router as system_router
from api.binance_routes import router as binance_router
from api.ai_stream_routes import router as ai_stream_router
from api.hyper_ai_routes import router as hyper_ai_router
from api.bot_routes import router as bot_router
from api.factor_routes import router as factor_router
from api.news_routes import router as news_router
from api.market_intelligence_routes import router as market_intelligence_router
from api.paper_trading_routes import router as paper_trading_router
from routes.program_routes import router as program_router
# Removed: AI account routes merged into account_routes (unified AI trader accounts)

app.include_router(market_data_router)
app.include_router(order_router)
app.include_router(account_router)
app.include_router(config_router)
app.include_router(ranking_router)
app.include_router(crypto_router)
app.include_router(arena_router)
app.include_router(system_log_router)
app.include_router(prompt_router)
app.include_router(sampling_router)
app.include_router(hyperliquid_action_router)
app.include_router(hyperliquid_router)
app.include_router(user_router)
app.include_router(kline_router)
app.include_router(kline_analysis_router)
app.include_router(market_flow_router)
app.include_router(signal_router)
app.include_router(market_regime_router)
app.include_router(analytics_router)
app.include_router(trader_data_router)
app.include_router(prompt_backtest_router)
app.include_router(program_router)
app.include_router(system_router)
app.include_router(binance_router)
app.include_router(ai_stream_router)
app.include_router(hyper_ai_router)
app.include_router(bot_router)
app.include_router(factor_router)
app.include_router(news_router)
app.include_router(market_intelligence_router)
app.include_router(paper_trading_router)
# app.include_router(ai_account_router, prefix="/api")  # Removed - merged into account_router

# Strategy route aliases for frontend compatibility
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from database.connection import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/accounts/{account_id}/strategy")
async def get_account_strategy_alias(account_id: int, db: Session = Depends(get_db)):
    """Alias for strategy config endpoint"""
    from api.account_routes import get_account_strategy
    return await get_account_strategy(account_id, db)

@app.put("/api/accounts/{account_id}/strategy")
async def update_account_strategy_alias(account_id: int, payload: dict, db: Session = Depends(get_db)):
    """Alias for strategy config endpoint"""
    from api.account_routes import update_account_strategy
    from schemas.account import StrategyConfigUpdate
    from pydantic import ValidationError
    try:
        strategy_update = StrategyConfigUpdate(**payload)
        return await update_account_strategy(account_id, strategy_update, db)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/strategy/status")
async def get_strategy_manager_status():
    """Get strategy manager status"""
    from services.trading_strategy import get_strategy_status
    return get_strategy_status()

# WebSocket endpoint
from api.ws import websocket_endpoint

app.websocket("/ws")(websocket_endpoint)

# Serve auth config file
@app.get("/auth-config.json")
async def serve_auth_config():
    """Serve the auth configuration file"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    config_path = os.path.join(static_dir, "auth-config.json")

    if os.path.exists(config_path):
        return FileResponse(
            config_path,
            media_type="application/json",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Auth config not found")

# Serve frontend index.html for root and SPA routes
@app.get("/")
async def serve_root():
    """Serve the frontend index.html for root route"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = os.path.join(static_dir, "index.html")

    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    else:
        return {"message": "Frontend not built yet"}

# Catch-all route for SPA routing (must be last)
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the frontend index.html for SPA routes that don't match API/static"""
    # Skip API and static routes
    if full_path.startswith("api") or full_path.startswith("static") or full_path.startswith("docs") or full_path.startswith("openapi.json") or full_path == "auth-config.json":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = os.path.join(static_dir, "index.html")
    
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    else:
        return {"message": "Frontend not built yet"}
