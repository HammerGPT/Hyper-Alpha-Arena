"""execution_mode propagation: schema -> repo -> ORM."""


def test_upsert_strategy_execution_mode(db_session):
    from repositories.strategy_repo import upsert_strategy
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150,
        exchange="hyperliquid", execution_mode="paper",
    )
    assert strategy.execution_mode == "paper"

    # partial update without execution_mode must preserve current value
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=200, exchange="hyperliquid",
    )
    assert strategy.execution_mode == "paper"

    # update back to real
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150,
        exchange="hyperliquid", execution_mode="real",
    )
    assert strategy.execution_mode == "real"


def test_upsert_strategy_invalid_mode_defaults_real(db_session):
    from repositories.strategy_repo import upsert_strategy
    strategy = upsert_strategy(
        db_session, account_id=2, trigger_interval=150,
        exchange="binance", execution_mode="bogus",
    )
    assert strategy.execution_mode == "real"


def test_upsert_strategy_mode_case_insensitive(db_session):
    from repositories.strategy_repo import upsert_strategy
    strategy = upsert_strategy(
        db_session, account_id=3, trigger_interval=150,
        exchange="hyperliquid", execution_mode="PAPER",
    )
    assert strategy.execution_mode == "paper"


def test_schema_has_execution_mode():
    from schemas.account import StrategyConfigUpdate
    payload = StrategyConfigUpdate(exchange="hyperliquid", execution_mode="paper")
    assert payload.execution_mode == "paper"
    assert StrategyConfigUpdate(exchange="hyperliquid").execution_mode is None
