from sqlalchemy import Column, Integer, BigInteger, String, DECIMAL, TIMESTAMP, ForeignKey, UniqueConstraint, Float, Date, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
import datetime

from .connection import Base


class User(Base):
    """
    User for authentication and account management
    In this project, use the default user, no user login
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=True)  # For future password authentication
    is_active = Column(String(10), nullable=False, default="true")
    
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    accounts = relationship("Account", back_populates="user")
    auth_sessions = relationship("UserAuthSession", back_populates="user")
    subscription = relationship("UserSubscription", back_populates="user", uselist=False)


class Account(Base):
    """Trading Account with AI model configuration"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    version = Column(String(100), nullable=False, default="v1")
    
    # Account Identity
    name = Column(String(100), nullable=False)  # Display name (e.g., "GPT Trader", "Claude Analyst")
    account_type = Column(String(20), nullable=False, default="AI")  # "AI" or "MANUAL"
    is_active = Column(String(10), nullable=False, default="true")
    auto_trading_enabled = Column(String(10), nullable=False, default="true")
    
    # AI Model Configuration (for AI accounts)
    model = Column(String(100), nullable=True, default="gpt-4")  # AI model name
    base_url = Column(String(500), nullable=True, default="https://api.openai.com/v1")  # API endpoint
    api_key = Column(String(500), nullable=True)  # API key for authentication
    
    # Trading Account Balances (USD for CRYPTO market)
    initial_capital = Column(DECIMAL(18, 2), nullable=False, default=10000.00)
    current_cash = Column(DECIMAL(18, 2), nullable=False, default=10000.00)
    frozen_cash = Column(DECIMAL(18, 2), nullable=False, default=0.00)

    # Hyperliquid Trading Configuration
    hyperliquid_enabled = Column(String(10), nullable=False, default="false")
    hyperliquid_environment = Column(String(20), nullable=True)  # "testnet" | "mainnet" | null
    hyperliquid_testnet_private_key = Column(String(500), nullable=True)  # Encrypted storage
    hyperliquid_mainnet_private_key = Column(String(500), nullable=True)  # Encrypted storage
    max_leverage = Column(Integer, nullable=True, default=3)  # Maximum allowed leverage
    default_leverage = Column(Integer, nullable=True, default=1)  # Default leverage for orders

    # Dashboard visibility
    show_on_dashboard = Column(Boolean, nullable=False, default=True)  # Show/hide on Dashboard views

    # Arena View avatar preset (1-12, assigned randomly on creation)
    avatar_preset_id = Column(Integer, nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User", back_populates="accounts")
    positions = relationship("Position", back_populates="account")
    orders = relationship("Order", back_populates="account")
    prompt_binding = relationship(
        "AccountPromptBinding",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserAuthSession(Base):
    __tablename__ = "user_auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    
    user = relationship("User", back_populates="auth_sessions")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(100), nullable=False, default="v1")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    market = Column(String(10), nullable=False)
    quantity = Column(DECIMAL(18, 8), nullable=False, default=0)  # Support fractional crypto amounts
    available_quantity = Column(DECIMAL(18, 8), nullable=False, default=0)
    avg_cost = Column(DECIMAL(18, 6), nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account", back_populates="positions")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(100), nullable=False, default="v1")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    order_no = Column(String(32), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False)  # e.g., 'BTC/USD'
    name = Column(String(100), nullable=False)   # e.g., 'Bitcoin'
    market = Column(String(10), nullable=False, default="CRYPTO")
    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)
    price = Column(DECIMAL(18, 6))
    quantity = Column(DECIMAL(18, 8), nullable=False)  # Support fractional crypto amounts
    filled_quantity = Column(DECIMAL(18, 8), nullable=False, default=0)
    status = Column(String(20), nullable=False)

    # Hyperliquid specific fields
    hyperliquid_environment = Column(String(20), nullable=True)  # "testnet" | "mainnet" | null
    leverage = Column(Integer, nullable=True, default=1)  # Position leverage (1-50)
    margin_mode = Column(String(20), nullable=True, default="cross")  # "cross" or "isolated"
    reduce_only = Column(String(10), nullable=True, default="false")  # Only close positions
    hyperliquid_order_id = Column(String(50), nullable=True)  # OID from Hyperliquid API
    liquidation_price = Column(DECIMAL(18, 6), nullable=True)  # Liquidation price for position

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account", back_populates="orders")
    trades = relationship("Trade", back_populates="order")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    symbol = Column(String(20), nullable=False)  # e.g., 'BTC/USD'
    name = Column(String(100), nullable=False)   # e.g., 'Bitcoin'
    market = Column(String(10), nullable=False, default="CRYPTO")
    side = Column(String(10), nullable=False)
    price = Column(DECIMAL(18, 6), nullable=False)
    quantity = Column(DECIMAL(18, 8), nullable=False)  # Support fractional crypto amounts
    commission = Column(DECIMAL(18, 6), nullable=False, default=0)
    trade_time = Column(TIMESTAMP, server_default=func.current_timestamp())

    # Hyperliquid environment tracking
    hyperliquid_environment = Column(String(20), nullable=True)  # "testnet" | "mainnet" | null (paper)

    order = relationship("Order", back_populates="trades")


class TradingConfig(Base):
    __tablename__ = "trading_configs"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(100), nullable=False, default="v1")
    market = Column(String(10), nullable=False)
    min_commission = Column(Float, nullable=False)
    commission_rate = Column(Float, nullable=False)
    exchange_rate = Column(Float, nullable=False, default=1.0)
    min_order_quantity = Column(Integer, nullable=False, default=1)
    lot_size = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    __table_args__ = (UniqueConstraint('market', 'version'),)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class CryptoPrice(Base):
    __tablename__ = "crypto_prices"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="CRYPTO")
    price = Column(DECIMAL(18, 6), nullable=False)
    price_date = Column(Date, nullable=False, index=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    __table_args__ = (UniqueConstraint('symbol', 'market', 'price_date'),)


class CryptoKline(Base):
    __tablename__ = "crypto_klines"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="CRYPTO")
    period = Column(String(10), nullable=False)  # 1m, 5m, 15m, 30m, 1h, 1d
    timestamp = Column(Integer, nullable=False, index=True)
    datetime_str = Column(String(50), nullable=False)
    environment = Column(String(20), nullable=False, default="mainnet", index=True)  # testnet or mainnet
    open_price = Column(DECIMAL(18, 6), nullable=True)
    high_price = Column(DECIMAL(18, 6), nullable=True)
    low_price = Column(DECIMAL(18, 6), nullable=True)
    close_price = Column(DECIMAL(18, 6), nullable=True)
    volume = Column(DECIMAL(18, 2), nullable=True)
    amount = Column(DECIMAL(18, 2), nullable=True)
    change = Column(DECIMAL(18, 6), nullable=True)
    percent = Column(DECIMAL(10, 4), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (UniqueConstraint('exchange', 'symbol', 'market', 'period', 'timestamp', 'environment'),)


class CryptoPriceTick(Base):
    __tablename__ = "crypto_price_ticks"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="CRYPTO")
    price = Column(DECIMAL(18, 8), nullable=False)
    event_time = Column(TIMESTAMP, nullable=False, index=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())


