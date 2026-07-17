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


def test_serialize_strategy_separates_enabled_from_account_pause(db_session):
    """Regression test for the enabled/auto_trading_enabled conflation bug.

    _serialize_strategy used to compute `enabled=(strategy.enabled == "true" and
    account.auto_trading_enabled == "true")`. Since the frontend stores this
    computed value and PUTs it back verbatim on every save, an account-level pause
    (auto_trading_enabled="false") silently flipped strategy.enabled to "false" in
    the DB on ANY save -- even one only touching an unrelated field. GET must
    report the raw per-strategy flag plus a separate auto_trading_enabled field,
    and that GET value must round-trip through PUT without mutating strategy.enabled.
    """
    from database.models import User, Account
    from api.account_routes import _serialize_strategy

    user = User(username="t_strategy_enabled_split")
    db_session.add(user)
    db_session.flush()

    account = Account(
        user_id=user.id, name="Paused Trader", model="m", api_key="k",
        auto_trading_enabled="false",
    )
    db_session.add(account)
    db_session.flush()

    # scheduled_trigger_enabled=False (and no signal pools) so _serialize_strategy's
    # prompt-binding warning lookup is skipped -- keeps this test independent of the
    # account_prompt_bindings table, which the shared db_session fixture doesn't create.
    strategy = upsert_strategy(
        db_session, account_id=account.id, trigger_interval=150,
        enabled=True, scheduled_trigger_enabled=False,
    )
    assert strategy.enabled == "true"

    serialized = _serialize_strategy(account, strategy, db_session)
    assert serialized.enabled is True, "enabled must reflect the strategy's own flag, not the account pause switch"
    assert serialized.auto_trading_enabled is False, "auto_trading_enabled must reflect the account-level pause switch"

    # Simulate the GET->PUT round-trip the frontend performs: it stores `enabled`
    # from the GET response and PUTs it back on a save that only changes an
    # unrelated field (e.g. trigger_interval). This must not clobber strategy.enabled.
    strategy = upsert_strategy(
        db_session, account_id=account.id, trigger_interval=200,
        enabled=serialized.enabled,
    )
    assert strategy.enabled == "true", "round-trip must preserve strategy.enabled=true even while the account is paused"


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


# --- signal_pool_ids / signal_pool_id omission semantics -------------------
#
# Regression coverage for the bug where an upsert_strategy call that omitted
# BOTH signal_pool_id and signal_pool_id args (e.g. an AI tool call that only
# changes trigger_interval) was indistinguishable from an explicit
# "unbind all pools" request, since both defaulted to None. Fixed via a
# module-level _UNSET sentinel in strategy_repo.py: omitted now means
# "preserve", while explicit None/[] still means "unbind" (the PUT route's
# existing, documented contract).

def test_omitting_pool_args_preserves_existing_bindings(db_session):
    """The bug's regression test: binding pools, then calling upsert_strategy
    again without mentioning signal_pool_ids/signal_pool_id at all (as the
    hyper_ai_tools dispatcher does when the LLM only changes trigger_interval)
    must NOT clear the trader's signal pool bindings."""
    strategy = upsert_strategy(
        db_session, account_id=201, trigger_interval=150,
        signal_pool_ids=[1, 2, 3],
    )
    assert strategy.signal_pool_ids == "[1, 2, 3]"
    assert strategy.signal_pool_id == 1

    # Partial update that never mentions pool args at all.
    strategy = upsert_strategy(db_session, account_id=201, trigger_interval=200)
    assert strategy.signal_pool_ids == "[1, 2, 3]", "omitted pool args must preserve existing bindings"
    assert strategy.signal_pool_id == 1
    assert strategy.trigger_interval == 200


def test_explicit_empty_list_unbinds_pools(db_session):
    """Explicit signal_pool_ids=[] is the documented unbind-all signal and must
    still clear bindings (unchanged from pre-fix behavior)."""
    strategy = upsert_strategy(
        db_session, account_id=202, trigger_interval=150,
        signal_pool_ids=[1, 2],
    )
    assert strategy.signal_pool_ids == "[1, 2]"

    strategy = upsert_strategy(db_session, account_id=202, trigger_interval=150, signal_pool_ids=[])
    assert strategy.signal_pool_ids is None, "explicit signal_pool_ids=[] must unbind all pools"
    assert strategy.signal_pool_id is None


def test_explicit_none_unbinds_pools(db_session):
    """Explicit signal_pool_ids=None (and signal_pool_id=None) is the PUT
    route's existing contract for a JSON body that nulls out the field -
    must still unbind, distinct from simply omitting the kwargs."""
    strategy = upsert_strategy(
        db_session, account_id=203, trigger_interval=150,
        signal_pool_ids=[7, 8],
    )
    assert strategy.signal_pool_ids == "[7, 8]"

    strategy = upsert_strategy(
        db_session, account_id=203, trigger_interval=150,
        signal_pool_id=None, signal_pool_ids=None,
    )
    assert strategy.signal_pool_ids is None, "explicit None/None must still unbind all pools"
    assert strategy.signal_pool_id is None


def test_explicit_signal_pool_id_alone_binds_single_pool(db_session):
    """Explicit legacy signal_pool_id (int) with signal_pool_ids omitted must
    still bind via the old single-pool format, unaffected by the sentinel
    change (mirrors pre-fix behavior where signal_pool_ids defaulted to None)."""
    strategy = upsert_strategy(
        db_session, account_id=204, trigger_interval=150, signal_pool_id=9,
    )
    assert strategy.signal_pool_ids == "[9]"
    assert strategy.signal_pool_id == 9

    # Omitting both on a later call preserves it.
    strategy = upsert_strategy(db_session, account_id=204, trigger_interval=175)
    assert strategy.signal_pool_ids == "[9]"
    assert strategy.signal_pool_id == 9
