"""enabled / trigger_mode / exchange / scheduled_trigger_enabled preservation on
partial strategy updates: schema -> repo -> ORM.

Mirrors the pattern established for execution_mode in test_execution_mode_config.py
(commit "Preserve execution_mode on partial strategy updates").
"""
from repositories.strategy_repo import upsert_strategy


def test_partial_update_preserves_enabled_and_exchange(db_session):
    # Explicit creation: disabled trader, bound to Binance.
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150,
        enabled=False, exchange="binance",
    )
    assert strategy.enabled == "false"
    assert strategy.exchange == "binance"

    # Partial update: only trigger_interval changes. A caller (e.g. an AI tool call
    # that only wants to change the interval) must NOT silently re-enable the trader
    # or flip it back to hyperliquid.
    strategy = upsert_strategy(db_session, account_id=1, trigger_interval=200)
    assert strategy.enabled == "false", "partial update must preserve enabled=False"
    assert strategy.exchange == "binance", "partial update must preserve exchange=binance"
    assert strategy.trigger_interval == 200


def test_partial_update_preserves_trigger_mode(db_session):
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150, trigger_mode="unified",
    )
    assert strategy.trigger_mode == "unified"

    strategy = upsert_strategy(db_session, account_id=1, trigger_interval=180)
    assert strategy.trigger_mode == "unified"


def test_partial_update_preserves_scheduled_trigger_enabled(db_session):
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150,
        scheduled_trigger_enabled=False,
    )
    assert strategy.scheduled_trigger_enabled is False

    # Omitting scheduled_trigger_enabled on a later call must not silently
    # re-enable the scheduled trigger.
    strategy = upsert_strategy(db_session, account_id=1, trigger_interval=175)
    assert strategy.scheduled_trigger_enabled is False


def test_creation_defaults(db_session):
    """A brand-new strategy row with nothing passed gets the historical defaults."""
    strategy = upsert_strategy(db_session, account_id=2, trigger_interval=150)
    assert strategy.enabled == "true"
    assert strategy.exchange == "hyperliquid"
    assert strategy.trigger_mode == "unified"
    assert strategy.scheduled_trigger_enabled is True


def test_explicit_updates_still_apply(db_session):
    """Explicitly-supplied values must still take effect (not just be preserved)."""
    strategy = upsert_strategy(
        db_session, account_id=3, trigger_interval=150,
        enabled=True, exchange="hyperliquid", scheduled_trigger_enabled=True,
    )
    assert strategy.enabled == "true"
    assert strategy.exchange == "hyperliquid"

    strategy = upsert_strategy(
        db_session, account_id=3, trigger_interval=150,
        enabled=False, exchange="binance", scheduled_trigger_enabled=False,
    )
    assert strategy.enabled == "false"
    assert strategy.exchange == "binance"
    assert strategy.scheduled_trigger_enabled is False


def test_invalid_exchange_on_existing_row_is_preserved(db_session):
    """An invalid, non-None exchange value must not clobber a valid current value."""
    strategy = upsert_strategy(
        db_session, account_id=4, trigger_interval=150, exchange="binance",
    )
    assert strategy.exchange == "binance"

    strategy = upsert_strategy(
        db_session, account_id=4, trigger_interval=150, exchange="not-a-real-exchange",
    )
    assert strategy.exchange == "binance", "invalid exchange must not overwrite an existing valid value"


def test_invalid_exchange_on_creation_falls_back_to_hyperliquid(db_session):
    """An invalid exchange supplied while creating a brand-new row has nothing to
    preserve, so it falls back to the historical default."""
    strategy = upsert_strategy(
        db_session, account_id=5, trigger_interval=150, exchange="not-a-real-exchange",
    )
    assert strategy.exchange == "hyperliquid"


def test_exchange_normalized_lowercase(db_session):
    strategy = upsert_strategy(
        db_session, account_id=6, trigger_interval=150, exchange="BINANCE",
    )
    assert strategy.exchange == "binance"


def test_schema_partial_update_fields_default_to_none():
    """Omitted fields in the PUT payload must decode to None (preserve), not the
    old hardcoded defaults - mirrors execution_mode's schema contract."""
    from schemas.account import StrategyConfigUpdate

    payload = StrategyConfigUpdate()
    assert payload.enabled is None
    assert payload.trigger_mode is None
    assert payload.exchange is None
    assert payload.scheduled_trigger_enabled is None
    assert payload.execution_mode is None

    payload = StrategyConfigUpdate(enabled=False, trigger_mode="unified", exchange="binance")
    assert payload.enabled is False
    assert payload.trigger_mode == "unified"
    assert payload.exchange == "binance"