class AccountAssetSnapshot(Base):
    __tablename__ = "account_asset_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    total_assets = Column(DECIMAL(18, 6), nullable=False)
    cash = Column(DECIMAL(18, 6), nullable=False)
    positions_value = Column(DECIMAL(18, 6), nullable=False)
    trigger_symbol = Column(String(20), nullable=True)
    trigger_market = Column(String(10), nullable=True, default="CRYPTO")
    event_time = Column(TIMESTAMP, nullable=False, index=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    account = relationship("Account")


class AccountStrategyConfig(Base):
    __tablename__ = "account_strategy_configs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True)
    price_threshold = Column(Float, nullable=False, default=1.0)  # Deprecated, kept for compatibility
    trigger_interval = Column(Integer, nullable=False, default=150)  # Trigger interval (seconds)
    # Note: Foreign key constraint exists at DB level (via migration), but not in ORM
    # because signal_pools table is managed via raw SQL, not SQLAlchemy models
    signal_pool_id = Column(Integer, nullable=True)  # Deprecated: use signal_pool_ids instead
    signal_pool_ids = Column(Text, nullable=True)  # JSON array of signal pool IDs, e.g. "[1, 2, 3]"
    enabled = Column(String(10), nullable=False, default="true")
    scheduled_trigger_enabled = Column(Boolean, nullable=False, default=True)  # Enable/disable scheduled trigger
    exchange = Column(String(20), nullable=False, default="hyperliquid")  # "hyperliquid" or "binance"
    execution_mode = Column(String(10), nullable=False, default="real")  # "real" or "paper"
    last_trigger_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account")


class GlobalSamplingConfig(Base):
    __tablename__ = "global_sampling_configs"

    id = Column(Integer, primary_key=True, index=True)
    sampling_interval = Column(Integer, nullable=False, default=18)  # Sampling interval (seconds)
    sampling_depth = Column(Integer, nullable=False, default=10)  # Sampling pool depth (10-60)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class UserSubscription(Base):
    """User subscription for premium features"""
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    subscription_type = Column(String(20), nullable=False, default="free")  # "free" | "premium"
    expires_at = Column(TIMESTAMP, nullable=True)  # NULL for free tier or lifetime premium
    max_sampling_depth = Column(Integer, nullable=False, default=10)  # Free: 10, Premium: up to 60
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationship
    user = relationship("User", back_populates="subscription")


class AIDecisionLog(Base):
    __tablename__ = "ai_decision_logs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    decision_time = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    reason = Column(String(1000), nullable=False)  # AI reasoning for the decision
    operation = Column(String(10), nullable=False)  # buy/sell/hold
    symbol = Column(String(20), nullable=True)  # symbol for buy/sell operations
    prev_portion = Column(DECIMAL(10, 6), nullable=False, default=0)  # previous balance portion
    target_portion = Column(DECIMAL(10, 6), nullable=False)  # target balance portion
    total_balance = Column(DECIMAL(18, 2), nullable=False)  # total balance at decision time
    executed = Column(String(10), nullable=False, default="false")  # whether the decision was executed
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)  # linked order if executed
    prompt_snapshot = Column(Text, nullable=True)
    reasoning_snapshot = Column(Text, nullable=True)
    decision_snapshot = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    # Hyperliquid environment tracking
    hyperliquid_environment = Column(String(20), nullable=True)  # "testnet" | "mainnet" | null (paper)
    wallet_address = Column(String(100), nullable=True, index=True)

    # Decision tracking fields for analysis
    prompt_template_id = Column(Integer, nullable=True, index=True)  # Link to strategy/prompt template OR program
    signal_trigger_id = Column(Integer, nullable=True, index=True)  # Link to signal trigger
    # NOTE: hyperliquid_order_id is used as exchange_order_id for attribution analysis
    # It stores order IDs from any exchange (Hyperliquid, Binance, etc.), not just Hyperliquid
    hyperliquid_order_id = Column(String(100), nullable=True, index=True)  # Main order ID (exchange-agnostic)
    tp_order_id = Column(String(100), nullable=True)  # Take profit order ID
    sl_order_id = Column(String(100), nullable=True)  # Stop loss order ID
    realized_pnl = Column(DECIMAL(18, 6), nullable=True)  # Realized PnL (filled on user refresh)
    pnl_updated_at = Column(TIMESTAMP, nullable=True)  # When PnL was last updated

    # Decision source type: "prompt_template" (AI Trader) or "program" (Program Trader)
    # NULL for old data, treated as "prompt_template" for backward compatibility
    decision_source_type = Column(String(20), nullable=True)

    # Exchange identifier: "hyperliquid" or "binance"
    # NULL for historical data, treated as "hyperliquid" for backward compatibility
    exchange = Column(String(20), nullable=True)

    # Relationships
    account = relationship("Account")
    order = relationship("Order")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), nullable=False, index=True)  # Removed unique constraint to allow copies
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    template_text = Column(Text, nullable=False)
    system_template_text = Column(Text, nullable=False)

    # User-level template support
    is_system = Column(String(10), nullable=False, default="false")  # System templates cannot be deleted
    is_deleted = Column(String(10), nullable=False, default="false")  # Soft delete
    deleted_at = Column(TIMESTAMP, nullable=True)  # When soft-deleted
    created_by = Column(String(100), nullable=False, default="system")  # Creator identifier

    updated_by = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account_bindings = relationship(
        "AccountPromptBinding",
        back_populates="prompt_template",
        cascade="all, delete-orphan",
    )


class AccountPromptBinding(Base):
    __tablename__ = "account_prompt_bindings"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True)
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False)
    updated_by = Column(String(100), nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account", back_populates="prompt_binding")
    prompt_template = relationship("PromptTemplate", back_populates="account_bindings")


class HyperliquidWallet(Base):
    """Store Hyperliquid wallet configurations per AI Trader per environment

    One-to-many relationship with Account. Each AI Trader can have multiple wallets
    (one for testnet, one for mainnet).
    """
    __tablename__ = "hyperliquid_wallets"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    # Environment (testnet or mainnet)
    environment = Column(String(20), nullable=False)  # 'testnet' or 'mainnet'

    # Wallet credentials (encrypted)
    private_key_encrypted = Column(String(500), nullable=False)
    wallet_address = Column(String(100), nullable=False, index=True)  # Parsed from private key

    # Trading configuration
    max_leverage = Column(Integer, nullable=False, default=3)  # Maximum allowed leverage (1-50)
    default_leverage = Column(Integer, nullable=False, default=1)  # Default leverage for new orders

    # Agent Wallet support
    key_type = Column(String(20), nullable=False, default="private_key")  # "private_key" or "agent_key"
    master_wallet_address = Column(String(100), nullable=True)  # Required for agent_key mode (query balance/positions)
    agent_valid_until = Column(TIMESTAMP, nullable=True)  # Agent key expiration time

    # Status
    is_active = Column(String(10), nullable=False, default="true")

    # Metadata
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Unique constraint: one wallet per account per environment
    __table_args__ = (
        UniqueConstraint('account_id', 'environment', name='uq_hyperliquid_wallets_account_environment'),
    )

    # Relationships
    account = relationship("Account")


class HyperliquidAccountSnapshot(Base):
    """Store Hyperliquid account state snapshots for audit and analysis"""
    __tablename__ = "hyperliquid_account_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    environment = Column(String(20), nullable=False, index=True)  # "testnet" | "mainnet"
    wallet_address = Column(String(100), nullable=True, index=True)
    snapshot_time = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Account state
    total_equity = Column(DECIMAL(18, 6), nullable=False)
    available_balance = Column(DECIMAL(18, 6), nullable=False)
    used_margin = Column(DECIMAL(18, 6), nullable=False)
    maintenance_margin = Column(DECIMAL(18, 6), nullable=False)

    # Snapshot metadata
    trigger_event = Column(String(50), nullable=True)  # "pre_decision", "post_order", etc.
    snapshot_data = Column(Text, nullable=True)  # JSON of full API response

    account = relationship("Account")


class HyperliquidPosition(Base):
    """Store Hyperliquid position snapshots"""
    __tablename__ = "hyperliquid_positions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    environment = Column(String(20), nullable=False, index=True)  # "testnet" | "mainnet"
    wallet_address = Column(String(100), nullable=True, index=True)
    snapshot_time = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    symbol = Column(String(20), nullable=False)
    position_size = Column(DECIMAL(18, 8), nullable=False)  # Signed: positive=long, negative=short
    entry_price = Column(DECIMAL(18, 6), nullable=False)
    current_price = Column(DECIMAL(18, 6), nullable=False)
    position_value = Column(DECIMAL(18, 6), nullable=False)
    unrealized_pnl = Column(DECIMAL(18, 6), nullable=False)
    margin_used = Column(DECIMAL(18, 6), nullable=False)
    liquidation_price = Column(DECIMAL(18, 6), nullable=True)
    leverage = Column(Integer, nullable=False)

    # Link to order that created/modified this position
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)

    account = relationship("Account")
    order = relationship("Order")


