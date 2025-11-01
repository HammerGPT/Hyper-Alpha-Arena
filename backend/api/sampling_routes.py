"""Sampling pool API routes"""

from fastapi import APIRouter
from typing import Dict, Any
from services.sampling_pool import sampling_pool

router = APIRouter(prefix="/api/sampling", tags=["sampling"])


@router.get("/pool-status")
async def get_sampling_pool_status() -> Dict[str, Any]:
    """Get current sampling pool status with detailed sample data"""
    return sampling_pool.get_pool_status()


@router.get("/pool-details")
async def get_sampling_pool_details() -> Dict[str, Any]:
    """Get detailed sampling pool data including all samples"""
    details = {}
    for symbol, pool in sampling_pool.pools.items():
        if pool:
            # Sort samples from oldest to newest (chronological order)
            sorted_samples = sorted(pool, key=lambda x: x['timestamp'])
            details[symbol] = {
                'samples': [
                    {
                        'price': sample['price'],
                        'timestamp': sample['timestamp'],
                        'datetime': sample['datetime'].isoformat()
                    }
                    for sample in sorted_samples
                ],
                'sample_count': len(sorted_samples),
                'price_change_percent': sampling_pool.get_price_change_percent(symbol)
            }
    return details