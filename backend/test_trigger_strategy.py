#!/usr/bin/env python3
"""
Manually trigger strategy check to see what happens
"""
from datetime import datetime, timezone
from services.trading_strategy import hyper_strategy_manager

print("=" * 80)
print("Manual Strategy Trigger Test")
print("=" * 80)

print(f"\nManager state:")
print(f"  running: {hyper_strategy_manager.running}")
print(f"  strategies: {len(hyper_strategy_manager.strategies)}")

if len(hyper_strategy_manager.strategies) == 0:
    print("\n✗ No strategies loaded!")
else:
    print("\nTrigger a test price update...")
    symbol = "BTC"
    price = 100000.0
    event_time = datetime.now(timezone.utc)

    print(f"Calling handle_price_update({symbol}, {price}, {event_time})")
    hyper_strategy_manager.handle_price_update(symbol, price, event_time)
    print("handle_price_update returned")

print("\n" + "=" * 80)
