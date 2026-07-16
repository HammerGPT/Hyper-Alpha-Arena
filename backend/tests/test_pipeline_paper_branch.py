"""Paper-mode helpers used by AI/program pipelines."""


def test_get_execution_mode(db_session):
    from database.models import AccountStrategyConfig
    from paper_trading import get_execution_mode
    assert get_execution_mode(db_session, 99) == "real"  # no config -> real
    cfg = AccountStrategyConfig(account_id=99, execution_mode="paper")
    db_session.add(cfg)
    db_session.flush()
    assert get_execution_mode(db_session, 99) == "paper"


def test_save_ai_decision_returns_log(db_session):
    from database.models import User, Account, SystemConfig
    from services.ai_decision_service import save_ai_decision
    # save_ai_decision tags each log with the global trading mode (via
    # get_global_trading_mode), which queries system_configs. The shared
    # db_session fixture doesn't provision that table, so create it here
    # (empty table is fine -- the lookup falls back to "testnet" default).
    SystemConfig.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    u = User(username="t1")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="T", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    log = save_ai_decision(
        db_session, account,
        decision={"operation": "buy", "symbol": "BTC", "target_portion_of_balance": 0.1,
                  "reason": "test"},
        portfolio={"total_assets": 10000},
        executed=True,
        hyperliquid_order_id="P-abc",
        exchange="hyperliquid",
    )
    assert log is not None
    assert log.hyperliquid_order_id == "P-abc"


def test_save_ai_decision_environment_override(db_session):
    from database.models import User, Account, SystemConfig
    SystemConfig.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    from services.ai_decision_service import save_ai_decision
    u = User(username="t9fix")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="T9", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    log = save_ai_decision(
        db_session, account,
        decision={"operation": "buy", "symbol": "BTC", "target_portion_of_balance": 0.1, "reason": "t"},
        portfolio={"total_assets": 10000},
        executed=True, exchange="binance", environment="paper",
    )
    assert log.hyperliquid_environment == "paper"