class HyperliquidExchangeAction(Base):
    """Track every POST /exchange action for Hyperliquid accounts"""
    __tablename__ = "hyperliquid_exchange_actions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    environment = Column(String(20), nullable=False, index=True)
    wallet_address = Column(String(100), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)  # e.g., create_order, set_leverage
    status = Column(String(20), nullable=False, default="success")  # success | error
    symbol = Column(String(20), nullable=True)
    side = Column(String(10), nullable=True)
    leverage = Column(Integer, nullable=True)
    size = Column(DECIMAL(24, 12), nullable=True)
    price = Column(DECIMAL(18, 6), nullable=True)
    notional = Column(DECIMAL(26, 10), nullable=True)
    request_weight = Column(Integer, nullable=False, default=1)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    account = relationship("Account")


class PerpFunding(Base):
    """Store perpetual contract funding rate data from multiple exchanges"""
    __tablename__ = "perp_funding"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False, index=True)
    funding_rate = Column(DECIMAL(18, 8), nullable=False)
    mark_price = Column(DECIMAL(18, 6), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (UniqueConstraint('exchange', 'symbol', 'timestamp'),)


class PriceSample(Base):
    """Store price sampling data for persistent sampling pools"""
    __tablename__ = "price_samples"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(DECIMAL(18, 8), nullable=False)
    sample_time = Column(TIMESTAMP, nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    # Relationships
    account = relationship("Account")


class UserExchangeConfig(Base):
    """Store user exchange selection preferences"""
    __tablename__ = "user_exchange_config"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    selected_exchange = Column(String(20), nullable=False, default="hyperliquid")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")


class KlineCollectionTask(Base):
    """Store K-line data collection task status"""
    __tablename__ = "kline_collection_tasks"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    start_time = Column(TIMESTAMP, nullable=False)
    end_time = Column(TIMESTAMP, nullable=False)
    period = Column(String(10), nullable=False, default="1m")
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Integer, nullable=False, default=0)
    total_records = Column(Integer, default=0)
    collected_records = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class BinanceWallet(Base):
    """Store Binance Futures API credentials per AI Trader per environment"""
    __tablename__ = "binance_wallets"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    environment = Column(String(20), nullable=False)  # 'testnet' or 'mainnet'
    api_key_encrypted = Column(String(500), nullable=False)
    secret_key_encrypted = Column(String(500), nullable=False)
    max_leverage = Column(Integer, nullable=False, default=20)
    default_leverage = Column(Integer, nullable=False, default=1)
    is_active = Column(String(10), nullable=False, default="true")
    # Binance API broker rebate eligibility status (mainnet only)
    # True: eligible for rebate, False: not eligible (daily quota limit applies)
    rebate_working = Column(Boolean, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint('account_id', 'environment', name='uq_binance_wallets_account_environment'),
    )

    account = relationship("Account")


class BinanceAccountSnapshot(Base):
    """Store Binance account state snapshots"""
    __tablename__ = "binance_account_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    environment = Column(String(20), nullable=False, index=True)
    snapshot_time = Column(TIMESTAMP, server_default=func.current_timestamp())
    total_wallet_balance = Column(DECIMAL(18, 6), nullable=False)
    available_balance = Column(DECIMAL(18, 6), nullable=False)
    total_unrealized_profit = Column(DECIMAL(18, 6), nullable=False)
    total_margin_balance = Column(DECIMAL(18, 6), nullable=False)
    total_initial_margin = Column(DECIMAL(18, 6), nullable=True)
    total_maint_margin = Column(DECIMAL(18, 6), nullable=True)
    trigger_event = Column(String(50), nullable=True)
    snapshot_data = Column(Text, nullable=True)

    account = relationship("Account")


class BinanceBackfillTask(Base):
    """Store Binance data backfill task status"""
    __tablename__ = "binance_backfill_tasks"

    id = Column(Integer, primary_key=True, index=True)
    symbols = Column(String(200), nullable=False)  # Comma-separated symbols
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class HyperliquidBackfillTask(Base):
    """Store Hyperliquid K-line backfill task status"""
    __tablename__ = "hyperliquid_backfill_tasks"

    id = Column(Integer, primary_key=True, index=True)
    symbols = Column(String(200), nullable=False)  # Comma-separated symbols
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class KlineAIAnalysisLog(Base):
    """Store K-line AI analysis logs for chart insights"""
    __tablename__ = "kline_ai_analysis_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    # Analysis context
    symbol = Column(String(20), nullable=False, index=True)
    period = Column(String(10), nullable=False)  # K-line period (1m, 5m, 1h, etc.)
    user_message = Column(Text, nullable=True)  # User's custom question

    # AI model info
    model_used = Column(String(100), nullable=False)

    # Snapshots
    prompt_snapshot = Column(Text, nullable=True)  # Full prompt sent to AI
    analysis_result = Column(Text, nullable=True)  # AI's analysis response (Markdown)

    # Metadata
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    user = relationship("User")
    account = relationship("Account")


class AiPromptConversation(Base):
    """AI Prompt Generation Conversation Sessions"""
    __tablename__ = "ai_prompt_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    prompt_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False, default="New Strategy Prompt")
    compression_points = Column(Text, nullable=True)  # JSON array of compression records
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")
    prompt_template = relationship("PromptTemplate")
    messages = relationship(
        "AiPromptMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AiPromptMessage.created_at"
    )


class AiPromptMessage(Base):
    """Messages in AI Prompt Generation Conversations"""
    __tablename__ = "ai_prompt_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_prompt_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content (markdown)

    # For assistant messages: extracted prompt from ```prompt``` code block
    prompt_result = Column(Text, nullable=True)

    # Reasoning and tool call logs (aligned with AiProgramMessage)
    reasoning_snapshot = Column(Text, nullable=True)  # AI reasoning process (thinking)
    tool_calls_log = Column(Text, nullable=True)  # JSON: tool calls and results

    # Completion status for retry/continue functionality
    is_complete = Column(Boolean, default=True)  # False = interrupted, can retry
    interrupt_reason = Column(Text, nullable=True)  # Reason for interruption (API error, timeout, etc.)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    conversation = relationship("AiPromptConversation", back_populates="messages")


class AiSignalConversation(Base):
    """AI Signal Creation Conversation Sessions"""
    __tablename__ = "ai_signal_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="New Signal")
    compression_points = Column(Text, nullable=True)  # JSON array of compression records
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")
    messages = relationship(
        "AiSignalMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AiSignalMessage.created_at"
    )


class AiSignalMessage(Base):
    """Messages in AI Signal Creation Conversations"""
    __tablename__ = "ai_signal_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_signal_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content (markdown)

    # For assistant messages: extracted signal configs from ```signal-config``` code blocks
    signal_configs = Column(Text, nullable=True)  # JSON array of signal configurations

    # Reasoning and tool call logs (aligned with other AI assistants)
    reasoning_snapshot = Column(Text, nullable=True)  # AI reasoning process (thinking)
    tool_calls_log = Column(Text, nullable=True)  # JSON: tool calls and results
    is_complete = Column(Boolean, nullable=True, default=True)  # False if interrupted
    interrupt_reason = Column(Text, nullable=True)  # API error, timeout, user cancel, etc.

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    conversation = relationship("AiSignalConversation", back_populates="messages")


class AiAttributionConversation(Base):
    """AI Attribution Analysis Conversation Sessions"""
    __tablename__ = "ai_attribution_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="New Analysis")
    compression_points = Column(Text, nullable=True)  # JSON array of compression records
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")
    messages = relationship(
        "AiAttributionMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AiAttributionMessage.created_at"
    )


class AiAttributionMessage(Base):
    """Messages in AI Attribution Analysis Conversations"""
    __tablename__ = "ai_attribution_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_attribution_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content (markdown)

    # For assistant messages: extracted diagnosis results from AI analysis
    diagnosis_result = Column(Text, nullable=True)  # JSON: diagnosis cards and prompt suggestions

    # Reasoning and tool call logs (aligned with other AI assistants)
    reasoning_snapshot = Column(Text, nullable=True)  # AI reasoning process
    tool_calls_log = Column(Text, nullable=True)  # JSON: tool calls and results log
    is_complete = Column(Boolean, nullable=True, default=True)  # False if interrupted
    interrupt_reason = Column(Text, nullable=True)  # API error, timeout, user cancel, etc.

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    conversation = relationship("AiAttributionConversation", back_populates="messages")


class AiProgramConversation(Base):
    """AI Program Coding Conversation Sessions"""
    __tablename__ = "ai_program_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("trading_programs.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False, default="New Program")
    compression_points = Column(Text, nullable=True)  # JSON array of compression records
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")
    program = relationship("TradingProgram")
    messages = relationship(
        "AiProgramMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AiProgramMessage.created_at"
    )


