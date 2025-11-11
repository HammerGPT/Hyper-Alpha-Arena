#!/usr/bin/env python3
"""
Check the actual state of the running StrategyManager
"""

from services.trading_strategy import hyper_strategy_manager

print("=" * 80)
print("StrategyManager State Check")
print("=" * 80)

print(f"\nManager running: {hyper_strategy_manager.running}")
print(f"Number of strategies loaded: {len(hyper_strategy_manager.strategies)}")

if len(hyper_strategy_manager.strategies) == 0:
    print("\n⚠️  WARNING: No strategies loaded in manager!")
    print("   This explains why no AI trading is happening.")
else:
    print("\nLoaded strategies:")
    for account_id, state in hyper_strategy_manager.strategies.items():
        print(f"  Account {account_id}:")
        print(f"    enabled: {state.enabled}")
        print(f"    price_threshold: {state.price_threshold}%")
        print(f"    trigger_interval: {state.trigger_interval}s")
        print(f"    last_trigger_at: {state.last_trigger_at}")
        print(f"    running: {state.running}")

print("\n" + "=" * 80)
