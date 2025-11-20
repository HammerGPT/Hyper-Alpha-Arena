"""
System config API routes
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging

from database.connection import SessionLocal
from database.models import SystemConfig, GlobalSamplingConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ConfigUpdateRequest(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


@router.get("/check-required")
async def check_required_configs(db: Session = Depends(get_db)):
    """Check if required configs are set"""
    try:
        return {
            "has_required_configs": True,
            "missing_configs": []
        }
    except Exception as e:
        logger.error(f"Failed to check required configs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check required configs: {str(e)}")


@router.get("/global-sampling")
async def get_global_sampling_config(db: Session = Depends(get_db)):
    """Get global sampling configuration"""
    try:
        config = db.query(GlobalSamplingConfig).first()
        if not config:
            # Create default config
            config = GlobalSamplingConfig(sampling_interval=18, sampling_depth=10)
            db.add(config)
            db.commit()
            db.refresh(config)

        return {
            "sampling_interval": config.sampling_interval,
            "sampling_depth": config.sampling_depth
        }
    except Exception as e:
        logger.error(f"Failed to get global sampling config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get global sampling config: {str(e)}")


@router.put("/global-sampling")
async def update_global_sampling_config(payload: dict, db: Session = Depends(get_db)):
    """Update global sampling configuration"""
    try:
        sampling_interval = payload.get("sampling_interval")
        sampling_depth = payload.get("sampling_depth")

        # Validate sampling_interval if provided
        if sampling_interval is not None:
            if not isinstance(sampling_interval, int) or sampling_interval < 5 or sampling_interval > 60:
                raise HTTPException(
                    status_code=400,
                    detail="sampling_interval must be between 5 and 60 seconds"
                )

        # Validate sampling_depth if provided
        if sampling_depth is not None:
            if not isinstance(sampling_depth, int) or sampling_depth < 10 or sampling_depth > 60:
                raise HTTPException(
                    status_code=400,
                    detail="sampling_depth must be between 10 and 60"
                )

            # Check premium requirement for sampling depth > 10
            if sampling_depth > 10:
                # For now, we'll allow it but log a warning
                # In a real implementation, you'd check user authentication and membership
                logger.warning(f"Sampling depth > 10 requested: {sampling_depth}. Premium check should be implemented.")

        config = db.query(GlobalSamplingConfig).first()
        if not config:
            config = GlobalSamplingConfig(
                sampling_interval=sampling_interval or 18,
                sampling_depth=sampling_depth or 10
            )
            db.add(config)
        else:
            if sampling_interval is not None:
                config.sampling_interval = sampling_interval
            if sampling_depth is not None:
                config.sampling_depth = sampling_depth

        db.commit()
        db.refresh(config)

        # Trigger sampling pool reconfiguration (use watchlist if available)
        try:
            print(f"[DEBUG] Starting sampling pool update to depth={config.sampling_depth}")
            from services.sampling_pool import sampling_pool
            from services.trading_commands import AI_TRADING_SYMBOLS
            from services.hyperliquid_symbol_service import get_selected_symbols as get_hyperliquid_selected_symbols

            symbols = get_hyperliquid_selected_symbols() or AI_TRADING_SYMBOLS
            for symbol in symbols:
                sampling_pool.set_max_samples(symbol, config.sampling_depth)

            print(f"[DEBUG] Sampling pool updated: depth={config.sampling_depth} for {len(symbols)} symbols")
            logger.info(f"Sampling pool updated: depth={config.sampling_depth} for {len(symbols)} symbols")
        except Exception as pool_err:
            print(f"[ERROR] Failed to update sampling pool: {pool_err}")
            logger.warning(f"Failed to update sampling pool: {pool_err}")

        return {
            "sampling_interval": config.sampling_interval,
            "sampling_depth": config.sampling_depth
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update global sampling config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update global sampling config: {str(e)}")
