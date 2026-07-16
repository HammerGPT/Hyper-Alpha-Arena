"""Program Trader execution service - paper mode branch (Task 10).

Covers the one behavior change made beyond the brief's literal diff: an
immediate realized_pnl writeback on ProgramExecutionLog for paper fills,
mirroring the pattern trading_commands.py already applies to
AIDecisionLog.realized_pnl for paper closes. Real-path (non-paper) behavior
is untouched by this fix, so it is not re-tested here (covered by the
existing 52-test suite continuing to pass).
"""


def test_update_log_with_order_writes_realized_pnl_for_paper_fill(db_session, monkeypatch):
    from database.models import User, Account, ProgramExecutionLog
    from services.program_execution_service import ProgramExecutionService

    ProgramExecutionLog.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    u = User(username="pt_paper")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="PT", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    log = ProgramExecutionLog(
        account_id=account.id,
        trigger_type="signal",
        success=True,
        environment="paper",
    )
    db_session.add(log)
    db_session.flush()

    service = ProgramExecutionService()
    # Avoid the real snapshot-DB trade write (a separate concern, unrelated to
    # the realized_pnl writeback under test here).
    monkeypatch.setattr(service, "_create_hyperliquid_trade", lambda *a, **kw: None)

    class FakeDecision:
        symbol = "BTC"
        leverage = 1
        operation = "close"

    order_result = {
        "status": "filled",
        "order_id": "P-1",
        "realized_pnl": 12.5,
    }

    service._update_log_with_order(
        db_session, log.id, order_result, binding=None, decision=FakeDecision(),
        wallet_address="paper-1", environment="paper", exchange="hyperliquid",
    )

    db_session.refresh(log)
    assert log.realized_pnl == 12.5
    assert log.pnl_updated_at is not None


def test_update_log_with_order_skips_realized_pnl_for_real_fill(db_session, monkeypatch):
    """Real-path fills are untouched: this log's realized_pnl stays unset,
    consistent with pre-existing behavior (backfilled elsewhere via 'user refresh')."""
    from database.models import User, Account, ProgramExecutionLog
    from services.program_execution_service import ProgramExecutionService

    ProgramExecutionLog.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    u = User(username="pt_real")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="PT2", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    log = ProgramExecutionLog(
        account_id=account.id,
        trigger_type="signal",
        success=True,
        environment="mainnet",
    )
    db_session.add(log)
    db_session.flush()

    service = ProgramExecutionService()
    monkeypatch.setattr(service, "_create_hyperliquid_trade", lambda *a, **kw: None)

    class FakeDecision:
        symbol = "BTC"
        leverage = 1
        operation = "close"

    order_result = {
        "status": "filled",
        "order_id": "R-1",
        "realized_pnl": 99.0,
    }

    service._update_log_with_order(
        db_session, log.id, order_result, binding=None, decision=FakeDecision(),
        wallet_address="0xabc", environment="mainnet", exchange="hyperliquid",
    )

    db_session.refresh(log)
    assert log.realized_pnl is None
    assert log.pnl_updated_at is None
