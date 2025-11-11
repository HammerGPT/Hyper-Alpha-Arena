#!/usr/bin/env python3
"""
Test script to debug strategy loading issue
"""
import sys
import traceback
from datetime import datetime, timezone

from database.connection import SessionLocal
from database.models import Account, AccountStrategyConfig


def _as_aware(dt):
    """Ensure stored timestamps are timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def test_load_strategies():
    """Test loading strategies like HyperliquidStrategyManager does"""
    print("=" * 80)
    print("Testing Strategy Loading")
    print("=" * 80)

    db = SessionLocal()
    try:
        print("\n1. Querying database...")
        rows = (
            db.query(AccountStrategyConfig, Account)
            .join(Account, AccountStrategyConfig.account_id == Account.id)
            .all()
        )
        print(f"   Found {len(rows)} rows")

        print("\n2. Processing each strategy...")
        strategies = {}
        for i, (strategy, account) in enumerate(rows, 1):
            print(f"\n   Strategy #{i}:")
            print(f"     account_id: {strategy.account_id}")
            print(f"     account_name: {account.name}")
            print(f"     enabled: {strategy.enabled}")
            print(f"     price_threshold: {strategy.price_threshold}")
            print(f"     trigger_interval: {strategy.trigger_interval}")
            print(f"     last_trigger_at: {strategy.last_trigger_at} (type: {type(strategy.last_trigger_at)})")

            try:
                print(f"     Converting last_trigger_at...")
                aware_time = _as_aware(strategy.last_trigger_at)
                print(f"     ✓ Converted to: {aware_time}")

                strategies[strategy.account_id] = {
                    "account_id": strategy.account_id,
                    "price_threshold": strategy.price_threshold,
                    "trigger_interval": strategy.trigger_interval,
                    "enabled": strategy.enabled == "true",
                    "last_trigger_at": aware_time,
                }
                print(f"     ✓ Strategy added to dict")

            except Exception as e:
                print(f"     ✗ ERROR processing strategy: {e}")
                print(f"     Traceback:")
                traceback.print_exc()

        print(f"\n3. Final result:")
        print(f"   Loaded {len(strategies)} strategies successfully")

        if len(strategies) == 0:
            print("   ⚠️  NO STRATEGIES LOADED!")
            return False

        print("\n" + "=" * 80)
        print("✓ Test passed!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = test_load_strategies()
    sys.exit(0 if success else 1)
