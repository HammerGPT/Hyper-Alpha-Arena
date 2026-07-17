"""Tool-layer regression coverage for the update_trader_strategy signal-pool
omission bug: an LLM tool call that omits signal_pool_ids (e.g. one that only
changes trigger_interval) must not silently unbind the trader's signal pools.

The bug lived in the execute_hyper_ai_tool dispatcher, which built kwargs via
a bare `arguments.get("signal_pool_ids")` - indistinguishable from an explicit
None/unbind-all request once it reached upsert_strategy. The fix extracts the
dispatcher's kwargs-building into build_update_trader_strategy_kwargs(), which
is tested directly here (no DB needed), plus an end-to-end check through
execute_update_trader_strategy + upsert_strategy against a real db_session.
"""
from services.hyper_ai_tools import (
    build_update_trader_strategy_kwargs,
    execute_update_trader_strategy,
)
from repositories.strategy_repo import upsert_strategy, get_strategy_by_account, _UNSET


def test_kwargs_builder_omits_signal_pool_ids_when_key_absent():
    """Mirrors an LLM tool call that only supplies trigger_interval."""
    kwargs = build_update_trader_strategy_kwargs({"trader_id": 5, "trigger_interval": 200})
    assert "signal_pool_ids" not in kwargs
    assert kwargs["trader_id"] == 5
    assert kwargs["trigger_interval"] == 200


def test_kwargs_builder_passes_through_explicit_empty_list():
    kwargs = build_update_trader_strategy_kwargs({"trader_id": 5, "signal_pool_ids": []})
    assert kwargs["signal_pool_ids"] == []


def test_kwargs_builder_passes_through_explicit_list():
    kwargs = build_update_trader_strategy_kwargs({"trader_id": 5, "signal_pool_ids": [1, 2]})
    assert kwargs["signal_pool_ids"] == [1, 2]


def test_kwargs_builder_passes_through_explicit_none():
    """If the LLM explicitly sends signal_pool_ids: null, the key is present
    with value None - this must still flow through (existing unbind contract),
    distinct from the key being absent entirely."""
    kwargs = build_update_trader_strategy_kwargs({"trader_id": 5, "signal_pool_ids": None})
    assert "signal_pool_ids" in kwargs
    assert kwargs["signal_pool_ids"] is None


def test_execute_update_trader_strategy_default_is_unset_sentinel():
    """Guards against a future refactor accidentally reverting the default
    back to None, which would reopen the bug."""
    import inspect
    sig = inspect.signature(execute_update_trader_strategy)
    assert sig.parameters["signal_pool_ids"].default is _UNSET


def test_end_to_end_omitted_signal_pool_ids_preserves_bindings(db_session):
    """Full path: dispatcher kwargs-builder -> execute_update_trader_strategy
    -> upsert_strategy, against a real db_session, reproducing the exact
    reported bug scenario (an update that only changes trigger_interval)."""
    from database.models import User, Account
    import json as json_module

    user = User(username="t_tool_layer_pool_preserve")
    db_session.add(user)
    db_session.flush()

    account = Account(user_id=user.id, name="Tool Layer Trader", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    # Bind two signal pools first.
    upsert_strategy(db_session, account_id=account.id, trigger_interval=150, signal_pool_ids=[10, 20])

    # Simulate the LLM's tool call arguments omitting signal_pool_ids entirely,
    # only changing trigger_interval - exactly the reported failure scenario.
    arguments = {"trader_id": account.id, "trigger_interval": 300}
    kwargs = build_update_trader_strategy_kwargs(arguments)
    result = json_module.loads(execute_update_trader_strategy(db_session, **kwargs))

    assert result["success"] is True
    assert result["signal_pool_ids"] == [10, 20], "omitted signal_pool_ids must preserve existing bindings"

    strategy = get_strategy_by_account(db_session, account.id)
    assert strategy.signal_pool_ids == "[10, 20]"
    assert strategy.trigger_interval == 300


def test_end_to_end_explicit_empty_list_unbinds(db_session):
    from database.models import User, Account
    import json as json_module

    user = User(username="t_tool_layer_pool_unbind")
    db_session.add(user)
    db_session.flush()

    account = Account(user_id=user.id, name="Tool Layer Trader 2", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    upsert_strategy(db_session, account_id=account.id, trigger_interval=150, signal_pool_ids=[10, 20])

    # trigger_interval must still be supplied here: upsert_strategy's
    # trigger_interval handling is unconditional (`trigger_interval or
    # interval_seconds`), unlike the None-preserve semantics of the other
    # fields - unrelated to this bug, but omitting it would hit a NOT NULL
    # constraint rather than exercising the signal_pool_ids behavior.
    arguments = {"trader_id": account.id, "trigger_interval": 150, "signal_pool_ids": []}
    kwargs = build_update_trader_strategy_kwargs(arguments)
    result = json_module.loads(execute_update_trader_strategy(db_session, **kwargs))

    assert result["success"] is True
    assert result["signal_pool_ids"] == [], "explicit [] from the LLM must still unbind"
