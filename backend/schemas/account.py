from pydantic import BaseModel
from typing import Optional, List


class AccountCreate(BaseModel):
    """Create a new AI Trading Account"""
    name: str  # Display name (e.g., "GPT Trader", "Claude Analyst")
    model: str = "gpt-4-turbo"
    base_url: str = "https://api.openai.com/v1"
    api_key: str
    initial_capital: float = 10000.0
    account_type: str = "AI"  # "AI" or "MANUAL"


class AccountUpdate(BaseModel):
    """Update AI Trading Account"""
    name: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class AccountOut(BaseModel):
    """AI Trading Account output"""
    id: int
    user_id: int
    name: str
    model: str
    base_url: str
    api_key: str  # Will be masked in API responses
    initial_capital: float
    current_cash: float
    frozen_cash: float
    account_type: str
    is_active: bool

    class Config:
        from_attributes = True


class AccountOverview(BaseModel):
    """Account overview with portfolio information"""
    account: AccountOut
    total_assets: float  # Total assets in USD
    positions_value: float  # Total positions value in USD


class StrategyConfigBase(BaseModel):
    """Base fields shared by strategy config schemas"""
    trigger_mode: Optional[str] = None  # "unified"; omitted in PUT = preserve current
    interval_seconds: Optional[int] = None
    tick_batch_size: Optional[int] = None
    enabled: Optional[bool] = None  # omitted in PUT = preserve current
    scheduled_trigger_enabled: Optional[bool] = None  # omitted in PUT = preserve current
    exchange: Optional[str] = None  # "hyperliquid" or "binance"; omitted in PUT = preserve current
    execution_mode: Optional[str] = None  # "real" or "paper"; omitted in PUT = preserve current
    price_threshold: Optional[float] = None  # Deprecated, kept for compatibility
    signal_pool_id: Optional[int] = None  # Deprecated: use signal_pool_ids instead
    signal_pool_ids: Optional[List[int]] = None  # Multiple signal pools binding (OR relationship)


class StrategyConfigUpdate(StrategyConfigBase):
    """Incoming payload for updating strategy configuration"""
    pass


class StrategyConfig(StrategyConfigBase):
    """Strategy configuration response"""
    last_trigger_at: Optional[str] = None
    signal_pool_name: Optional[str] = None  # Deprecated: use signal_pool_names instead
    signal_pool_names: Optional[List[str]] = None  # Signal pool names for display
    warning: Optional[str] = None  # Warning message if config is incomplete
    # Response-only: reflects the account-level auto-trading pause switch (toggled via
    # PUT /api/account/{account_id}, not this endpoint). Deliberately absent from
    # StrategyConfigBase/StrategyConfigUpdate so a GET->PUT round-trip can never send
    # it back and have it misinterpreted as the per-strategy `enabled` flag.
    auto_trading_enabled: Optional[bool] = None
