#!/usr/bin/env python3
"""
Verification script to simulate what the frontend sees
This mimics the WebSocket snapshot data that the frontend receives
"""

import json
from database.connection import SessionLocal
from database.models import Trade, User, Position, Order
from services.asset_calculator import calc_positions_value

def simulate_snapshot_for_user(username: str):
    """Simulate the snapshot data sent to frontend for a specific user"""
    db = SessionLocal()
    try:
        # Get user
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User '{username}' not found")
            return
        
        # Get trades (same query as WebSocket)
        trades = (
            db.query(Trade)
            .filter(Trade.user_id == user.id)
            .order_by(Trade.trade_time.desc())
            .limit(200)
            .all()
        )
        
        # Get positions
        positions = db.query(Position).filter(Position.user_id == user.id).all()
        
        # Get orders
        orders = db.query(Order).filter(Order.user_id == user.id).all()
        
        # Calculate values
        positions_value = calc_positions_value(db, user.id)
        total_assets = positions_value + float(user.current_cash)
        
        print(f"\n{'='*60}")
        print(f"📊 SNAPSHOT DATA FOR USER: {username} (id={user.id})")
        print(f"{'='*60}")
        
        print(f"\n💰 Account Overview:")
        print(f"  Initial Capital: ${user.initial_capital:,.2f}")
        print(f"  Current Cash:    ${user.current_cash:,.2f}")
        print(f"  Frozen Cash:     ${user.frozen_cash:,.2f}")
        print(f"  Positions Value: ${positions_value:,.2f}")
        print(f"  Total Assets:    ${total_assets:,.2f}")
        print(f"  P&L:             ${total_assets - float(user.initial_capital):,.2f}")
        
        print(f"\n📈 Positions ({len(positions)}):")
        if positions:
            for p in positions:
                print(f"  • {p.symbol}.{p.market}: {p.quantity} @ ${p.avg_cost:.4f} avg cost")
        else:
            print("  No positions")
        
        print(f"\n📋 Orders ({len(orders)}):")
        if orders:
            for o in orders:
                print(f"  • {o.order_no}: {o.side} {o.quantity} {o.symbol} @ {o.price or 'MARKET'} - {o.status}")
        else:
            print("  No orders")
        
        print(f"\n💸 Trades ({len(trades)}):")
        if trades:
            print(f"  Showing latest {min(10, len(trades))} of {len(trades)} total trades:")
            for i, t in enumerate(trades[:10], 1):
                print(f"  {i:2d}. {t.trade_time} | {t.side:4s} {t.quantity:>8} {t.symbol:5s} @ ${t.price:>10.4f} | Fee: ${t.commission:.2f}")
        else:
            print("  ❌ NO TRADES FOUND - This is the issue!")
        
        # Create the JSON structure that would be sent via WebSocket
        snapshot_data = {
            "type": "snapshot",
            "overview": {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "initial_capital": float(user.initial_capital),
                    "current_cash": float(user.current_cash),
                    "frozen_cash": float(user.frozen_cash),
                },
                "total_assets": total_assets,
                "positions_value": positions_value,
            },
            "positions": [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "name": p.name,
                    "market": p.market,
                    "quantity": p.quantity,
                    "available_quantity": p.available_quantity,
                    "avg_cost": float(p.avg_cost),
                }
                for p in positions
            ],
            "orders": [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "symbol": o.symbol,
                    "side": o.side,
                    "status": o.status,
                }
                for o in orders
            ],
            "trades": [
                {
                    "id": t.id,
                    "order_id": t.order_id,
                    "symbol": t.symbol,
                    "name": t.name,
                    "market": t.market,
                    "side": t.side,
                    "price": float(t.price),
                    "quantity": t.quantity,
                    "commission": float(t.commission),
                    "trade_time": str(t.trade_time),
                }
                for t in trades
            ],
        }
        
        print(f"\n📤 WebSocket Snapshot Summary:")
        print(f"  • Trades in payload: {len(snapshot_data['trades'])}")
        print(f"  • Positions in payload: {len(snapshot_data['positions'])}")
        print(f"  • Orders in payload: {len(snapshot_data['orders'])}")
        
        if len(snapshot_data['trades']) > 0:
            print(f"\n✅ SUCCESS: Trades will be visible in the frontend!")
        else:
            print(f"\n⚠️  WARNING: No trades in snapshot - frontend will show empty trade list")
        
        return snapshot_data
        
    finally:
        db.close()


def main():
    """Test all users"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        print("="*60)
        print("🔍 VERIFYING TRADES DISPLAY FOR ALL USERS")
        print("="*60)
        
        if not users:
            print("\n❌ No users found in database")
            return
        
        for user in users:
            simulate_snapshot_for_user(user.username)
        
        print("\n" + "="*60)
        print("📊 OVERALL SUMMARY")
        print("="*60)
        total_trades = db.query(Trade).count()
        print(f"Total trades in database: {total_trades}")
        
        if total_trades > 0:
            print("\n✅ Trades exist in database and should be visible in frontend")
            print("   Make sure the backend server is running with the updated main.py")
        else:
            print("\n⚠️  No trades in database")
            print("   1. Start the backend server to enable auto-trading")
            print("   2. Wait ~5 seconds for auto-trader to create trades")
            print("   3. Or run: python test_auto_trader_live.py")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
