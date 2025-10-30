from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import os

from database.connection import engine, Base, SessionLocal
from database.models import TradingConfig, User, Account, SystemConfig
from config.settings import DEFAULT_TRADING_CONFIGS
app = FastAPI(title="Crypto Paper Trading API")

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Trading API is running"}

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


@app.on_event("startup")
def on_startup():
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Seed trading configs if empty
    db: Session = SessionLocal()
    try:
        # Ensure AI decision log table has snapshot columns (backfill on existing installs)
        try:
            columns = {row[1] for row in db.execute(text("PRAGMA table_info(ai_decision_logs)"))}
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
        
        # Ensure default user has at least one account
        default_accounts = db.query(Account).filter(Account.user_id == default_user.id).all()
        if len(default_accounts) == 0:
            # Create default account
            default_account = Account(
                user_id=default_user.id,
                version="v1",
                name="GPT",
                account_type="AI",
                model="gpt-5-mini",
                base_url="https://api.openai.com/v1",
                api_key="default-key-please-update-in-settings",
                initial_capital=10000.0,  # $10,000 starting capital for crypto trading
                current_cash=10000.0,
                frozen_cash=0.0,
                is_active="true"
            )
            db.add(default_account)
            db.commit()
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
    from services.startup import initialize_services
    initialize_services()


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
# app.include_router(ai_account_router, prefix="/api")  # Removed - merged into account_router

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
        return FileResponse(index_path)
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
        return FileResponse(index_path)
    else:
        return {"message": "Frontend not built yet"}
