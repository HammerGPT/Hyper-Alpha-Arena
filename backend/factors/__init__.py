from __future__ import annotations

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Dict, Optional
import pandas as pd

from models import Factor

__all__ = ["list_factors", "compute_all_factors", "compute_selected_factors"]


def _iter_factor_modules() -> List[str]:
    modules = []
    package = __name__  # 'factors'
    for _, name, ispkg in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if name in {"__init__"}:
            continue
        modules.append(f"{package}.{name}")
    return modules


def list_factors() -> List[Factor]:
    """Dynamically import all factor modules and collect Factor instances from MODULE_FACTORS list."""
    factors: List[Factor] = []
    for mod_name in _iter_factor_modules():
        try:
            mod = importlib.import_module(mod_name)
            module_factors = getattr(mod, "MODULE_FACTORS", None)
            if isinstance(module_factors, list):
                for f in module_factors:
                    if isinstance(f, Factor):
                        factors.append(f)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to import factor module {mod_name}: {e}")
    return factors


def compute_all_factors(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Compute all registered factor DataFrames and outer-join them by 'Symbol'."""
    dfs: List[pd.DataFrame] = []
    for factor in list_factors():
        try:
            df = factor.compute(history, top_spot)
            if df is not None and not df.empty:
                if 'Symbol' not in df.columns:
                    continue
                dfs.append(df)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Factor {factor.id} failed: {e}")
    if not dfs:
        return pd.DataFrame()
    result = dfs[0]
    for df in dfs[1:]:
        result = result.merge(df, on='Symbol', how='outer')
    return result


def compute_selected_factors(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None, selected_factor_ids: Optional[List[str]] = None) -> pd.DataFrame:
    """Compute only selected factor DataFrames and outer-join them by 'Symbol'."""
    if selected_factor_ids is None:
        return compute_all_factors(history, top_spot)
    
    dfs: List[pd.DataFrame] = []
    all_factors = list_factors()
    selected_factors = [f for f in all_factors if f.id in selected_factor_ids]
    
    for factor in selected_factors:
        try:
            df = factor.compute(history, top_spot)
            if df is not None and not df.empty:
                if 'Symbol' not in df.columns:
                    continue
                dfs.append(df)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Factor {factor.id} failed: {e}")
    
    if not dfs:
        return pd.DataFrame()
    
    result = dfs[0]
    for df in dfs[1:]:
        result = result.merge(df, on='Symbol', how='outer')
    return result