class AiProgramMessage(Base):
    """Messages in AI Program Coding Conversations"""
    __tablename__ = "ai_program_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_program_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content (markdown)

    # For assistant messages: code suggestion that needs user confirmation
    code_suggestion = Column(Text, nullable=True)  # Python code to save (requires user confirm)

    # Reasoning and tool call logs
    reasoning_snapshot = Column(Text, nullable=True)  # AI reasoning process (thinking)
    tool_calls_log = Column(Text, nullable=True)  # JSON: tool calls and results

    # Completion status for retry/continue functionality
    is_complete = Column(Boolean, default=True)  # False = interrupted, can retry
    interrupt_reason = Column(Text, nullable=True)  # Reason for interruption (API error, timeout, etc.)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    conversation = relationship("AiProgramConversation", back_populates="messages")


# ============================================================================
# Market Flow Data Tables (for fund flow analysis)
# ============================================================================

class MarketTradesAggregated(Base):
    """15-second aggregated trade data for CVD and Taker Volume analysis"""
    __tablename__ = "market_trades_aggregated"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # milliseconds
    taker_buy_volume = Column(DECIMAL(24, 8), nullable=False, default=0)
    taker_sell_volume = Column(DECIMAL(24, 8), nullable=False, default=0)
    taker_buy_count = Column(Integer, nullable=False, default=0)
    taker_sell_count = Column(Integer, nullable=False, default=0)
    taker_buy_notional = Column(DECIMAL(24, 6), nullable=False, default=0)
    taker_sell_notional = Column(DECIMAL(24, 6), nullable=False, default=0)
    vwap = Column(DECIMAL(18, 6), nullable=True)
    high_price = Column(DECIMAL(18, 6), nullable=True)
    low_price = Column(DECIMAL(18, 6), nullable=True)
    # Large order tracking fields
    large_buy_notional = Column(DECIMAL(24, 6), nullable=False, default=0, server_default=text("0"))
    large_sell_notional = Column(DECIMAL(24, 6), nullable=False, default=0, server_default=text("0"))
    large_buy_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    large_sell_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'symbol', 'timestamp',
                         name='market_trades_aggregated_exchange_symbol_timestamp_key'),
    )


class MarketOrderbookSnapshots(Base):
    """Order book snapshots for depth ratio and liquidity analysis"""
    __tablename__ = "market_orderbook_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # milliseconds
    best_bid = Column(DECIMAL(18, 6), nullable=True)
    best_ask = Column(DECIMAL(18, 6), nullable=True)
    spread = Column(DECIMAL(18, 6), nullable=True)
    bid_depth_5 = Column(DECIMAL(24, 8), nullable=False, default=0)
    ask_depth_5 = Column(DECIMAL(24, 8), nullable=False, default=0)
    bid_depth_10 = Column(DECIMAL(24, 8), nullable=False, default=0)
    ask_depth_10 = Column(DECIMAL(24, 8), nullable=False, default=0)
    bid_orders_count = Column(Integer, nullable=False, default=0)
    ask_orders_count = Column(Integer, nullable=False, default=0)
    raw_levels = Column(Text, nullable=True)  # JSON string of full orderbook
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'symbol', 'timestamp',
                         name='market_orderbook_snapshots_exchange_symbol_timestamp_key'),
    )


class MarketAssetMetrics(Base):
    """Asset metrics snapshots for OI, Funding Rate, and Premium analysis"""
    __tablename__ = "market_asset_metrics"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # milliseconds
    open_interest = Column(DECIMAL(24, 8), nullable=True)
    funding_rate = Column(DECIMAL(18, 8), nullable=True)
    mark_price = Column(DECIMAL(18, 6), nullable=True)
    oracle_price = Column(DECIMAL(18, 6), nullable=True)
    mid_price = Column(DECIMAL(18, 6), nullable=True)
    premium = Column(DECIMAL(18, 8), nullable=True)
    day_notional_volume = Column(DECIMAL(24, 6), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'symbol', 'timestamp',
                         name='market_asset_metrics_exchange_symbol_timestamp_key'),
    )


