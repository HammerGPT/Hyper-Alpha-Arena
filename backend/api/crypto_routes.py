"""
Crypto-specific API routes
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from services.market_data import get_all_symbols, get_last_price, get_market_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crypto", tags=["crypto"])


@router.get("/symbols")
async def get_crypto_symbols() -> List[str]:
    """Get all available crypto trading pairs"""
    try:
        symbols = get_all_symbols()
        return symbols
    except Exception as e:
        logger.error(f"Error getting crypto symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price/{symbol}")
async def get_crypto_price(symbol: str) -> Dict[str, Any]:
    """Get current price for a crypto symbol"""
    try:
        price = get_last_price(symbol, "CRYPTO")
        return {
            "symbol": symbol,
            "price": price,
            "market": "CRYPTO"
        }
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{symbol}")
async def get_crypto_market_status(symbol: str) -> Dict[str, Any]:
    """Get market status for a crypto symbol"""
    try:
        status = get_market_status(symbol, "CRYPTO")
        return status
    except Exception as e:
        logger.error(f"Error getting market status for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/popular")
async def get_popular_cryptos() -> List[Dict[str, Any]]:
    """Get popular crypto trading pairs with current prices"""
    popular_symbols = ["BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"]
    
    results = []
    for symbol in popular_symbols:
        try:
            price = get_last_price(symbol, "CRYPTO")
            results.append({
                "symbol": symbol,
                "name": symbol.split("/")[0],  # Extract base currency
                "price": price,
                "market": "CRYPTO"
            })
        except Exception as e:
            logger.warning(f"Could not get price for {symbol}: {e}")
            continue
    
    return results