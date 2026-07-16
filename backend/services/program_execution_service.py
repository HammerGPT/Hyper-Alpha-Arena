"""
Program Trader execution service.
Handles signal-triggered and scheduled execution of bound programs.

Architecture:
- Programs are bound to AI Traders via AccountProgramBinding
- Each binding has its own trigger configuration (signal pools, interval)
- Execution uses the AI Trader's wallet for trading
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is timezone-aware UTC.

    Database stores UTC time in 'timestamp without time zone' columns.
    The naive datetime from DB is already UTC, just missing the timezone marker.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

from sqlalchemy import func

from database.connection import SessionLocal
from database.models import (
    TradingProgram, AccountProgramBinding, ProgramExecutionLog,
    Account, HyperliquidWallet, BinanceWallet, AIDecisionLog,
    User, UserSubscription
)
from program_trader.executor import execute_strategy
from program_trader.models import MarketData, ActionType
from program_trader.data_provider import DataProvider
from config.settings import BINANCE_DAILY_QUOTA_LIMIT

logger = logging.getLogger(__name__)


class ProgramExecutionService:
    """Manages execution of bound programs when signals trigger."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._running_bindings: Dict[int, bool] = {}
        self._binding_locks: Dict[int, threading.Lock] = {}
        # Binding state cache for scheduled triggers (similar to AI Trader's strategies)
        self._binding_states: Dict[int, dict] = {}  # binding_id -> state dict
        self._last_cache_refresh: Optional[datetime] = None
        self._cache_refresh_interval = 60  # Refresh cache every 60 seconds
        self._daily_quota_limit = BINANCE_DAILY_QUOTA_LIMIT
        logger.info("[ProgramExecution] Service initialized")

    def _is_premium_user(self, db) -> bool:
        """Check if current logged-in user is a premium member"""
        try:
            subscription = db.query(UserSubscription).join(User).filter(
                User.username != 'default',
                UserSubscription.subscription_type == 'premium'
            ).first()
            return subscription is not None
        except Exception as e:
            logger.warning(f"Failed to check premium status: {e}")
            return False

    def _check_binance_daily_quota(self, db, account_id: int) -> Tuple[bool, Dict[str, int]]:
        """Check if Binance mainnet daily quota is exceeded."""
        if self._is_premium_user(db):
            return False, {"used": 0, "limit": self._daily_quota_limit, "remaining": self._daily_quota_limit}

        # Use UTC midnight for quota reset
        today_start_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        ai_count = db.query(func.count(AIDecisionLog.id)).filter(
            AIDecisionLog.account_id == account_id,
            AIDecisionLog.exchange == "binance",
            AIDecisionLog.hyperliquid_environment == "mainnet",
            AIDecisionLog.created_at >= today_start_utc,
            AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        ).scalar() or 0

        program_count = db.query(func.count(ProgramExecutionLog.id)).filter(
            ProgramExecutionLog.account_id == account_id,
            ProgramExecutionLog.exchange == "binance",
            ProgramExecutionLog.environment == "mainnet",
            ProgramExecutionLog.created_at >= today_start_utc,
            ProgramExecutionLog.decision_action.in_(["buy", "sell", "close"]),
        ).scalar() or 0

        used = ai_count + program_count
        remaining = max(0, self._daily_quota_limit - used)
        exceeded = used >= self._daily_quota_limit

        return exceeded, {"used": used, "limit": self._daily_quota_limit, "remaining": remaining}

    def on_signal_triggered(
        self,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
    ):
        """Called when a signal pool triggers - execute bound programs."""
        pool_id = pool.get("pool_id")
        pool_name = pool.get("pool_name", "Unknown")

        logger.info(f"[ProgramExecution] Signal triggered: {pool_name} (pool_id={pool_id}) on {symbol}")

        db = SessionLocal()
        try:
            # Find active bindings that include this pool_id
            all_bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.is_active == True,
                AccountProgramBinding.is_deleted != True
            ).all()

            # Filter bindings that have this pool_id in their signal_pool_ids
            bindings = []
            for binding in all_bindings:
                if binding.signal_pool_ids:
                    try:
                        pool_ids = json.loads(binding.signal_pool_ids)
                        if pool_id in pool_ids:
                            bindings.append(binding)
                    except:
                        pass

            if not bindings:
                logger.debug(f"[ProgramExecution] No bindings for pool_id={pool_id}")
                return

            logger.info(f"[ProgramExecution] Found {len(bindings)} bindings for pool_id={pool_id}")
            raw_trigger_type = pool.get("trigger_type", "signal")
            # Program Trader keeps a stable top-level trigger taxonomy: signal vs scheduled.
            # Wallet tracking is a signal-source subtype and should flow through wallet_event
            # / signal_source_type instead of becoming a third top-level trigger type.
            trigger_type = "signal" if raw_trigger_type == "wallet_signal" else raw_trigger_type
            for binding in bindings:
                self._execute_binding(
                    db,
                    binding,
                    symbol,
                    pool,
                    market_data_snapshot,
                    triggered_signals,
                    trigger_type=trigger_type,
                )

        except Exception as e:
            logger.error(f"[ProgramExecution] Error processing signal: {e}")
        finally:
            db.close()

    def on_price_update(self, symbol: str, price: float, event_time: datetime):
        """Called on price updates - check for scheduled triggers (like AI Trader)."""
        try:
            # Refresh binding cache periodically
            self._maybe_refresh_cache()

            # Check each binding for scheduled trigger
            for binding_id, state in list(self._binding_states.items()):
                if self._should_trigger_scheduled(binding_id, state, event_time):
                    # Scheduled triggers have no specific symbol (empty string)
                    self._execute_scheduled_trigger(binding_id, "", event_time)

        except Exception as e:
            logger.error(f"[ProgramExecution] Error in on_price_update: {e}")

    def _maybe_refresh_cache(self):
        """Refresh binding state cache if needed."""
        now = datetime.now(timezone.utc)
        if (self._last_cache_refresh is None or
            (now - self._last_cache_refresh).total_seconds() >= self._cache_refresh_interval):
            self._refresh_binding_cache()
            self._last_cache_refresh = now

    def _refresh_binding_cache(self):
        """Load active bindings with scheduled trigger enabled into cache."""
        db = SessionLocal()
        try:
            bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.is_active == True,
                AccountProgramBinding.scheduled_trigger_enabled == True,
                AccountProgramBinding.is_deleted != True
            ).all()

            for binding in bindings:
                self._binding_states[binding.id] = {
                    "binding_id": binding.id,
                    "account_id": binding.account_id,
                    "program_id": binding.program_id,
                    "trigger_interval": binding.trigger_interval,
                    "last_trigger_at": _as_utc(binding.last_trigger_at),
                    "signal_pool_ids": json.loads(binding.signal_pool_ids) if binding.signal_pool_ids else [],
                }

            # Remove bindings that are no longer active/enabled
            active_ids = {b.id for b in bindings}
            for bid in list(self._binding_states.keys()):
                if bid not in active_ids:
                    del self._binding_states[bid]

            logger.debug(f"[ProgramExecution] Refreshed cache: {len(self._binding_states)} scheduled bindings")
        except Exception as e:
            logger.error(f"[ProgramExecution] Error refreshing cache: {e}")
        finally:
            db.close()

    def _should_trigger_scheduled(self, binding_id: int, state: dict, event_time: datetime) -> bool:
        """Check if binding should trigger based on scheduled interval."""
        # Check if already running
        if self._running_bindings.get(binding_id, False):
            return False

        trigger_interval = state.get("trigger_interval", 300)
        last_trigger_at = state.get("last_trigger_at")

        now_ts = event_time.timestamp()
        last_ts = last_trigger_at.timestamp() if last_trigger_at else 0
        time_diff = now_ts - last_ts

        if time_diff >= trigger_interval:
            logger.info(
                f"[ProgramExecution] Scheduled trigger for binding {binding_id}: "
                f"interval={trigger_interval}s, elapsed={time_diff:.1f}s"
            )
            return True

        return False

    def _execute_scheduled_trigger(self, binding_id: int, symbol: str, event_time: datetime):
        """Execute a scheduled trigger for a binding."""
        db = SessionLocal()
        try:
            binding = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.id == binding_id,
                AccountProgramBinding.is_active == True,
                AccountProgramBinding.is_deleted != True
            ).first()

            if not binding:
                logger.warning(f"[ProgramExecution] Binding {binding_id} not found or inactive")
                return

            # Build minimal pool/trigger context for scheduled execution
            pool = {
                "pool_id": None,
                "pool_name": None,
            }
            market_data_snapshot = {}
            triggered_signals = []

            # Execute with trigger_type="scheduled"
            self._execute_binding(
                db, binding, symbol, pool, market_data_snapshot, triggered_signals,
                trigger_type="scheduled", event_time=event_time
            )

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing scheduled trigger: {e}")
        finally:
            db.close()

    def _execute_binding(
        self,
        db,
        binding: AccountProgramBinding,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
        trigger_type: str = "signal",
        event_time: Optional[datetime] = None,
    ):
        """Execute a single binding (program + account combination)."""
        binding_id = binding.id
        if event_time is None:
            event_time = datetime.now(timezone.utc)

        # Get or create lock for this binding
        if binding_id not in self._binding_locks:
            self._binding_locks[binding_id] = threading.Lock()

        lock = self._binding_locks[binding_id]

        # Check if already running
        if not lock.acquire(blocking=False):
            logger.warning(f"[ProgramExecution] Binding {binding_id} already running, skipping")
            return

        try:
            self._running_bindings[binding_id] = True

            # Update last_trigger_at immediately (like AI Trader does)
            # This resets the scheduled trigger timer for both signal and scheduled triggers
            binding.last_trigger_at = event_time
            db.commit()

            # Also update cache
            if binding_id in self._binding_states:
                self._binding_states[binding_id]["last_trigger_at"] = event_time

            # Load related objects
            program = binding.program
            account = binding.account

            if not program or not account:
                logger.error(f"[ProgramExecution] Binding {binding_id} missing program or account")
                return

            logger.info(f"[ProgramExecution] Executing: {program.name} via {account.name} (trigger: {trigger_type})")

            # Get exchange from binding (default to hyperliquid for backward compatibility)
            exchange = getattr(binding, 'exchange', None) or 'hyperliquid'

            # Get wallet address for this account based on exchange
            wallet_address = self._get_wallet_address(db, account, exchange)

            # Get trading environment and create trading client
            from services.hyperliquid_environment import get_global_trading_mode, get_hyperliquid_client, get_leverage_settings
            from paper_trading import get_execution_mode

            is_paper = get_execution_mode(db, account.id) == "paper"
            if is_paper:
                environment = "paper"
                from paper_trading.client import PaperTradingClient
                trading_client = PaperTradingClient(account.id, exchange)
                # Paper accounts have no row in HyperliquidWallet/BinanceWallet for the
                # global environment (_get_wallet_address above looked one up regardless
                # of paper status), so use the client's own paper wallet identifier --
                # matches the AI Trader pipeline's convention (trading_commands.py
                # wallet_address="paper-{id}"). Without this, Hyperliquid paper accounts
                # with no real wallet configured would be blocked later in
                # _handle_decision's "no wallet address" check.
                wallet_address = trading_client.wallet_address
                if exchange == "binance":
                    leverage_settings = self._get_binance_leverage_settings(db, account.id, "mainnet")
                else:
                    leverage_settings = get_leverage_settings(db, account.id, "mainnet")
            else:
                environment = get_global_trading_mode(db)
                trading_client = None

                if exchange == "binance":
                    # Use Binance trading client
                    if wallet_address:  # wallet_address here is actually API key presence indicator
                        try:
                            from services.binance_trading_client import BinanceTradingClient
                            from utils.encryption import decrypt_private_key

                            binance_wallet = db.query(BinanceWallet).filter(
                                BinanceWallet.account_id == account.id,
                                BinanceWallet.environment == (environment or "mainnet"),
                                BinanceWallet.is_active == "true"
                            ).first()

                            if binance_wallet:
                                api_key = decrypt_private_key(binance_wallet.api_key_encrypted)
                                secret_key = decrypt_private_key(binance_wallet.secret_key_encrypted)
                                trading_client = BinanceTradingClient(api_key, secret_key, environment or "mainnet")
                            else:
                                logger.warning(f"[ProgramExecution] No active Binance wallet found for account {account.id} on {environment}")
                        except Exception as e:
                            logger.warning(f"[ProgramExecution] Failed to create Binance trading client: {e}")
                    # Get leverage settings from BinanceWallet
                    leverage_settings = self._get_binance_leverage_settings(db, account.id, environment or "mainnet")
                else:
                    # Use Hyperliquid trading client (default)
                    if environment and wallet_address:
                        try:
                            trading_client = get_hyperliquid_client(db, account.id, override_environment=environment)
                        except Exception as e:
                            logger.warning(f"[ProgramExecution] Failed to create Hyperliquid trading client: {e}")
                    # Get leverage settings (same as AI Trader)
                    leverage_settings = get_leverage_settings(db, account.id, environment or "mainnet")

            max_leverage = leverage_settings["max_leverage"]
            default_leverage = leverage_settings["default_leverage"]

            # Build MarketData with trading client (enable query recording for analysis).
            # Paper mode always trades against mainnet market data, regardless of the
            # global testnet/mainnet toggle (matches trading_commands.py's paper branch).
            data_provider = DataProvider(
                db, account.id, "mainnet" if is_paper else (environment or "mainnet"), trading_client,
                record_queries=True, exchange=exchange
            )
            market_data = self._build_market_data(
                data_provider=data_provider,
                symbol=symbol,
                pool=pool,
                market_data_snapshot=market_data_snapshot,
                triggered_signals=triggered_signals,
                trigger_type=trigger_type,
                signal_source_type="wallet_tracking" if isinstance(pool.get("wallet_event"), dict) else None,
                environment=environment or "mainnet",
                max_leverage=max_leverage,
                default_leverage=default_leverage,
            )

            # Get params (binding override > program default)
            params = {}
            if program.params:
                try:
                    params = json.loads(program.params)
                except:
                    pass
            if binding.params_override:
                try:
                    override = json.loads(binding.params_override)
                    params.update(override)
                except:
                    pass

            # Execute strategy
            result = execute_strategy(program.code, market_data, params)

            # Determine if this is an actual trade (buy/sell/close) that needs quota check
            quota_exceeded = False
            quota_info = {}
            is_trade = False
            if result.success and result.decision:
                op = result.decision.operation.lower() if hasattr(result.decision, 'operation') else (result.decision.action.value if hasattr(result.decision, 'action') else "")
                is_trade = op in ["buy", "sell", "close"]

            # Check daily quota only for actual trades (buy/sell/close), not HOLD/errors
            if is_trade and exchange == "binance" and (environment or "mainnet") == "mainnet":
                binance_wallet = db.query(BinanceWallet).filter(
                    BinanceWallet.account_id == account.id,
                    BinanceWallet.environment == (environment or "mainnet"),
                    BinanceWallet.is_active == "true"
                ).first()
                if binance_wallet and binance_wallet.rebate_working is False:
                    quota_exceeded, quota_info = self._check_binance_daily_quota(db, account.id)
                    if quota_exceeded:
                        logger.warning(
                            f"[ProgramExecution] Binding {binding.id} ({program.name}) quota exceeded - "
                            f"Decision recorded but NOT executed ({quota_info['used']}/{quota_info['limit']})"
                        )
                        # Modify result to indicate quota exceeded
                        result.success = False
                        result.error = f"Daily quota exceeded ({quota_info['used']}/{quota_info['limit']})"

            # Log execution with full context for analysis
            log_id = self._log_execution(
                db, binding, symbol, pool, wallet_address, result, params,
                data_provider, market_data, environment or "mainnet", trigger_type, exchange
            )

            # If quota exceeded, don't proceed to handle decision (no trading)
            if quota_exceeded:
                return

            # Handle decision if successful
            if result.success and result.decision:
                order_result = self._handle_decision(
                    db, binding, result.decision, symbol, wallet_address,
                    exchange=exchange, trading_client=trading_client
                )
                # Update log with order result and create HyperliquidTrade if filled
                # Skip for HOLD decisions - they don't execute orders
                op = result.decision.operation.lower() if hasattr(result.decision, 'operation') else result.decision.action.value
                if log_id and op != "hold":
                    self._update_log_with_order(
                        db, log_id, order_result, binding, result.decision,
                        wallet_address, environment or "mainnet", exchange=exchange
                    )

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing binding {binding_id}: {e}")
        finally:
            self._running_bindings[binding_id] = False
            lock.release()

    def _get_wallet_address(self, db, account: Account, exchange: str = "hyperliquid") -> Optional[str]:
        """Get the active wallet address for an account based on exchange."""
        from services.hyperliquid_environment import get_global_trading_mode

        environment = get_global_trading_mode(db)
        if not environment:
            return None

        if exchange == "binance":
            # For Binance, check if API key exists (return a truthy value if configured)
            wallet = db.query(BinanceWallet).filter(
                BinanceWallet.account_id == account.id,
                BinanceWallet.environment == environment,
                BinanceWallet.is_active == "true"
            ).first()
            # Return a placeholder to indicate wallet is configured
            return "binance_configured" if wallet and wallet.api_key_encrypted else None
        else:
            # Hyperliquid wallet
            wallet = db.query(HyperliquidWallet).filter(
                HyperliquidWallet.account_id == account.id,
                HyperliquidWallet.environment == environment,
                HyperliquidWallet.is_active == "true"
            ).first()
            return wallet.wallet_address if wallet else None

    def _get_binance_leverage_settings(self, db, account_id: int, environment: str) -> dict:
        """Get leverage settings from BinanceWallet."""
        wallet = db.query(BinanceWallet).filter(
            BinanceWallet.account_id == account_id,
            BinanceWallet.environment == environment,
            BinanceWallet.is_active == "true"
        ).first()
        if wallet:
            return {
                "max_leverage": wallet.max_leverage or 10,
                "default_leverage": wallet.default_leverage or 3
            }
        return {"max_leverage": 10, "default_leverage": 3}

    def _build_market_data(
        self,
        data_provider: DataProvider,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
        trigger_type: str = "signal",
        signal_source_type: Optional[str] = None,
        environment: str = "mainnet",
        max_leverage: int = 10,
        default_leverage: int = 3,
    ) -> MarketData:
        """Build MarketData object for strategy execution.

        Populates all fields to match AI Trader's prompt context variables,
        ensuring Programs have access to the same information.
        """
        from program_trader.models import RegimeInfo

        account_info = data_provider.get_account_info()

        # Extract trigger context from pool (matches AI Trader's {trigger_context})
        signal_pool_name = pool.get("pool_name", "") or ""
        pool_logic = pool.get("logic", "OR") or "OR"
        wallet_event = pool.get("wallet_event") if signal_source_type == "wallet_tracking" else None

        # Build trigger market regime snapshot if this is a signal trigger
        trigger_market_regime = None
        # Wallet-origin signals are still signals, but they do not have local market
        # indicator context. Only market-native signals should populate regime snapshots.
        if trigger_type == "signal" and signal_source_type != "wallet_tracking" and symbol:
            # Get market regime at trigger time (same timeframe as first signal if available)
            timeframe = "5m"  # Default
            if triggered_signals:
                timeframe = triggered_signals[0].get("time_window", "5m")
            regime_info = data_provider.get_regime(symbol, timeframe)
            trigger_market_regime = regime_info

        return MarketData(
            # Account info
            available_balance=account_info.get("available_balance", 0.0),
            total_equity=account_info.get("total_equity", 0.0),
            used_margin=account_info.get("used_margin", 0.0),
            margin_usage_percent=account_info.get("margin_usage_percent", 0.0),
            maintenance_margin=account_info.get("maintenance_margin", 0.0),
            # Positions and trades
            positions=data_provider.get_positions(),
            recent_trades=data_provider.get_recent_trades(),
            open_orders=data_provider.get_open_orders(),
            # Trigger info (basic)
            trigger_symbol=symbol,
            trigger_type=trigger_type,
            # Trigger context (detailed)
            signal_pool_name=signal_pool_name,
            pool_logic=pool_logic,
            triggered_signals=triggered_signals or [],
            signal_source_type=signal_source_type,
            wallet_event=wallet_event if isinstance(wallet_event, dict) else None,
            # Trigger market regime snapshot
            trigger_market_regime=trigger_market_regime,
            # Environment info
            environment=environment,
            max_leverage=max_leverage,
            default_leverage=default_leverage,
            # Data provider
            _data_provider=data_provider,
        )

    def _log_execution(
        self,
        db,
        binding: AccountProgramBinding,
        symbol: str,
        pool: dict,
        wallet_address: Optional[str],
        result,
        params: dict,
        data_provider: Optional[DataProvider],
        market_data,
        environment: str,
        trigger_type: str = "signal",
        exchange: str = "hyperliquid"
    ):
        """Log program execution to database with full context for analysis."""
        try:
            decision = result.decision
            # Handle both old (action) and new (operation) Decision formats
            action_value = None
            size_value = None
            if decision:
                if hasattr(decision, 'operation'):
                    action_value = decision.operation
                    size_value = decision.target_portion_of_balance
                elif hasattr(decision, 'action'):
                    action_value = decision.action.value if hasattr(decision.action, 'value') else decision.action
                    size_value = getattr(decision, 'size_usd', None)

            # Build comprehensive market_context for analysis/backtest
            positions_snapshot = {}
            if market_data and market_data.positions:
                for sym, pos in market_data.positions.items():
                    positions_snapshot[sym] = {
                        "side": pos.side,
                        "size": pos.size,
                        "entry_price": pos.entry_price,
                        "unrealized_pnl": getattr(pos, 'unrealized_pnl', 0),
                        "leverage": getattr(pos, 'leverage', None),
                        "opened_at": getattr(pos, 'opened_at', None),
                        "opened_at_str": getattr(pos, 'opened_at_str', None),
                        "holding_duration_seconds": getattr(pos, 'holding_duration_seconds', None),
                        "holding_duration_str": getattr(pos, 'holding_duration_str', None),
                    }

            market_context = {
                "input_data": {
                    "environment": environment,
                    "trigger_symbol": symbol,
                    "trigger_type": trigger_type,
                    "signal_pool_id": pool.get("pool_id"),
                    "signal_pool_name": pool.get("pool_name"),
                    "pool_logic": market_data.pool_logic if market_data else "OR",
                    "triggered_signals": market_data.triggered_signals if market_data else [],
                    "signal_source_type": market_data.signal_source_type if market_data else None,
                    "wallet_event": market_data.wallet_event if market_data else None,
                    "trigger_market_regime": {
                        "regime": market_data.trigger_market_regime.regime,
                        "conf": market_data.trigger_market_regime.conf,
                        "direction": market_data.trigger_market_regime.direction,
                        "indicators": market_data.trigger_market_regime.indicators,
                    } if market_data and market_data.trigger_market_regime else None,
                    "max_leverage": market_data.max_leverage if market_data else 10,
                    "default_leverage": market_data.default_leverage if market_data else 3,
                    "available_balance": market_data.available_balance if market_data else 0,
                    "total_equity": market_data.total_equity if market_data else 0,
                    "margin_usage_percent": market_data.margin_usage_percent if market_data else 0,
                    "positions": positions_snapshot,
                    "positions_count": len(positions_snapshot),
                    "open_orders": [
                        {
                            "order_id": o.order_id,
                            "symbol": o.symbol,
                            "side": o.side,
                            "direction": o.direction,
                            "order_type": o.order_type,
                            "size": o.size,
                            "price": o.price,
                            "trigger_price": o.trigger_price,
                            "reduce_only": o.reduce_only,
                            "timestamp": o.timestamp,
                        }
                        for o in (market_data.open_orders if market_data else [])
                    ],
                    "open_orders_count": len(market_data.open_orders) if market_data else 0,
                },
                "data_queries": data_provider.get_query_log() if data_provider else [],
                "execution_logs": getattr(result, 'logs', []) or [],
            }

            log = ProgramExecutionLog(
                binding_id=binding.id,
                account_id=binding.account_id,
                program_id=binding.program_id,
                program_name=binding.program.name if binding.program else None,
                trigger_type=trigger_type,
                trigger_symbol=symbol,
                signal_pool_id=pool.get("pool_id"),
                wallet_address=wallet_address,
                environment=environment,  # Track execution environment for attribution
                exchange=exchange,  # Track exchange for attribution (NULL treated as "hyperliquid")
                success=result.success,
                error_message=result.error,
                execution_time_ms=result.execution_time_ms,
                decision_action=action_value,
                decision_symbol=decision.symbol if decision else None,
                decision_size_usd=size_value,
                decision_leverage=decision.leverage if decision else None,
                decision_reason=decision.reason if decision else None,
                decision_json=json.dumps(decision.to_dict()) if decision else None,
                params_snapshot=json.dumps(params) if params else None,
                market_context=json.dumps(market_context),
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            # Bot push notification for Program Trader decisions
            if result.success and decision and decision.operation.lower() != "hold":
                try:
                    from api.bot_routes import get_notification_config_dict
                    from services.bot_event_service import enqueue_system_event, push_event_to_all_channels
                    import asyncio
                    notif_config = get_notification_config_dict(db)
                    if notif_config.get("program_trader", True):
                        event_data = {
                            "program_name": binding.program.name if binding.program else "Unknown",
                            "operation": decision.operation.upper(),
                            "symbol": decision.symbol or symbol,
                            "size_usd": f"{decision.target_portion_of_balance*100:.0f}%" if decision.target_portion_of_balance else "N/A",
                            "leverage": f"{decision.leverage}x" if decision.leverage else "N/A",
                            "reason": decision.reason[:100] if decision.reason else "",
                        }
                        results = enqueue_system_event(db, "program_decision", event_data)
                        if results:
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(push_event_to_all_channels(db, results))
                            except RuntimeError:
                                asyncio.run(push_event_to_all_channels(db, results))
                except Exception as notif_err:
                    logger.warning(f"[ProgramExecution] Failed to send bot notification: {notif_err}")

            return log.id
        except Exception as e:
            logger.error(f"[ProgramExecution] Failed to log execution: {e}")
            return None

    def _update_log_with_order(
        self,
        db,
        log_id: int,
        order_result: Optional[dict],
        binding: AccountProgramBinding,
        decision,
        wallet_address: str,
        environment: str,
        exchange: str = "hyperliquid"
    ):
        """Update execution log with order IDs and create HyperliquidTrade if filled."""
        try:
            log = db.query(ProgramExecutionLog).filter(ProgramExecutionLog.id == log_id).first()
            if not log:
                return

            # If order failed (order_result is None), mark the log as failed
            if order_result is None:
                log.success = False
                log.error_message = (log.error_message or "") + " [Order execution failed]"
                db.commit()
                logger.info(f"[ProgramExecution] Updated log {log_id} with order failure status")
                return

            # Handle quota exceeded - decision was recorded but not executed
            if isinstance(order_result, dict) and order_result.get('quota_exceeded'):
                quota_info = order_result.get('quota_info', {})
                log.success = False  # Mark as not executed due to quota
                log.error_message = f"Executed: NO - Daily quota exceeded ({quota_info.get('used', 0)}/{quota_info.get('limit', 20)})"
                db.commit()
                logger.info(f"[ProgramExecution] Updated log {log_id} with quota exceeded status")
                return

            # Extract order IDs from result
            order_id = order_result.get('order_id')
            tp_order_id = order_result.get('tp_order_id')
            sl_order_id = order_result.get('sl_order_id')

            # Update log with order IDs
            if order_id:
                log.hyperliquid_order_id = str(order_id)
            if tp_order_id:
                log.tp_order_id = str(tp_order_id)
            if sl_order_id:
                log.sl_order_id = str(sl_order_id)
            db.commit()
            logger.info(f"[ProgramExecution] Updated log {log_id} with order IDs")

            # Paper fills carry an accurate realized_pnl synchronously in order_result.
            # Write it back immediately -- unlike real fills, whose realized_pnl on this
            # log is otherwise only backfilled by a separate "user refresh" job (see
            # ProgramExecutionLog.realized_pnl column comment) that has no real exchange
            # order to reconcile paper trades against. Mirrors the immediate writeback
            # trading_commands.py applies to AIDecisionLog.realized_pnl for paper closes.
            if environment == "paper" and order_result.get("status") == "filled" and order_result.get("realized_pnl"):
                log.realized_pnl = order_result["realized_pnl"]
                log.pnl_updated_at = datetime.utcnow()
                db.commit()

            # Create HyperliquidTrade record only if order is filled
            order_status = order_result.get('status')
            if order_status == 'filled':
                self._create_hyperliquid_trade(
                    binding, decision, order_result, wallet_address, environment, exchange
                )

        except Exception as e:
            logger.error(f"[ProgramExecution] Failed to update log with order: {e}")

    def _create_hyperliquid_trade(
        self,
        binding: AccountProgramBinding,
        decision,
        order_result: dict,
        wallet_address: str,
        environment: str,
        exchange: str = "hyperliquid"
    ):
        """Create HyperliquidTrade record for filled orders."""
        try:
            from database.snapshot_connection import SnapshotSessionLocal
            from database.snapshot_models import HyperliquidTrade
            from decimal import Decimal

            op = decision.operation.lower() if hasattr(decision, 'operation') else decision.action.value
            order_id = order_result.get('order_id')
            order_status = order_result.get('status')
            leverage = decision.leverage if hasattr(decision, 'leverage') else 1

            # Use different field names based on exchange
            if exchange == "binance":
                # Binance uses filled_qty, avg_price
                filled_qty = float(order_result.get('filled_qty', 0))
                avg_price = float(order_result.get('avg_price', 0))
                # Fallback to decision values if Binance returns 0
                decision_qty = float(decision.quantity) if hasattr(decision, 'quantity') else 0
                decision_price = float(decision.price) if hasattr(decision, 'price') else 0
                trade_qty = Decimal(str(filled_qty)) if filled_qty > 0 else Decimal(str(decision_qty))
                trade_price = Decimal(str(avg_price)) if avg_price > 0 else Decimal(str(decision_price))
            else:
                # Hyperliquid uses filled_amount, average_price
                trade_qty = Decimal(str(order_result.get('filled_amount', 0)))
                trade_price = Decimal(str(order_result.get('average_price', 0)))

            snapshot_db = SnapshotSessionLocal()
            try:
                trade_record = HyperliquidTrade(
                    account_id=binding.account_id,
                    environment=environment,
                    wallet_address=wallet_address,
                    symbol=decision.symbol,
                    side=op,
                    quantity=trade_qty,
                    price=trade_price,
                    leverage=leverage,
                    order_id=order_id,
                    order_status=order_status,
                    trade_value=trade_qty * trade_price,
                    fee=Decimal(str(order_result.get('fee', 0)))
                )
                snapshot_db.add(trade_record)
                snapshot_db.commit()
                logger.info(f"[ProgramExecution] HyperliquidTrade record saved for binding {binding.id}")
            finally:
                snapshot_db.close()
        except Exception as e:
            logger.warning(f"[ProgramExecution] Failed to save HyperliquidTrade record: {e}")

    def _handle_decision(
        self,
        db,
        binding: AccountProgramBinding,
        decision,
        symbol: str,
        wallet_address: Optional[str],
        exchange: str = "hyperliquid",
        trading_client=None
    ):
        """Handle the decision from program execution - execute actual trade."""
        from program_trader.executor import validate_decision
        from services.hyperliquid_environment import get_global_trading_mode, get_hyperliquid_client
        from paper_trading import get_execution_mode

        op = decision.operation.lower() if hasattr(decision, 'operation') else decision.action.value

        if op == "hold":
            logger.info(f"[ProgramExecution] Binding {binding.id} decision: HOLD - {decision.reason}")
            return None  # HOLD is not an order, no success/failure

        # Validate decision
        positions_dict = {}
        is_paper = get_execution_mode(db, binding.account_id) == "paper"
        environment = "paper" if is_paper else get_global_trading_mode(db)

        # Note: Quota check is now done in _execute_binding before logging,
        # so we don't need to check again here.

        # Use provided trading_client or create one based on exchange
        client = trading_client
        if not client:
            if is_paper:
                from paper_trading.client import PaperTradingClient
                client = PaperTradingClient(binding.account_id, exchange)
            elif exchange == "binance":
                try:
                    from services.binance_trading_client import BinanceTradingClient
                    from database.models import BinanceWallet
                    from utils.encryption import decrypt_private_key

                    binance_wallet = db.query(BinanceWallet).filter(
                        BinanceWallet.account_id == binding.account_id,
                        BinanceWallet.environment == (environment or "mainnet"),
                        BinanceWallet.is_active == "true"
                    ).first()

                    if binance_wallet:
                        api_key = decrypt_private_key(binance_wallet.api_key_encrypted)
                        secret_key = decrypt_private_key(binance_wallet.secret_key_encrypted)
                        client = BinanceTradingClient(api_key, secret_key, environment or "mainnet")
                    else:
                        logger.error(f"[ProgramExecution] No active Binance wallet found for account {binding.account_id}")
                        return False
                except Exception as e:
                    logger.error(f"[ProgramExecution] Failed to create Binance client: {e}")
                    return False
            else:
                client = get_hyperliquid_client(db, binding.account_id, override_environment=environment)

        if hasattr(decision, 'operation'):
            # New Decision format - get positions for validation
            if environment and client:
                try:
                    # Paper mode always reads mainnet market data (same rationale as
                    # the DataProvider built in _execute_binding); "paper" itself is
                    # not a valid environment for market-data API routing.
                    data_provider = DataProvider(
                        db, binding.account_id, "mainnet" if is_paper else environment, client, exchange=exchange
                    )
                    for sym, pos in data_provider.get_positions().items():
                        positions_dict[sym] = {"side": pos.side, "size": pos.size}
                except Exception as e:
                    logger.warning(f"[ProgramExecution] Failed to get positions for validation: {e}")

            is_valid, errors = validate_decision(decision, positions_dict)
            if not is_valid:
                logger.error(f"[ProgramExecution] Invalid decision: {errors}")
                return False

        logger.info(
            f"[ProgramExecution] Binding {binding.id} decision: {op} "
            f"{decision.symbol} portion={getattr(decision, 'target_portion_of_balance', 0)} "
            f"leverage={decision.leverage}x exchange={exchange} - {decision.reason}"
        )

        # Check wallet (for Binance, wallet_address may be API key indicator)
        if not wallet_address and exchange != "binance":
            logger.error(f"[ProgramExecution] No wallet address for binding {binding.id}")
            return False

        if not environment:
            logger.error(f"[ProgramExecution] No trading environment configured")
            return False

        try:
            # Get account info and current market price
            account_info = client.get_account_state(db)
            available_balance = account_info.get("available_balance", 0)

            # Get real-time market price based on exchange
            if is_paper:
                # PaperTradingClient has no get_mark_price()/exchange-specific price API;
                # use the same generic lookup the paper client uses internally
                # (services.market_data.get_last_price), always against mainnet data.
                from services.market_data import get_last_price
                market_price = get_last_price(decision.symbol, market=("binance" if exchange == "binance" else "CRYPTO"))
            elif exchange == "binance":
                market_price = client.get_mark_price(decision.symbol)
            else:
                from services.hyperliquid_market_data import get_last_price_from_hyperliquid
                market_price = get_last_price_from_hyperliquid(decision.symbol, environment)

            if not market_price or market_price <= 0:
                market_price = getattr(decision, 'max_price', None) or getattr(decision, 'min_price', None)
            if not market_price:
                logger.error(f"[ProgramExecution] No price available for {decision.symbol}")
                return False

            # Validate TP/SL prices against market price (approximate entry)
            if op in ("buy", "sell"):
                from program_trader.executor import validate_tp_sl_prices
                tp_valid, tp_errors = validate_tp_sl_prices(
                    operation=op,
                    entry_price=market_price,
                    take_profit_price=getattr(decision, 'take_profit_price', None),
                    stop_loss_price=getattr(decision, 'stop_loss_price', None),
                )
                if not tp_valid:
                    logger.error(f"[ProgramExecution] Invalid TP/SL: {tp_errors}")
                    return False

            # Execute based on operation type
            order_result = None
            if op == "buy":
                order_result = self._execute_buy(
                    db, client, decision, available_balance, market_price, environment
                )
            elif op == "sell":
                order_result = self._execute_sell(
                    db, client, decision, available_balance, market_price, environment
                )
            elif op == "close":
                order_result = self._execute_close(
                    db, client, decision, positions_dict, market_price, environment
                )

            # Log result
            if order_result and order_result.get("status") in ["filled", "resting"]:
                logger.info(f"[ProgramExecution] Order succeeded on {exchange}: {order_result}")
                return order_result  # Return full order_result for trade record creation
            else:
                error_msg = order_result.get('error', 'Unknown error') if order_result else 'No result'
                logger.error(f"[ProgramExecution] Order failed on {exchange}: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing trade on {exchange}: {e}")
            return None

    def _execute_buy(self, db, client, decision, available_balance, market_price, environment):
        """Execute BUY order with price bounds and IOC->GTC retry."""
        symbol = decision.symbol
        leverage = decision.leverage
        portion = getattr(decision, 'target_portion_of_balance', 0)
        time_in_force = getattr(decision, 'time_in_force', 'Ioc')

        # Calculate position size
        margin = available_balance * portion
        order_value = margin * leverage
        quantity = round(order_value / market_price, 6)

        # Use max_price from decision directly (no bounds adjustment)
        max_price = getattr(decision, 'max_price', None)
        if max_price:
            price_to_use = max_price
        else:
            price_to_use = market_price * 1.005  # Default: slightly above market
            logger.warning(f"[ProgramExecution] BUY {symbol}: No max_price, using {price_to_use:.2f}")

        logger.info(
            f"[ProgramExecution] BUY {symbol}: size={quantity}, price={price_to_use:.2f}, "
            f"leverage={leverage}x, TIF={time_in_force}"
        )

        # Place order
        order_result = client.place_order_with_tpsl(
            db=db, symbol=symbol, is_buy=True, size=quantity, price=price_to_use,
            leverage=leverage, time_in_force=time_in_force, reduce_only=False,
            take_profit_price=getattr(decision, 'take_profit_price', None),
            stop_loss_price=getattr(decision, 'stop_loss_price', None),
            tp_execution=getattr(decision, 'tp_execution', 'limit'),
            sl_execution=getattr(decision, 'sl_execution', 'limit'),
        )

        # IOC->GTC retry if no liquidity
        if order_result and order_result.get('status') == 'error':
            error_msg = order_result.get('error', '').lower()
            if 'could not immediately match' in error_msg or 'no resting orders' in error_msg:
                logger.warning(f"[ProgramExecution] BUY {symbol} IOC failed, retrying with GTC...")
                order_result = client.place_order_with_tpsl(
                    db=db, symbol=symbol, is_buy=True, size=quantity, price=price_to_use,
                    leverage=leverage, time_in_force="Gtc", reduce_only=False,
                    take_profit_price=getattr(decision, 'take_profit_price', None),
                    stop_loss_price=getattr(decision, 'stop_loss_price', None),
                    tp_execution=getattr(decision, 'tp_execution', 'limit'),
                    sl_execution=getattr(decision, 'sl_execution', 'limit'),
                )
                if order_result and order_result.get('status') in ['filled', 'resting']:
                    logger.info(f"[ProgramExecution] BUY {symbol} GTC fallback succeeded")

        return order_result

    def _execute_sell(self, db, client, decision, available_balance, market_price, environment):
        """Execute SELL order with price bounds and IOC->GTC retry."""
        symbol = decision.symbol
        leverage = decision.leverage
        portion = getattr(decision, 'target_portion_of_balance', 0)
        time_in_force = getattr(decision, 'time_in_force', 'Ioc')

        # Calculate position size
        margin = available_balance * portion
        order_value = margin * leverage
        quantity = round(order_value / market_price, 6)

        # Use min_price from decision directly (no bounds adjustment)
        min_price = getattr(decision, 'min_price', None)
        if min_price:
            price_to_use = min_price
        else:
            price_to_use = market_price * 0.995  # Default: slightly below market
            logger.warning(f"[ProgramExecution] SELL {symbol}: No min_price, using {price_to_use:.2f}")

        logger.info(
            f"[ProgramExecution] SELL {symbol}: size={quantity}, price={price_to_use:.2f}, "
            f"leverage={leverage}x, TIF={time_in_force}"
        )

        # Place order
        order_result = client.place_order_with_tpsl(
            db=db, symbol=symbol, is_buy=False, size=quantity, price=price_to_use,
            leverage=leverage, time_in_force=time_in_force, reduce_only=False,
            take_profit_price=getattr(decision, 'take_profit_price', None),
            stop_loss_price=getattr(decision, 'stop_loss_price', None),
            tp_execution=getattr(decision, 'tp_execution', 'limit'),
            sl_execution=getattr(decision, 'sl_execution', 'limit'),
        )

        # IOC->GTC retry if no liquidity
        if order_result and order_result.get('status') == 'error':
            error_msg = order_result.get('error', '').lower()
            if 'could not immediately match' in error_msg or 'no resting orders' in error_msg:
                logger.warning(f"[ProgramExecution] SELL {symbol} IOC failed, retrying with GTC...")
                order_result = client.place_order_with_tpsl(
                    db=db, symbol=symbol, is_buy=False, size=quantity, price=price_to_use,
                    leverage=leverage, time_in_force="Gtc", reduce_only=False,
                    take_profit_price=getattr(decision, 'take_profit_price', None),
                    stop_loss_price=getattr(decision, 'stop_loss_price', None),
                    tp_execution=getattr(decision, 'tp_execution', 'limit'),
                    sl_execution=getattr(decision, 'sl_execution', 'limit'),
                )
                if order_result and order_result.get('status') in ['filled', 'resting']:
                    logger.info(f"[ProgramExecution] SELL {symbol} GTC fallback succeeded")

        return order_result

    def _execute_close(self, db, client, decision, positions_dict, market_price, environment):
        """Execute CLOSE order with multi-retry and GTC fallback."""
        symbol = decision.symbol
        portion = getattr(decision, 'target_portion_of_balance', 1.0)

        # Get position info
        pos_info = positions_dict.get(symbol, {})
        is_long = pos_info.get("side") == "long"
        position_size = pos_info.get("size", 0)

        if not position_size or position_size <= 0:
            logger.warning(f"[ProgramExecution] CLOSE {symbol}: No position found")
            return {"status": "error", "error": "No position to close"}

        close_size = position_size * portion

        # Use price from decision directly (no bounds adjustment)
        if is_long:
            # Close long = sell, use min_price
            ai_price = getattr(decision, 'min_price', None)
            fallback_mult = 0.995
        else:
            # Close short = buy, use max_price
            ai_price = getattr(decision, 'max_price', None)
            fallback_mult = 1.005

        if ai_price:
            close_price = ai_price
        else:
            close_price = market_price * fallback_mult

        # Validate price direction (only when AI didn't provide price)
        if not ai_price:
            if not is_long and close_price < market_price:
                close_price = market_price * 1.005
            elif is_long and close_price > market_price:
                close_price = market_price * 0.995

        logger.info(
            f"[ProgramExecution] CLOSE {symbol}: size={close_size}, price={close_price:.2f}, "
            f"direction={'long->sell' if is_long else 'short->buy'}"
        )

        # Multi-retry with progressive price adjustment
        max_retries = 4
        price_mults = [0.996, 0.994, 0.992, 0.99] if is_long else [1.004, 1.006, 1.008, 1.01]
        order_result = None

        for retry in range(max_retries):
            attempt_price = close_price if retry == 0 else market_price * price_mults[retry]
            if retry > 0:
                logger.info(f"[ProgramExecution] CLOSE {symbol} retry {retry}: price={attempt_price:.2f}")

            attempt_result = client.place_order_with_tpsl(
                db=db, symbol=symbol, is_buy=(not is_long), size=close_size,
                price=attempt_price, leverage=1, time_in_force="Ioc", reduce_only=True,
                take_profit_price=None, stop_loss_price=None,
            )

            if attempt_result and attempt_result.get('status') == 'filled':
                order_result = attempt_result
                if retry > 0:
                    logger.info(f"[ProgramExecution] CLOSE {symbol} succeeded on retry {retry}")
                break

            error_msg = attempt_result.get('error', '').lower() if attempt_result else ''
            should_retry = 'could not immediately match' in error_msg or 'no resting orders' in error_msg
            if not should_retry or retry >= max_retries - 1:
                order_result = attempt_result
                break

        # GTC fallback if IOC retries failed
        if not order_result or order_result.get('status') != 'filled':
            boundary_mult = 0.99 if is_long else 1.01
            fallback_price = market_price * boundary_mult
            logger.warning(f"[ProgramExecution] CLOSE {symbol} fallback: GTC at {fallback_price:.2f}")

            order_result = client.place_order_with_tpsl(
                db=db, symbol=symbol, is_buy=(not is_long), size=close_size,
                price=fallback_price, leverage=1, time_in_force="Gtc", reduce_only=True,
                take_profit_price=None, stop_loss_price=None,
            )

        return order_result


# Singleton instance
program_execution_service = ProgramExecutionService()
