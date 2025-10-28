from pydantic import BaseModel
from typing import Dict


class MarketConfig(BaseModel):
    market: str
    min_commission: float
    commission_rate: float
    exchange_rate: float
    min_order_quantity: int = 1
    lot_size: int = 1


#  default configs for CRYPTO markets
DEFAULT_TRADING_CONFIGS: Dict[str, MarketConfig] = {
    "CRYPTO": MarketConfig(
        market="CRYPTO",
        min_commission=0.1,  # $0.1 minimum commission for crypto
        commission_rate=0.001,  # 0.1% commission rate (typical for crypto)
        exchange_rate=1.0,  # USD base
        min_order_quantity=1,  # Can trade fractional amounts
        lot_size=1,
    ),
}