class MarketSentimentMetrics(Base):
    """Market sentiment metrics for long/short ratio analysis (Binance-specific data)"""
    __tablename__ = "market_sentiment_metrics"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # milliseconds
    long_ratio = Column(DECIMAL(10, 6), nullable=True)  # e.g., 0.65 = 65% long
    short_ratio = Column(DECIMAL(10, 6), nullable=True)  # e.g., 0.35 = 35% short
    long_short_ratio = Column(DECIMAL(10, 6), nullable=True)  # e.g., 1.86 = longs/shorts
    data_type = Column(String(30), nullable=False, default="top_position")  # top_position, top_account, global
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'symbol', 'timestamp', 'data_type',
                         name='market_sentiment_metrics_unique_key'),
    )


# ============================================================================
# Signal System Tables (for signal-based trading triggers)
# ============================================================================

class SignalDefinition(Base):
    """Signal definitions for market condition triggers"""
    __tablename__ = "signal_definitions"

    id = Column(Integer, primary_key=True, index=True)
    signal_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    trigger_condition = Column(Text, nullable=False)  # JSONB stored as text
    enabled = Column(Boolean, nullable=True, default=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid")

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())


class SignalPool(Base):
    """Signal pools for grouping multiple signals"""
    __tablename__ = "signal_pools"

    id = Column(Integer, primary_key=True, index=True)
    pool_name = Column(String(100), nullable=False)
    signal_ids = Column(Text, nullable=False, default="[]")  # JSONB stored as text
    symbols = Column(Text, nullable=False, default="[]")  # JSONB stored as text
    logic = Column(String(10), nullable=True, default="OR")  # AND/OR logic
    enabled = Column(Boolean, nullable=True, default=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid")
    source_type = Column(String(30), nullable=False, default="market_signals")
    source_config = Column(Text, nullable=False, default="{}")  # wallet_tracking-only JSON config

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())


class SignalTriggerLog(Base):
    """Logs of signal triggers for audit and analysis"""
    __tablename__ = "signal_trigger_logs"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, nullable=True)
    pool_id = Column(Integer, nullable=True)
    symbol = Column(String(20), nullable=False)
    trigger_value = Column(Text, nullable=True)  # JSONB stored as text
    triggered_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    market_regime = Column(Text, nullable=True)  # JSON: {"regime", "direction", "confidence", "reason"}


class TraderTriggerConfig(Base):
    """Configuration for trader trigger settings"""
    __tablename__ = "trader_trigger_config"

    trader_id = Column(String(36), primary_key=True)  # UUID as string
    scheduled_enabled = Column(Boolean, nullable=True, default=True)
    scheduled_interval = Column(Integer, nullable=True, default=30)
    signal_pool_id = Column(Integer, nullable=True)  # Deprecated: use signal_pool_ids instead
    signal_pool_ids = Column(Text, nullable=True)  # JSON array of signal pool IDs, e.g. "[1, 2, 3]"
    last_trigger_time = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())


class MarketRegimeConfig(Base):
    """Configuration for Market Regime classification thresholds"""
    __tablename__ = "market_regime_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=True, default=False)
    rolling_window = Column(Integer, nullable=True, default=48)
    # Breakout thresholds
    breakout_cvd_z = Column(Float, nullable=True, default=1.5)
    breakout_oi_z = Column(Float, nullable=True, default=1.0)
    breakout_price_atr = Column(Float, nullable=True, default=0.5)
    breakout_taker_high = Column(Float, nullable=True, default=1.8)
    breakout_taker_low = Column(Float, nullable=True, default=0.55)
    # Absorption thresholds
    absorption_cvd_z = Column(Float, nullable=True, default=1.5)
    absorption_price_atr = Column(Float, nullable=True, default=0.3)
    # Trap thresholds
    trap_cvd_z = Column(Float, nullable=True, default=1.0)
    trap_oi_z = Column(Float, nullable=True, default=-1.0)
    # Exhaustion thresholds
    exhaustion_cvd_z = Column(Float, nullable=True, default=1.0)
    exhaustion_rsi_high = Column(Float, nullable=True, default=70.0)
    exhaustion_rsi_low = Column(Float, nullable=True, default=30.0)
    # Stop Hunt thresholds
    stop_hunt_range_atr = Column(Float, nullable=True, default=1.0)
    stop_hunt_close_atr = Column(Float, nullable=True, default=0.3)
    # Noise thresholds
    noise_cvd_z = Column(Float, nullable=True, default=0.5)
    # Breakout body ratio (hardcoded 0.4 before, now configurable)
    breakout_body_ratio = Column(Float, nullable=True, default=0.4)
    # Continuation CVD divisor (cvd_weak = cvd_strong / divisor, default 3)
    continuation_cvd_divisor = Column(Float, nullable=True, default=3.0)
    # Timestamps
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())


# ============================================================================
# Prompt Backtest Tables
# ============================================================================

class PromptBacktestTask(Base):
    """Prompt backtest task - batch test prompt modifications against historical decisions"""
    __tablename__ = "prompt_backtest_tasks"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    wallet_address = Column(String(100), nullable=True, index=True)
    environment = Column(String(20), nullable=True)  # testnet/mainnet
    name = Column(String(200), nullable=True)  # User-defined task name
    status = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed
    total_count = Column(Integer, nullable=False, default=0)
    completed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    replace_rules = Column(Text, nullable=True)  # JSON: replacement rules used
    started_at = Column(TIMESTAMP, nullable=True)
    finished_at = Column(TIMESTAMP, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())

    # Relationships
    account = relationship("Account")
    items = relationship("PromptBacktestItem", back_populates="task", cascade="all, delete-orphan")


