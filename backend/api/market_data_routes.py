"""
Market data API routes
Provides RESTful API interfaces for crypto market data
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from services.market_data import get_last_price, get_kline_data, get_market_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market_data"])


class PriceResponse(BaseModel):
    """Price response model"""
    symbol: str
    market: str
    price: float
    timestamp: int


class KlineItem(BaseModel):
    """K-line data item model"""
    timestamp: int
    datetime: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    chg: Optional[float]
    percent: Optional[float]


class KlineResponse(BaseModel):
    """K-line data response model"""
    symbol: str
    market: str
    period: str
    count: int
    data: List[KlineItem]


class MarketStatusResponse(BaseModel):
    """Market status response model"""
    symbol: str
    market: str = None
    market_status: str
    timestamp: int
    current_time: str


@router.get("/price/{symbol}", response_model=PriceResponse)
async def get_crypto_price(symbol: str, market: str = "US"):
    """
    Get latest crypto price

    Args:
        symbol: crypto symbol, such as 'MSFT'
        market: Market symbol, default 'US'

    Returns:
        Response containing latest price
    """
    try:
        price = get_last_price(symbol, market)
        
        import time
        return PriceResponse(
            symbol=symbol,
            market=market,
            price=price,
            timestamp=int(time.time() * 1000)
        )
    except Exception as e:
        logger.error(f"Failed to get crypto price: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get crypto price: {str(e)}")


@router.get("/prices", response_model=List[PriceResponse])
async def get_multiple_prices(symbols: str, market: str = "hyperliquid"):
    """
    Get latest prices for multiple cryptos in batch

    Returns:
        Response list containing multiple crypto prices
    """
    try:
        symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
        
        if not symbol_list:
            raise HTTPException(status_code=400, detail="crypto symbol list cannot be empty")
        
        if len(symbol_list) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 crypto symbols supported")
        
        results = []
        import time
        current_timestamp = int(time.time() * 1000)
        
        for symbol in symbol_list:
            try:
                price = get_last_price(symbol, market)
                results.append(PriceResponse(
                    symbol=symbol,
                    market=market,
                    price=price,
                    timestamp=current_timestamp
                ))
            except Exception as e:
                logger.warning(f"Failed to get {symbol} price: {e}")
                # Continue processing other cryptos without interrupting the entire request
                
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch get crypto prices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to batch get crypto prices: {str(e)}")


@router.get("/kline/{symbol}", response_model=KlineResponse)
async def get_crypto_kline(
    symbol: str, 
    market: str = "US",
    period: str = "1m",
    count: int = 100
):
    """
    Get crypto K-line data

    Args:
        symbol: crypto symbol, such as 'MSFT'
        market: Market symbol, default 'US'
        period: Time period, supports '1m', '5m', '15m', '30m', '1h', '1d'
        count: Number of data points, default 100, max 500

    Returns:
        Response containing K-line data
    """
    try:
        # Parameter validation - Hyperliquid supported time periods
        valid_periods = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M']
        if period not in valid_periods:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported time period, supported periods: {', '.join(valid_periods)}"
            )
            
        if count <= 0 or count > 500:
            raise HTTPException(status_code=400, detail="Data count must be between 1-500")
        
        # Get K-line data
        kline_data = get_kline_data(symbol, market, period, count)
        
        # Convert data format
        kline_items = []
        for item in kline_data:
            # Handle datetime - may be string or datetime object
            dt_value = item.get('datetime')
            if dt_value is not None:
                dt_str = dt_value.isoformat() if hasattr(dt_value, 'isoformat') else str(dt_value)
            else:
                dt_str = None

            kline_items.append(KlineItem(
                timestamp=item.get('timestamp'),
                datetime=dt_str,
                open=item.get('open'),
                high=item.get('high'),
                low=item.get('low'),
                close=item.get('close'),
                volume=item.get('volume'),
                amount=item.get('amount'),
                chg=item.get('chg'),
                percent=item.get('percent')
            ))
        
        return KlineResponse(
            symbol=symbol,
            market=market,
            period=period,
            count=len(kline_items),
            data=kline_items
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get K-line data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get K-line data: {str(e)}")


@router.get("/status/{symbol}", response_model=MarketStatusResponse)
async def get_crypto_market_status(symbol: str, market: str = "US"):
    """
    Get crypto market status

    Args:
        symbol: crypto symbol, such as 'MSFT'
        market: Market symbol, default 'US'

    Returns:
        Response containing market status
    """
    try:
        status_data = get_market_status(symbol, market)
        
        return MarketStatusResponse(
            symbol=status_data.get('symbol', symbol),
            market=status_data.get('market', market),
            market_status=status_data.get('market_status', 'UNKNOWN'),
            timestamp=status_data.get('timestamp'),
            current_time=status_data.get('current_time', '')
        )
    except Exception as e:
        logger.error(f"Failed to get market status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get market status: {str(e)}")


@router.get("/health")
async def market_data_health():
    """
    Market data service health check

    Returns:
        Service status information
    """
    try:
        # Test getting a price to check if service is running normally
        test_price = get_last_price("MSFT", "US")
        
        import time
        return {
            "status": "healthy",
            "timestamp": int(time.time() * 1000),
            "test_price": {
                "symbol": "MSFT.US",
                "price": test_price
            },
            "message": "Market data service is running normally"
        }
    except Exception as e:
        logger.error(f"Market data service health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": int(time.time() * 1000),
            "error": str(e),
            "message": "Market data service abnormal"
        }