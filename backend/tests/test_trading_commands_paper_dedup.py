"""Guards item 1 (double-recorded paper fills) at the AI-Binance pipeline write
sites in trading_commands.py: PaperEngine._record_fill is the sole writer of
HyperliquidTrade rows for environment="paper" (with the real fee). The two
pipeline write sites in _execute_binance_decision (the "close" branch and the
general buy/sell branch) must be skipped for is_paper=True, or every paper
fill gets a second row (same order_id, fee=0) that corrupts fee-attribution
joins keyed on order_id. Real (non-paper) fills still need these writes since
no PaperEngine runs for them.

A fake trading client stands in for PaperTradingClient/BinanceTradingClient --
the guard under test is purely "does _execute_binance_decision itself call
HyperliquidTrade(...)", independent of what a real client would do.
"""
import database.snapshot_connection as snapshot_connection


class FakeBinanceClient:
    """Stub with just enough surface for _execute_binance_decision's buy/close paths."""

    def __init__(self, order_id="B-1"):
        self.order_id = order_id

    def place_order_with_tpsl(self, **kwargs):
        return {
            "status": "filled",
            "order_id": self.order_id,
            "filled_qty": 0.01,
            "avg_price": 50000.0,
            "fee": 0,
        }

    def close_position(self, symbol, cancel_tpsl=True):
        return {
            "status": "filled",
            "order_id": self.order_id,
            "filled_qty": 0.01,
            "avg_price": 50000.0,
            "realized_pnl": 5.0,
        }


def _setup_account(db_session):
    from database.models import User, Account, SystemConfig
    SystemConfig.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    u = User(username=f"tc_dedup_{id(db_session)}")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="TCDedup", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    return account


def _count_trades(snapshot_session_factory):
    from database.snapshot_models import HyperliquidTrade
    sdb = snapshot_session_factory()
    try:
        return len(sdb.query(HyperliquidTrade).all())
    finally:
        sdb.close()


def test_binance_buy_skips_hyperliquid_trade_write_when_paper(db_session, snapshot_session_factory, monkeypatch):
    from services.trading_commands import _execute_binance_decision
    monkeypatch.setattr(snapshot_connection, "SnapshotSessionLocal", snapshot_session_factory)

    account = _setup_account(db_session)
    decision = {
        "operation": "buy", "symbol": "BTC", "target_portion_of_balance": 0.1,
        "leverage": 2, "reason": "test",
    }
    _execute_binance_decision(
        db=db_session, account=account, client=FakeBinanceClient(),
        decision=decision, portfolio={"total_assets": 10000}, positions=[],
        prices={"BTC": 50000.0}, available_balance=10000.0,
        is_paper=True,
    )
    assert _count_trades(snapshot_session_factory) == 0


def test_binance_buy_writes_hyperliquid_trade_when_real(db_session, snapshot_session_factory, monkeypatch):
    from services.trading_commands import _execute_binance_decision
    monkeypatch.setattr(snapshot_connection, "SnapshotSessionLocal", snapshot_session_factory)

    account = _setup_account(db_session)
    decision = {
        "operation": "buy", "symbol": "BTC", "target_portion_of_balance": 0.1,
        "leverage": 2, "reason": "test",
    }
    _execute_binance_decision(
        db=db_session, account=account, client=FakeBinanceClient(),
        decision=decision, portfolio={"total_assets": 10000}, positions=[],
        prices={"BTC": 50000.0}, available_balance=10000.0,
        is_paper=False,
    )
    assert _count_trades(snapshot_session_factory) == 1


def test_binance_close_skips_hyperliquid_trade_write_when_paper(db_session, snapshot_session_factory, monkeypatch):
    from services.trading_commands import _execute_binance_decision
    monkeypatch.setattr(snapshot_connection, "SnapshotSessionLocal", snapshot_session_factory)

    account = _setup_account(db_session)
    decision = {"operation": "close", "symbol": "BTC", "reason": "test"}
    _execute_binance_decision(
        db=db_session, account=account, client=FakeBinanceClient(order_id="B-2"),
        decision=decision, portfolio={"total_assets": 10000}, positions=[],
        prices={"BTC": 50000.0}, available_balance=10000.0,
        is_paper=True,
    )
    assert _count_trades(snapshot_session_factory) == 0


def test_binance_close_writes_hyperliquid_trade_when_real(db_session, snapshot_session_factory, monkeypatch):
    from services.trading_commands import _execute_binance_decision
    monkeypatch.setattr(snapshot_connection, "SnapshotSessionLocal", snapshot_session_factory)

    account = _setup_account(db_session)
    decision = {"operation": "close", "symbol": "BTC", "reason": "test"}
    _execute_binance_decision(
        db=db_session, account=account, client=FakeBinanceClient(order_id="B-2"),
        decision=decision, portfolio={"total_assets": 10000}, positions=[],
        prices={"BTC": 50000.0}, available_balance=10000.0,
        is_paper=False,
    )
    assert _count_trades(snapshot_session_factory) == 1
