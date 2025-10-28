from __future__ import annotations

from typing import Dict, Optional, List
import pandas as pd
import numpy as np

from models import Factor



def calculate_momentum_simple(df: pd.DataFrame) -> float:
    """Calculate (later-period low - earlier-period low) / longest candle"""
    if len(df) < 2:
        return 0.0
    
    # Convert date column to datetime for proper sorting if needed
    df_copy = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_copy['Date']):
        df_copy['Date'] = pd.to_datetime(df_copy['Date'])
    
    # Sort by date (oldest first)
    df_sorted = df_copy.sort_values("Date", ascending=True)
    df_sorted = df_sorted.reset_index(drop=True)
    
    # Calculate the necessary values
    # Minimum price in first half of period
    half_idx = len(df_sorted) // 2
    first_half_low = df_sorted.iloc[:half_idx]["Low"].min()
    
    # Minimum price in second half of period
    second_half_low = df_sorted.iloc[half_idx:]["Low"].min()
    
    # Maximum daily body length (absolute |close - open|) in entire period
    max_daily_change = (df_sorted["Close"] - df_sorted["Open"]).abs().max()
    
    # Check for invalid data
    if pd.isna(first_half_low) or pd.isna(second_half_low) or pd.isna(max_daily_change):
        return 0.0
    
    first_half_low = float(first_half_low)
    second_half_low = float(second_half_low)
    max_daily_change = float(max_daily_change)
    
    if max_daily_change == 0:
        return 0.0
    
    return (second_half_low - first_half_low) / max_daily_change


def compute_momentum(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Calculate momentum factor using formula: (later-period low - earlier-period low) / longest candle
    
    Args:
        history: Historical price data
        top_spot: Optional spot data (unused)
    """
    rows: List[dict] = []
    
    for code, df in history.items():
        if df is None or df.empty or len(df) < 2:
            continue
        
        momentum = calculate_momentum_simple(df)
        score = (np.tanh(momentum) + 1) / 2

        rows.append({
            "Symbol": code, 
            "Momentum": momentum,
            "Momentum Score": score
        })
    
    # Sort by momentum factor from high to low
    df_result = pd.DataFrame(rows)
    if not df_result.empty:
        df_result = df_result.sort_values("Momentum", ascending=False)
    
    return df_result


MOMENTUM_FACTOR = Factor(
    id="momentum",
    name="Momentum",
    description="Momentum: (later-period low - earlier-period low) / longest candle, sorted descending",
    columns=[
        {"key": "Momentum", "label": "Momentum", "type": "number", "sortable": True},
        {"key": "Momentum Score", "label": "Momentum Score", "type": "score", "sortable": True},
    ],
    compute=lambda history, top_spot=None: compute_momentum(history, top_spot),
)

MODULE_FACTORS = [MOMENTUM_FACTOR]
