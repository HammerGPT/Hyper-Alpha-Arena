#!/usr/bin/env python3
"""
Manually start the strategy manager and verify it works
"""

from services.trading_strategy import hyper_strategy_manager

print("=" * 80)
print("Manually Starting StrategyManager")
print("=" * 80)

print("\nBefore start():")
print(f"  running: {hyper_strategy_manager.running}")
print(f"  strategies: {len(hyper_strategy_manager.strategies)}")

print("\nCalling start()...")
hyper_strategy_manager.start()

print("\nAfter start():")
print(f"  running: {hyper_strategy_manager.running}")
print(f"  strategies: {len(hyper_strategy_manager.strategies)}")

if hyper_strategy_manager.running and len(hyper_strategy_manager.strategies) > 0:
    print("\n✓ StrategyManager started successfully!")
    print("\nLoaded strategies:")
    for account_id, state in hyper_strategy_manager.strategies.items():
        print(f"  Account {account_id}: enabled={state.enabled}, threshold={state.price_threshold}%")
else:
    print("\n✗ StrategyManager failed to start properly!")
    if not hyper_strategy_manager.running:
        print("  - running is still False")
    if len(hyper_strategy_manager.strategies) == 0:
        print("  - no strategies loaded")

print("\n" + "=" * 80)
