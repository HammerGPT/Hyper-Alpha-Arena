from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey, UniqueConstraint, Float, Date, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
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
    value = Column(String(5000), nullable=True)  # 增加到5000字符以支持长cookie
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
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="CRYPTO")
    period = Column(String(10), nullable=False)  # 1m, 5m, 15m, 30m, 1h, 1d
    timestamp = Column(Integer, nullable=False, index=True)
    datetime_str = Column(String(50), nullable=False)
    open_price = Column(DECIMAL(18, 6), nullable=True)
    high_price = Column(DECIMAL(18, 6), nullable=True)
    low_price = Column(DECIMAL(18, 6), nullable=True)
    close_price = Column(DECIMAL(18, 6), nullable=True)
    volume = Column(DECIMAL(18, 2), nullable=True)
    amount = Column(DECIMAL(18, 2), nullable=True)
    change = Column(DECIMAL(18, 6), nullable=True)
    percent = Column(DECIMAL(10, 4), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (UniqueConstraint('symbol', 'market', 'period', 'timestamp'),)


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
    trigger_mode = Column(String(20), nullable=False, default="realtime")  # realtime / interval / tick_batch
    interval_seconds = Column(Integer, nullable=True)  # for interval mode
    tick_batch_size = Column(Integer, nullable=True)  # for tick_batch mode
    enabled = Column(String(10), nullable=False, default="true")
    last_trigger_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account")


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

    # Relationships
    account = relationship("Account")
    order = relationship("Order")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    template_text = Column(Text, nullable=False)
    system_template_text = Column(Text, nullable=False)
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
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    account = relationship("Account", back_populates="prompt_binding")
    prompt_template = relationship("PromptTemplate", back_populates="account_bindings")


# CRYPTO market trading configuration constants
CRYPTO_MIN_COMMISSION = 0.1  # $0.1 minimum commission
CRYPTO_COMMISSION_RATE = 0.001  # 0.1% commission rate
CRYPTO_MIN_ORDER_QUANTITY = 1
CRYPTO_LOT_SIZE = 1
