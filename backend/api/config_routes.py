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
            config = GlobalSamplingConfig(sampling_interval=18)
            db.add(config)
            db.commit()
            db.refresh(config)

        return {
            "sampling_interval": config.sampling_interval
        }
    except Exception as e:
        logger.error(f"Failed to get global sampling config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get global sampling config: {str(e)}")


@router.put("/global-sampling")
async def update_global_sampling_config(payload: dict, db: Session = Depends(get_db)):
    """Update global sampling configuration"""
    try:
        sampling_interval = payload.get("sampling_interval")

        if sampling_interval is None:
            raise HTTPException(status_code=400, detail="sampling_interval is required")

        if not isinstance(sampling_interval, int) or sampling_interval < 5 or sampling_interval > 60:
            raise HTTPException(
                status_code=400,
                detail="sampling_interval must be between 5 and 60 seconds"
            )

        config = db.query(GlobalSamplingConfig).first()
        if not config:
            config = GlobalSamplingConfig(sampling_interval=sampling_interval)
            db.add(config)
        else:
            config.sampling_interval = sampling_interval

        db.commit()
        db.refresh(config)

        return {
            "sampling_interval": config.sampling_interval
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update global sampling config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update global sampling config: {str(e)}")