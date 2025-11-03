from pydantic import BaseModel
from typing import Optional


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
    # Phase 2: Live Trading Support
    trading_mode: str = "PAPER"  # PAPER | LIVE
    exchange: Optional[str] = None  # HYPERLIQUID
    wallet_address: Optional[str] = None  # For Hyperliquid wallet-based auth
    testnet_enabled: str = "true"  # true | false
    # Note: exchange_api_key/secret not exposed (defer to Phase 3)

    class Config:
        from_attributes = True


class AccountOverview(BaseModel):
    """Account overview with portfolio information"""
    account: AccountOut
    total_assets: float  # Total assets in USD
    positions_value: float  # Total positions value in USD


class StrategyConfigBase(BaseModel):
    """Base fields shared by strategy config schemas"""
    trigger_mode: str = "unified"
    interval_seconds: Optional[int] = None
    tick_batch_size: Optional[int] = None
    enabled: bool = True
    price_threshold: Optional[float] = None


class StrategyConfigUpdate(StrategyConfigBase):
    """Incoming payload for updating strategy configuration"""
    pass


class StrategyConfig(StrategyConfigBase):
    """Strategy configuration response"""
    last_trigger_at: Optional[str] = None
