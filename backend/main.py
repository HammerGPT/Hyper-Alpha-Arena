from datetime import datetime, timezone
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
app = FastAPI(title="Crypto Paper Trading API")

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Trading API is running"}

# Manual frontend rebuild endpoint
@app.post("/api/rebuild-frontend")
async def rebuild_frontend():
    """Manually trigger frontend rebuild"""
    try:
        build_frontend()
        return {"status": "success", "message": "Frontend rebuild triggered"}
    except Exception as e:
        return {"status": "error", "message": f"Frontend rebuild failed: {str(e)}"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins, or specify specific domains
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
last_build_time = 0

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

    # Create tables
    Base.metadata.create_all(bind=engine)
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
        # Ensure only default user and its account exist
        # Delete all non-default users and their accounts
        from database.models import Position, Order, Trade
        
        non_default_users = db.query(User).filter(User.username != "default").all()
        for user in non_default_users:
            # Get user's account IDs
            account_ids = [acc.id for acc in db.query(Account).filter(Account.user_id == user.id).all()]
            
            if account_ids:
                # Delete trades, orders, positions associated with these accounts
                db.query(Trade).filter(Trade.account_id.in_(account_ids)).delete(synchronize_session=False)
                db.query(Order).filter(Order.account_id.in_(account_ids)).delete(synchronize_session=False)
                db.query(Position).filter(Position.account_id.in_(account_ids)).delete(synchronize_session=False)
                
                # Now delete the accounts
                db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
            
            # Delete the user
            db.delete(user)
        
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

    # Initialize all services (scheduler, market data tasks, auto trading, etc.)
    print("About to initialize services...")
    from services.startup import initialize_services
    initialize_services()
    print("Services initialization completed")


@app.on_event("shutdown")
def on_shutdown():
    # Shutdown all services (scheduler, market data tasks, auto trading, etc.)
    from services.startup import shutdown_services
    shutdown_services()


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
    if full_path.startswith("api") or full_path.startswith("static") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
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