class PromptBacktestItem(Base):
    """Individual item in a prompt backtest task"""
    __tablename__ = "prompt_backtest_items"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("prompt_backtest_tasks.id"), nullable=False, index=True)
    original_decision_log_id = Column(Integer, ForeignKey("ai_decision_logs.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed
    error_message = Column(Text, nullable=True)

    # Original data snapshot
    original_operation = Column(String(20), nullable=True)
    original_symbol = Column(String(20), nullable=True)
    original_target_portion = Column(DECIMAL(10, 6), nullable=True)
    original_reasoning = Column(Text, nullable=True)
    original_decision_json = Column(Text, nullable=True)
    original_realized_pnl = Column(DECIMAL(18, 6), nullable=True)
    original_decision_time = Column(TIMESTAMP, nullable=True)
    original_prompt_template_name = Column(String(200), nullable=True)

    # Modified prompt (cache)
    modified_prompt = Column(Text, nullable=True)

    # New decision results
    new_operation = Column(String(20), nullable=True)
    new_symbol = Column(String(20), nullable=True)
    new_target_portion = Column(DECIMAL(10, 6), nullable=True)
    new_reasoning = Column(Text, nullable=True)
    new_decision_json = Column(Text, nullable=True)

    # Derived fields
    decision_changed = Column(Boolean, nullable=True)
    change_type = Column(String(50), nullable=True)  # e.g., buy_to_hold
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    # Relationships
    task = relationship("PromptBacktestTask", back_populates="items")
    original_decision_log = relationship("AIDecisionLog")


# ============================================================================
# Program Trader Tables
# ============================================================================

class TradingProgram(Base):
    """Trading program (reusable strategy code template)"""
    __tablename__ = "trading_programs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Program definition
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)  # Python strategy code
    params = Column(Text, nullable=True)  # JSON: default parameters
    icon = Column(String(50), nullable=True)  # Icon identifier for UI

    # Backtest results cache
    last_backtest_result = Column(Text, nullable=True)  # JSON
    last_backtest_at = Column(TIMESTAMP, nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user = relationship("User")
    bindings = relationship("AccountProgramBinding", back_populates="program")
    execution_logs = relationship("ProgramExecutionLog", back_populates="program", passive_deletes=True)


class AccountProgramBinding(Base):
    """Binding between AI Trader (Account) and Trading Program with trigger config"""
    __tablename__ = "account_program_bindings"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("trading_programs.id"), nullable=False, index=True)

    # Trigger configuration
    signal_pool_ids = Column(Text, nullable=True)  # JSON: [1, 2, 3]
    trigger_interval = Column(Integer, nullable=False, default=300)  # seconds
    scheduled_trigger_enabled = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_trigger_at = Column(TIMESTAMP, nullable=True)

    # Custom params override (optional, overrides program.params)
    params_override = Column(Text, nullable=True)  # JSON

    # Exchange selection for this binding (hyperliquid or binance)
    exchange = Column(String(20), nullable=False, default="hyperliquid")

    # Soft delete
    is_deleted = Column(Boolean, nullable=False, server_default=text('false'))
    deleted_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    account = relationship("Account")
    program = relationship("TradingProgram", back_populates="bindings")
    execution_logs = relationship("ProgramExecutionLog", back_populates="binding")


class ProgramExecutionLog(Base):
    """Execution log for trading programs"""
    __tablename__ = "program_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    binding_id = Column(Integer, ForeignKey("account_program_bindings.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("trading_programs.id", ondelete="SET NULL"), nullable=True, index=True)
    program_name = Column(String(200), nullable=True)  # Stored for history when program is deleted

    # Trigger info
    trigger_type = Column(String(20), nullable=False)  # "signal" or "scheduled"
    trigger_symbol = Column(String(20), nullable=True)
    signal_pool_id = Column(Integer, nullable=True)  # Which signal pool triggered
    wallet_address = Column(String(100), nullable=True)  # Which wallet was used

    # Execution result
    success = Column(Boolean, nullable=False)
    decision_action = Column(String(20), nullable=True)  # buy/sell/close/hold
    decision_symbol = Column(String(20), nullable=True)
    decision_size_usd = Column(Float, nullable=True)
    decision_leverage = Column(Integer, nullable=True)
    decision_reason = Column(Text, nullable=True)
    decision_json = Column(Text, nullable=True)  # Full decision as JSON
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)

    # Context snapshots for analysis/backtest
    market_context = Column(Text, nullable=True)  # JSON: market data at execution time
    params_snapshot = Column(Text, nullable=True)  # JSON: params used for this execution

    # Order tracking for Completed Trades integration
    # NOTE: hyperliquid_order_id is used as exchange_order_id for attribution analysis
    # It stores order IDs from any exchange (Hyperliquid, Binance, etc.), not just Hyperliquid
    hyperliquid_order_id = Column(String(100), nullable=True, index=True)  # Main order ID (exchange-agnostic)
    tp_order_id = Column(String(100), nullable=True)  # Take profit order ID
    sl_order_id = Column(String(100), nullable=True)  # Stop loss order ID

    # Environment and PnL tracking (for attribution analysis)
    environment = Column(String(20), nullable=True, index=True)  # "testnet" | "mainnet"
    realized_pnl = Column(DECIMAL(18, 6), nullable=True)  # Realized PnL (filled on user refresh)
    pnl_updated_at = Column(TIMESTAMP, nullable=True)  # When PnL was last updated

    # Exchange identifier: "hyperliquid" or "binance"
    # NULL for historical data, treated as "hyperliquid" for backward compatibility
    exchange = Column(String(20), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    binding = relationship("AccountProgramBinding", back_populates="execution_logs")
    account = relationship("Account")
    program = relationship("TradingProgram")


# ============================================================================
# BACKTEST SYSTEM
# ============================================================================
class BacktestResult(Base):
    """
    Stores backtest results for both Program and Prompt (future) backtests.
    """
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, index=True)
    backtest_type = Column(String(20), nullable=False, default="program")  # "program" | "prompt"
    binding_id = Column(Integer, ForeignKey("account_program_bindings.id"), nullable=True)
    prompt_id = Column(Integer, nullable=True)  # For future prompt backtest
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Configuration
    config = Column(Text, nullable=True)  # JSON: full config snapshot

    # Time range
    start_time = Column(TIMESTAMP, nullable=True)
    end_time = Column(TIMESTAMP, nullable=True)

    # Results
    initial_balance = Column(Float, default=10000)
    final_equity = Column(Float, nullable=True)
    total_pnl = Column(Float, default=0)
    total_pnl_percent = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    max_drawdown_percent = Column(Float, default=0)

    # Statistics
    total_triggers = Column(Integer, default=0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    profit_factor = Column(Float, default=0)
    sharpe_ratio = Column(Float, nullable=True)

    # Equity curve (JSON array)
    equity_curve = Column(Text, nullable=True)

    # Execution info
    execution_time_ms = Column(Integer, nullable=True)
    status = Column(String(20), default="running")  # "running" | "completed" | "error"
    error_message = Column(Text, nullable=True)

    # Exchange used for data source: "hyperliquid" or "binance"
    # NULL for historical data, treated as "hyperliquid" for backward compatibility
    exchange = Column(String(20), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    completed_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    trigger_logs = relationship("BacktestTriggerLog", back_populates="backtest", cascade="all, delete-orphan")


class BacktestTriggerLog(Base):
    """
    Stores detailed logs for each trigger during backtest.
    Supports both Program decisions and AI decisions (future).
    """
    __tablename__ = "backtest_trigger_logs"

    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(Integer, ForeignKey("backtest_results.id", ondelete="CASCADE"), nullable=False)
    trigger_index = Column(Integer, nullable=False)

    # Trigger info
    trigger_type = Column(String(20), nullable=True)  # "signal" | "scheduled"
    trigger_time = Column(TIMESTAMP, nullable=True)
    symbol = Column(String(20), nullable=True)

    # Decision info
    decision_type = Column(String(20), default="program")  # "program" | "ai"
    decision_action = Column(String(20), nullable=True)  # "open_long" | "close" | "hold" | etc.
    decision_symbol = Column(String(20), nullable=True)
    decision_side = Column(String(10), nullable=True)  # "long" | "short"
    decision_size = Column(Float, nullable=True)
    decision_reason = Column(Text, nullable=True)

    # Trade result
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    fee = Column(Float, nullable=True)  # Trading fee for this trigger
    unrealized_pnl = Column(Float, nullable=True)  # Current unrealized PnL
    realized_pnl = Column(Float, nullable=True)  # Realized PnL from this trade

    # Equity tracking
    equity_before = Column(Float, nullable=True)
    equity_after = Column(Float, nullable=True)

    # Full snapshots (JSON)
    decision_input = Column(Text, nullable=True)  # MarketData snapshot
    decision_output = Column(Text, nullable=True)  # Full decision result
    data_queries = Column(Text, nullable=True)  # Data queries during execution (JSON)
    execution_logs = Column(Text, nullable=True)  # log() outputs during execution (JSON)

    # Error tracking
    execution_error = Column(Text, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    # Relationships
    backtest = relationship("BacktestResult", back_populates="trigger_logs")


# ============================================================================
# Hyper AI - Main Agent for Full-Site AI Intelligence
# ============================================================================
# Hyper AI is the master agent that:
# - Guides users through onboarding and profile setup
# - Maintains user memory (preferences, decisions, lessons, insights)
# - Orchestrates sub-agents (Prompt AI, Program AI, Signal AI, Attribution AI)
# - Handles context compression for long conversations
# ============================================================================


class HyperAiProfile(Base):
    """
    Hyper AI User Profile - Stores user trading preferences and LLM configuration.

    This is the core profile for Hyper AI, containing:
    - Trading style and risk preferences (collected during onboarding)
    - LLM provider configuration (API endpoint, key, model)
    - Onboarding status

    Single-user system: only one profile exists per installation.
    """
    __tablename__ = "hyper_ai_profile"

    id = Column(Integer, primary_key=True, index=True)

    # User identity
    nickname = Column(String(100), nullable=True)  # User's preferred name/nickname

    # Trading preferences (collected during onboarding conversation)
    trading_style = Column(String(50), nullable=True)  # trend_following / mean_reversion / mixed
    risk_preference = Column(String(50), nullable=True)  # conservative / moderate / aggressive
    experience_level = Column(String(50), nullable=True)  # beginner / intermediate / expert
    preferred_symbols = Column(Text, nullable=True)  # JSON array: ["BTC", "ETH", "SOL"]
    preferred_timeframe = Column(String(50), nullable=True)  # short / medium / long
    capital_scale = Column(String(50), nullable=True)  # small / medium / large

    # Onboarding status
    onboarding_completed = Column(Boolean, default=False)  # True after initial setup conversation

    # LLM provider configuration (user selects during onboarding)
    llm_provider = Column(String(50), nullable=True)  # openai / anthropic / google / deepseek / zhipu / minimax / minimax-cn / openrouter / qwen / moonshot / custom
    llm_base_url = Column(String(500), nullable=True)  # API endpoint URL
    llm_api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key (use decrypt_private_key to read)
    llm_model = Column(String(100), nullable=True)  # Model name (e.g., gpt-4o, claude-opus-4-6)

    # Skill System: Controls which Skill modules are active for this user.
    # Skills are SKILL.md files in backend/skills/ that provide domain-specific
    # workflow guidance to Hyper AI (e.g., strategy setup, diagnosis, market analysis).
    # Format: JSON array of enabled skill names, e.g. ["prompt-strategy-setup", "market-analysis"]
    # NULL = all skills enabled (default for new/existing users)
    enabled_skills = Column(Text, nullable=True)

    # External tool configurations (e.g., Tavily web search, future tools)
    # Format: JSON dict keyed by tool name, e.g. {"tavily": {"api_key_encrypted": "...", "enabled": true}}
    # API keys are encrypted using encrypt_private_key() before storage
    tool_configs = Column(Text, nullable=True)

    # Suggested questions for welcome screen (lazy-updated cache)
    # Format: JSON array of 3 questions, e.g. ["How is my BTC Trader doing?", ...]
    # Updated asynchronously when user visits Hyper AI page and cache > 6 hours old
    suggested_questions = Column(Text, nullable=True)
    suggested_questions_at = Column(TIMESTAMP, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class HyperAiMemory(Base):
    """
    Hyper AI User Memory - Stores AI-extracted insights about the user.

    Memory categories:
    - preference: User preferences (e.g., "likes trend following strategies")
    - decision: User decisions (e.g., "chose 5-minute timeframe for signals")
    - lesson: Trading lessons (e.g., "got caught chasing pumps last time")
    - insight: Strategy insights (e.g., "this strategy underperforms in ranging markets")

    Memory lifecycle:
    - Created: AI extracts from conversations or trade results
    - Updated: AI merges similar memories (Mem0-style deduplication)
    - Soft-deleted: is_active=False when contradicted by newer information
    """
    __tablename__ = "hyper_ai_memory"

    id = Column(Integer, primary_key=True, index=True)

    # Memory content
    category = Column(String(50), nullable=False, index=True)  # preference / decision / lesson / insight
    content = Column(Text, nullable=False)  # The actual memory text

    # Memory metadata
    source = Column(String(50), nullable=True)  # onboarding / prompt_chat / program_chat / signal_chat / trade_result / backtest
    importance = Column(Float, default=0.5)  # 0.0-1.0, higher = more important for retrieval
    is_active = Column(Boolean, default=True)  # False = soft-deleted (contradicted by newer memory)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class HyperAiConversation(Base):
    """
    Hyper AI Conversation Session - Tracks conversation history with compression support.

    Compression mechanism:
    - When token count approaches 70% of context window, compression is triggered
    - AI generates a summary of the conversation
    - Old messages are deleted, summary is stored in this table
    - New messages continue from the compressed state
    """
    __tablename__ = "hyper_ai_conversations"

    id = Column(Integer, primary_key=True, index=True)

    # Conversation metadata
    title = Column(String(200), nullable=False, default="Hyper AI Chat")
    is_onboarding = Column(Boolean, default=False)  # True for onboarding conversations (hidden from history)

    # Compression data
    summary = Column(Text, nullable=True)  # Compressed summary of old messages (after compression)
    compression_points = Column(Text, nullable=True)  # JSON array of compression records
    message_count = Column(Integer, default=0)  # Total messages before compression
    total_tokens = Column(Integer, default=0)  # Estimated total tokens (for compression trigger)

    # Bot integration
    is_bot_conversation = Column(Boolean, default=False)  # True if initiated from Telegram/Discord bot
    bot_platform = Column(String(20), nullable=True)  # telegram / discord

    # Timestamps
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    compressed_at = Column(TIMESTAMP, nullable=True)  # When compression was performed

    # Relationships
    messages = relationship(
        "HyperAiMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="HyperAiMessage.created_at"
    )


class HyperAiMessage(Base):
    """
    Hyper AI Message - Individual messages in a conversation.

    Stores full message details including:
    - Content and role (user/assistant/system/tool)
    - AI reasoning process (thinking/chain-of-thought)
    - Tool calls and results (function calling)
    - Sub-agent orchestration logs (calls to Prompt/Program/Signal/Attribution AI)
    - Completion status for retry functionality
    """
    __tablename__ = "hyper_ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("hyper_ai_conversations.id"), nullable=False, index=True)

    # Message content
    role = Column(String(20), nullable=False)  # user / assistant / system / tool
    content = Column(Text, nullable=False)  # Message content (markdown supported)

    # AI reasoning and tool usage (for assistant messages)
    reasoning_snapshot = Column(Text, nullable=True)  # AI thinking process (chain-of-thought, extended thinking)
    tool_calls_log = Column(Text, nullable=True)  # JSON: [{name, arguments, result}, ...] - function calling log
    subagent_calls_log = Column(Text, nullable=True)  # JSON: [{agent, task, result}, ...] - sub-agent orchestration log

    # Completion status (for retry/continue functionality)
    is_complete = Column(Boolean, default=True)  # False = interrupted, can retry
    interrupt_reason = Column(Text, nullable=True)  # API error, timeout, user cancel, etc.

    # Token tracking (for compression calculation)
    token_count = Column(Integer, nullable=True)  # Estimated tokens in this message

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), index=True)

    # Relationships
    conversation = relationship("HyperAiConversation", back_populates="messages")


# ============================================================================
# CRYPTO market trading configuration constants
# ============================================================================
CRYPTO_MIN_COMMISSION = 0.1  # $0.1 minimum commission
CRYPTO_COMMISSION_RATE = 0.001  # 0.1% commission rate
CRYPTO_MIN_ORDER_QUANTITY = 1
CRYPTO_LOT_SIZE = 1


# ============================================================================
# Bot Integration
# ============================================================================
class BotConfig(Base):
    """Bot platform configuration (Telegram / Discord)"""
    __tablename__ = "bot_configs"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), unique=True, nullable=False)  # telegram / discord
    bot_token_encrypted = Column(Text, nullable=True)
    bot_username = Column(String(100), nullable=True)
    bot_app_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="disconnected")
    error_message = Column(Text, nullable=True)
    webhook_url = Column(Text, nullable=True)  # Last successful webhook URL (for auto-restore on restart)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class BotChatBinding(Base):
    """Track chat_ids that have interacted with the bot (for push broadcast)."""
    __tablename__ = "bot_chat_bindings"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), nullable=False)  # telegram / discord
    chat_id = Column(String(100), nullable=False)
    username = Column(String(100), nullable=True)
    display_name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    last_message_at = Column(TIMESTAMP, server_default=func.current_timestamp())


