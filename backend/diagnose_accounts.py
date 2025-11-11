#!/usr/bin/env python3
"""
Diagnose AI Trader account configuration issues
检查AI Trader账户配置问题的诊断脚本
"""
import sys
from database.connection import SessionLocal
from database.models import Account, AccountStrategyConfig, SystemConfig

def diagnose():
    db = SessionLocal()
    try:
        print("=" * 80)
        print("AI Trader Account Diagnosis / AI Trader账户诊断")
        print("=" * 80)
        print()

        # Check AI accounts
        accounts = db.query(Account).filter(Account.account_type == "AI").all()

        if not accounts:
            print("❌ No AI accounts found / 没有找到AI账户")
            return

        print(f"✓ Found {len(accounts)} AI account(s) / 找到{len(accounts)}个AI账户")
        print()

        issues_found = []

        for account in accounts:
            print(f"Account #{account.id}: {account.name}")
            print("-" * 60)

            # Check basic fields
            is_active = account.is_active == "true"
            auto_trading = account.auto_trading_enabled == "true"
            environment = account.hyperliquid_environment
            hyperliquid_enabled = account.hyperliquid_enabled == "true"

            print(f"  is_active: {account.is_active} {'✓' if is_active else '❌'}")
            print(f"  auto_trading_enabled: {account.auto_trading_enabled} {'✓' if auto_trading else '❌'}")
            print(f"  hyperliquid_enabled: {account.hyperliquid_enabled} {'ℹ️  (legacy field)'}")
            print(f"  hyperliquid_environment: {environment or 'NULL'} {'✓' if environment else '❌'}")

            if not is_active:
                issues_found.append(f"Account {account.id} ({account.name}): is_active != 'true'")

            if not auto_trading:
                issues_found.append(f"Account {account.id} ({account.name}): auto_trading_enabled != 'true'")

            if not environment:
                issues_found.append(f"Account {account.id} ({account.name}): hyperliquid_environment is NULL ⚠️  CRITICAL")

            # Check private key
            if environment:
                if environment == "testnet":
                    has_key = bool(account.hyperliquid_testnet_private_key)
                    print(f"  testnet_private_key: {'configured ✓' if has_key else 'NOT configured ❌'}")
                    if not has_key:
                        issues_found.append(f"Account {account.id} ({account.name}): No testnet private key")
                else:
                    has_key = bool(account.hyperliquid_mainnet_private_key)
                    print(f"  mainnet_private_key: {'configured ✓' if has_key else 'NOT configured ❌'}")
                    if not has_key:
                        issues_found.append(f"Account {account.id} ({account.name}): No mainnet private key")

            # Check strategy config
            strategy = db.query(AccountStrategyConfig).filter(
                AccountStrategyConfig.account_id == account.id
            ).first()

            if strategy:
                strategy_enabled = strategy.enabled == "true"
                print(f"  strategy_configured: Yes ✓")
                print(f"  strategy_enabled: {strategy.enabled} {'✓' if strategy_enabled else '❌'}")
                print(f"  price_threshold: {strategy.price_threshold}%")
                print(f"  trigger_interval: {strategy.trigger_interval}s")

                if not strategy_enabled:
                    issues_found.append(f"Account {account.id} ({account.name}): Strategy enabled != 'true'")
            else:
                print(f"  strategy_configured: No ❌")
                issues_found.append(f"Account {account.id} ({account.name}): No strategy configuration")

            print()

        # Check Hyperliquid watchlist
        print("System Configuration / 系统配置")
        print("-" * 60)

        watchlist_config = db.query(SystemConfig).filter(
            SystemConfig.key == "hyperliquid_selected_symbols"
        ).first()

        if watchlist_config and watchlist_config.value:
            import json
            try:
                symbols = json.loads(watchlist_config.value)
                print(f"  hyperliquid_watchlist: {symbols} ✓")
            except:
                print(f"  hyperliquid_watchlist: Invalid JSON ❌")
                issues_found.append("Hyperliquid watchlist has invalid JSON")
        else:
            print(f"  hyperliquid_watchlist: NOT configured ❌")
            issues_found.append("Hyperliquid watchlist is empty ⚠️  CRITICAL")

        print()
        print("=" * 80)

        if issues_found:
            print(f"❌ Found {len(issues_found)} issue(s) / 发现{len(issues_found)}个问题:")
            print()
            for i, issue in enumerate(issues_found, 1):
                print(f"  {i}. {issue}")
            print()
            print("Fix suggestions / 修复建议:")
            print()

            if any("hyperliquid_environment is NULL" in issue for issue in issues_found):
                print("  🔧 Critical: Configure Hyperliquid environment for accounts")
                print("     Go to: AI Trader → Hyperliquid tab → Configure private key")
                print("     前往：AI Trader → Hyperliquid标签 → 配置私钥")
                print()

            if any("auto_trading_enabled" in issue for issue in issues_found):
                print("  🔧 Enable 'Start Trading' switch for accounts")
                print("     启用账户的 Start Trading 开关")
                print()

            if any("No strategy configuration" in issue or "Strategy enabled" in issue for issue in issues_found):
                print("  🔧 Configure and enable strategy for accounts")
                print("     Go to: AI Trader → Strategy tab → Configure and enable")
                print("     前往：AI Trader → Strategy标签 → 配置并启用")
                print()

            if any("Hyperliquid watchlist" in issue for issue in issues_found):
                print("  🔧 Critical: Configure Hyperliquid watchlist")
                print("     Go to: Settings → Hyperliquid → Select symbols to trade")
                print("     前往：Settings → Hyperliquid → 选择交易币种")
                print()

            return 1
        else:
            print("✓ All checks passed! / 所有检查通过!")
            print()
            print("If trading still doesn't work, check:")
            print("  1. Docker container logs: docker logs hyper-arena-app")
            print("  2. Price feed is working (check logs for 'Fetching price')")
            print("  3. Strategy trigger conditions are being met")
            return 0

    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(diagnose())
