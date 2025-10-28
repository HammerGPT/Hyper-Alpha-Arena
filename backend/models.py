from __future__ import annotations

from typing import Dict, Optional, List, Callable, Any
import pandas as pd
from dataclasses import dataclass


@dataclass
class Factor:
    """Factor definition for ranking calculations"""
    id: str
    name: str
    description: str
    columns: List[Dict[str, Any]]
    compute: Callable[[Dict[str, pd.DataFrame], Optional[pd.DataFrame]], pd.DataFrame]