# ============================================================================
# Factor System Tables
# ============================================================================

class FactorValue(Base):
    """Computed factor values for each symbol/period/timestamp"""
    __tablename__ = "factor_values"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid")
    symbol = Column(String(20), nullable=False)
    period = Column(String(10), nullable=False)
    factor_name = Column(String(80), nullable=False)
    factor_category = Column(String(30), nullable=False)
    timestamp = Column(Integer, nullable=False)  # Unix seconds
    value = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'symbol', 'period', 'factor_name', 'timestamp',
                         name='factor_values_unique_key'),
    )


class FactorEffectiveness(Base):
    """Factor effectiveness metrics (IC, ICIR, win rate, etc.)"""
    __tablename__ = "factor_effectiveness"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(20), nullable=False, default="hyperliquid")
    factor_name = Column(String(80), nullable=False)
    factor_category = Column(String(30), nullable=False)
    symbol = Column(String(20), nullable=False)
    period = Column(String(10), nullable=False)
    forward_period = Column(String(10), nullable=False)
    calc_date = Column(Date, nullable=False)
    lookback_days = Column(Integer, nullable=False, default=30)
    ic_mean = Column(Float, nullable=True)
    ic_std = Column(Float, nullable=True)
    icir = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    decay_half_life = Column(Integer, nullable=True)
    sample_count = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('exchange', 'factor_name', 'symbol', 'period', 'forward_period', 'calc_date',
                         name='factor_effectiveness_unique_key'),
    )


