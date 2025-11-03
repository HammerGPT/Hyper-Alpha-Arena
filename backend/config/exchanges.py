"""
Exchange Configuration for Live Trading

This module contains configuration for supported exchanges, including:
- API endpoints (testnet and mainnet)
- WebSocket endpoints
- Commission rates
- Symbol format patterns
- Leverage limits
"""

from typing import Dict, Any


# Hyperliquid Exchange Configuration
HYPERLIQUID_TESTNET = {
    "exchange": "HYPERLIQUID",
    "environment": "TESTNET",
    "api_endpoint": "https://api.hyperliquid-testnet.xyz",
    "ws_endpoint": "wss://api.hyperliquid-testnet.xyz/ws",
    "commission_rate": 0.00025,  # 0.025% (2.5 basis points)
    "min_commission": 0.0,  # No minimum commission on Hyperliquid
    "max_leverage": 50,  # Maximum 50x leverage
}

HYPERLIQUID_MAINNET = {
    "exchange": "HYPERLIQUID",
    "environment": "MAINNET",
    "api_endpoint": "https://api.hyperliquid.xyz",
    "ws_endpoint": "wss://api.hyperliquid.xyz/ws",
    "commission_rate": 0.00025,  # 0.025% (2.5 basis points)
    "min_commission": 0.0,  # No minimum commission on Hyperliquid
    "max_leverage": 50,  # Maximum 50x leverage
}

# Symbol format patterns for Hyperliquid
HYPERLIQUID_SYMBOL_FORMATS = {
    "spot": "{base}/USDC:USDC",  # e.g., BTC/USDC:USDC
    "perp": "{base}-PERP",  # e.g., BTC-PERP
}

# All exchange configurations
EXCHANGE_CONFIGS = [
    HYPERLIQUID_TESTNET,
    HYPERLIQUID_MAINNET,
]

# Exchange features and capabilities
EXCHANGE_FEATURES = {
    "HYPERLIQUID": {
        "supports_spot": True,
        "supports_perpetuals": True,
        "supports_margin": True,
        "requires_wallet_signature": True,  # Hyperliquid uses wallet-based auth
        "supports_api_keys": False,  # Hyperliquid does not use API keys
        "default_quote_currency": "USDC",
    }
}


def get_exchange_config(exchange: str, environment: str) -> Dict[str, Any]:
    """
    Get configuration for a specific exchange and environment

    Args:
        exchange: Exchange name (e.g., "HYPERLIQUID")
        environment: Environment ("TESTNET" or "MAINNET")

    Returns:
        Dictionary containing exchange configuration

    Raises:
        ValueError: If exchange or environment is not found
    """
    for config in EXCHANGE_CONFIGS:
        if config["exchange"] == exchange and config["environment"] == environment:
            return config

    raise ValueError(f"No configuration found for {exchange} {environment}")


def format_symbol(symbol: str, exchange: str, market_type: str = "spot") -> str:
    """
    Format a symbol according to exchange requirements

    Args:
        symbol: Standard symbol format (e.g., "BTC/USDT", "BTC")
        exchange: Exchange name
        market_type: "spot" or "perp"

    Returns:
        Exchange-specific symbol format

    Examples:
        >>> format_symbol("BTC", "HYPERLIQUID", "spot")
        'BTC/USDC:USDC'
        >>> format_symbol("BTC", "HYPERLIQUID", "perp")
        'BTC-PERP'
    """
    if exchange == "HYPERLIQUID":
        # Extract base currency if symbol contains /
        base = symbol.split("/")[0] if "/" in symbol else symbol

        if market_type == "spot":
            return HYPERLIQUID_SYMBOL_FORMATS["spot"].format(base=base)
        elif market_type == "perp":
            return HYPERLIQUID_SYMBOL_FORMATS["perp"].format(base=base)

    # Default: return as-is
    return symbol


def parse_exchange_symbol(exchange_symbol: str, exchange: str) -> str:
    """
    Parse exchange-specific symbol back to standard format

    Args:
        exchange_symbol: Exchange-specific symbol (e.g., "BTC/USDC:USDC", "BTC-PERP")
        exchange: Exchange name

    Returns:
        Standard symbol format (e.g., "BTC/USDT", "BTC")

    Examples:
        >>> parse_exchange_symbol("BTC/USDC:USDC", "HYPERLIQUID")
        'BTC/USDT'
        >>> parse_exchange_symbol("BTC-PERP", "HYPERLIQUID")
        'BTC/USDT'
    """
    if exchange == "HYPERLIQUID":
        if "/USDC:USDC" in exchange_symbol:
            # Spot format: BTC/USDC:USDC → BTC/USDT
            base = exchange_symbol.split("/")[0]
            return f"{base}/USDT"
        elif "-PERP" in exchange_symbol:
            # Perp format: BTC-PERP → BTC/USDT
            base = exchange_symbol.replace("-PERP", "")
            return f"{base}/USDT"

    # Default: return as-is
    return exchange_symbol
