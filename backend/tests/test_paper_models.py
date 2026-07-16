"""Paper trading ORM model tests."""


def test_paper_account_defaults(db_session):
    from database.models import PaperAccount
    paper = PaperAccount(account_id=1, data_exchange="hyperliquid")
    db_session.add(paper)
    db_session.flush()
    assert float(paper.initial_capital) == 10000.00
    assert float(paper.realized_pnl_total) == 0
    assert float(paper.total_fees) == 0
    assert float(paper.total_funding) == 0
    assert paper.cycle == 1
    assert paper.taker_fee_pct is None


def test_paper_order_defaults(db_session, paper_account):
    from database.models import PaperOrder
    order = PaperOrder(
        paper_account_id=paper_account.id, order_no="P-abc", symbol="BTC",
        side="sell", order_type="take_profit", trigger_price=120000, size=0.1,
        cycle=1,
    )
    db_session.add(order)
    db_session.flush()
    assert order.status == "pending"
    assert order.exec_mode == "limit"
    assert order.reduce_only is True
    assert order.leverage == 1


def test_strategy_config_execution_mode_default(db_session):
    from database.models import AccountStrategyConfig
    cfg = AccountStrategyConfig(account_id=1)
    db_session.add(cfg)
    db_session.flush()
    assert cfg.execution_mode == "real"