class CustomFactor(Base):
    """User/AI-defined custom factor expressions"""
    __tablename__ = "custom_factors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    expression = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(30), nullable=False, default="custom")
    source = Column(String(20), nullable=False, default="manual")  # manual / ai / builtin
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('name', name='custom_factors_name_unique'),
    )


class NewsArticle(Base):
    """Aggregated news articles from multiple sources for market intelligence"""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    source_domain = Column(String(255), nullable=False, index=True)
    source_url = Column(Text, nullable=False)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    published_at = Column(TIMESTAMP, nullable=True, index=True)
    symbols = Column(Text, nullable=True)  # JSON array: ["BTC","ETH"]
    sentiment = Column(String(20), nullable=True)  # bullish/bearish/neutral
    sentiment_source = Column(String(20), nullable=True)  # api/keyword/ai
    relevance_score = Column(Float, nullable=True)
    ai_summary = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)  # Thumbnail/preview image URL from source
    raw_data = Column(Text, nullable=True)
    classified = Column(Boolean, nullable=False, default=False)
    fetched_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('source_domain', 'source_url',
                         name='news_articles_source_unique'),
    )


# ============================================================================
# Paper Trading Tables (internal simulated execution, mainnet read-only data)
# ============================================================================

class PaperAccount(Base):
    """Per-trader paper trading account (persistent simulated equity)."""
    __tablename__ = "paper_accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True, index=True)
    data_exchange = Column(String(20), nullable=False, default="hyperliquid")  # market data source
    initial_capital = Column(DECIMAL(18, 2), nullable=False, default=10000.00)
    realized_pnl_total = Column(DECIMAL(18, 6), nullable=False, default=0)
    total_fees = Column(DECIMAL(18, 6), nullable=False, default=0)
    total_funding = Column(DECIMAL(18, 6), nullable=False, default=0)  # positive = received
    cycle = Column(Integer, nullable=False, default=1)
    cycle_started_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    # Fee/slippage overrides (NULL = exchange defaults in paper_trading/fees.py)
    taker_fee_pct = Column(DECIMAL(10, 6), nullable=True)
    maker_fee_pct = Column(DECIMAL(10, 6), nullable=True)
    slippage_fallback_pct = Column(DECIMAL(10, 6), nullable=True)
    last_funding_at = Column(TIMESTAMP, nullable=True)
    last_monitor_at = Column(TIMESTAMP, nullable=True)  # for restart kline catch-up
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    account = relationship("Account")


class PaperPosition(Base):
    """Open paper position (netted per symbol, like Hyperliquid)."""
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "long" | "short"
    size = Column(DECIMAL(18, 8), nullable=False)
    entry_price = Column(DECIMAL(18, 6), nullable=False)  # weighted average on add
    leverage = Column(Integer, nullable=False, default=1)
    cycle = Column(Integer, nullable=False, default=1)
    opened_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('paper_account_id', 'symbol', name='uq_paper_positions_account_symbol'),
    )


class PaperOrder(Base):
    """Pending paper order: resting GTC limit, or independent TP/SL trigger order."""
    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    order_no = Column(String(40), unique=True, nullable=False, index=True)  # "P-<hex16>"
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "buy" | "sell"
    order_type = Column(String(20), nullable=False)  # "limit" | "take_profit" | "stop_loss"
    exec_mode = Column(String(10), nullable=False, default="limit")  # "limit" (maker) | "market" (taker+slippage)
    trigger_price = Column(DECIMAL(18, 6), nullable=False)
    size = Column(DECIMAL(18, 8), nullable=False)
    entry_price = Column(DECIMAL(18, 6), nullable=True)  # entry px for TP/SL PnL attribution
    leverage = Column(Integer, nullable=False, default=1)
    reduce_only = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | filled | cancelled
    cycle = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    filled_at = Column(TIMESTAMP, nullable=True)


class PaperFundingRecord(Base):
    """Funding settlement ledger for paper positions."""
    __tablename__ = "paper_funding_records"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    funding_rate = Column(DECIMAL(18, 10), nullable=False)
    position_notional = Column(DECIMAL(18, 6), nullable=False)
    amount = Column(DECIMAL(18, 6), nullable=False)  # positive = received by account
    cycle = Column(Integer, nullable=False, default=1)
    settled_at = Column(TIMESTAMP, server_default=func.current_timestamp())
