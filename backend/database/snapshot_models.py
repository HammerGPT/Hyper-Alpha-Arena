"""
Snapshot database models - separate from main database
"""
from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, Text
from sqlalchemy.sql import func
from database.snapshot_connection import SnapshotBase


class HyperliquidAccountSnapshot(SnapshotBase):
    """Store Hyperliquid account state snapshots for audit and analysis"""
    __tablename__ = "hyperliquid_account_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False, index=True)
    environment = Column(String(20), nullable=False)  # "testnet" | "mainnet"

    # Account state data
    total_equity = Column(DECIMAL(18, 6), nullable=False)
    available_balance = Column(DECIMAL(18, 6), nullable=False)
    used_margin = Column(DECIMAL(18, 6), nullable=False)
    maintenance_margin = Column(DECIMAL(18, 6), nullable=True, default=0)

    # Metadata
    trigger_event = Column(String(50), nullable=False, default="scheduled")  # "scheduled", "manual", "trade"
    snapshot_data = Column(Text, nullable=True)  # JSON data for additional info
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())


class HyperliquidTrade(SnapshotBase):
    """Store Hyperliquid trade records with environment separation"""
    __tablename__ = "hyperliquid_trades"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False, index=True)
    environment = Column(String(20), nullable=False)  # "testnet" | "mainnet"

    # Trade data
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "buy" | "sell"
    quantity = Column(DECIMAL(18, 8), nullable=False)
    price = Column(DECIMAL(18, 6), nullable=False)
    leverage = Column(Integer, nullable=False, default=1)

    # Order info
    order_id = Column(String(100), nullable=True)  # Hyperliquid order ID
    order_status = Column(String(20), nullable=False)  # "filled" | "resting" | "error"

    # Financial data
    trade_value = Column(DECIMAL(18, 6), nullable=False)
    fee = Column(DECIMAL(18, 6), nullable=True, default=0)

    # Metadata
    trade_time = Column(TIMESTAMP, server_default=func.current_timestamp())
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())