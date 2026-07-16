# 纸交易通道（Paper Trading）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AI 交易员和程序化交易员新增纸交易执行模式——主网只读行情 + 系统内部持久化撮合（订单簿滑点、真实费率、funding、全仓清算），归因分析与看板全链路打通。

**Architecture:** 新建 `backend/paper_trading/` 包：`PaperTradingClient` 与真实交易 client 同接口，内部驱动 DB 持久化的 `PaperEngine`；`PaperMonitor` 后台高频轮询触发挂单/TP/SL/清算/funding。现有 AI/程序管线只在"获取 client"处按 `AccountStrategyConfig.execution_mode` 分叉，决策日志/成交记录/归因/资产曲线复用现有链路（environment="paper"）。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2 + PostgreSQL（主库/快照库分离）；React 18 + Vite + i18next；测试用 pytest + SQLite 内存库。

**Spec:** `docs/superpowers/specs/2026-07-16-paper-trading-design.md`（已批准，撮合/费率/清算规则以 spec 第 5 节为准）

## Global Constraints

- Python >= 3.12，包管理用 `uv`（backend/pyproject.toml；pytest 在 dev-dependencies 中）
- 后端测试命令统一：`cd backend` 后 `uv run pytest tests/ -v`（tests 目录本计划创建）
- 环境字面量：新环境值为小写 `"paper"`（写入 `AIDecisionLog.hyperliquid_environment`、`ProgramExecutionLog.environment`、`HyperliquidTrade.environment`、`HyperliquidAccountSnapshot.environment`）
- 纸交易订单号统一前缀 `"P-"`（`"P-" + uuid4().hex[:16]`），写入决策日志的 `hyperliquid_order_id` / `tp_order_id` / `sl_order_id`
- 纸交易虚拟钱包地址统一 `f"paper-{account_id}"`
- 默认费率（百分比）：hyperliquid taker 0.045 / maker 0.015；binance taker 0.05 / maker 0.02；默认回退滑点 0.05%
- 维持保证金 = 已用保证金 × 0.5（与 `hyperliquid_trading_client.get_account_state` 第 578 行估算口径一致）
- funding 结算周期：hyperliquid 1 小时，binance 8 小时；金额 = 持仓名义价值 × 费率，多头付正费率、空头收正费率
- 初始资金默认 10000 USD；重置开新周期（cycle+1），历史记录保留
- git 提交信息用仓库现有的简洁祈使句风格（如 "Add paper trading engine core"），结尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 前端构建检查：`cd frontend; npm run build`
- 后端所有新代码不得调用交易所任何写接口（下单/撤单/转账）——纸交易只读主网公开数据

---

### Task 1: 数据模型与迁移（4 张新表 + execution_mode 字段）

**Files:**
- Modify: `backend/database/models.py`（AccountStrategyConfig 在 291 行附近加一列；文件末尾追加 4 个新模型）
- Create: `backend/database/migrations/add_paper_trading_tables.py`
- Modify: `backend/database/migration_manager.py:81`（MIGRATIONS 列表末尾追加）
- Create: `backend/tests/__init__.py`（空文件）
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_paper_models.py`

**Interfaces:**
- Produces: ORM 模型 `PaperAccount`（字段 account_id/data_exchange/initial_capital/realized_pnl_total/total_fees/total_funding/cycle/cycle_started_at/taker_fee_pct/maker_fee_pct/slippage_fallback_pct/last_funding_at/last_monitor_at）、`PaperPosition`（paper_account_id/symbol/side/size/entry_price/leverage/cycle/opened_at）、`PaperOrder`（paper_account_id/order_no/symbol/side/order_type/exec_mode/trigger_price/size/entry_price/leverage/reduce_only/status/cycle/filled_at）、`PaperFundingRecord`（paper_account_id/symbol/funding_rate/position_notional/amount/cycle/settled_at）
- Produces: `AccountStrategyConfig.execution_mode`（String(10)，"real"|"paper"，默认 "real"）
- Produces: pytest fixtures `db_session`（SQLite 内存主库）、`snapshot_session_factory`（SQLite 内存快照库）、`paper_account`

- [ ] **Step 1: 写 conftest 与失败测试**

`backend/tests/__init__.py`：空文件。

`backend/tests/conftest.py`：

```python
"""Shared fixtures: in-memory SQLite for main and snapshot databases."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def db_session():
    from database.connection import Base
    from database.models import (  # noqa: F401 - register tables
        User, Account, AccountStrategyConfig, AIDecisionLog,
        PaperAccount, PaperPosition, PaperOrder, PaperFundingRecord,
    )
    engine = _memory_engine()
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__, Account.__table__, AccountStrategyConfig.__table__,
            AIDecisionLog.__table__,
            PaperAccount.__table__, PaperPosition.__table__,
            PaperOrder.__table__, PaperFundingRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def snapshot_session_factory():
    from database.snapshot_connection import SnapshotBase
    from database.snapshot_models import HyperliquidTrade, HyperliquidAccountSnapshot  # noqa: F401
    engine = _memory_engine()
    SnapshotBase.metadata.create_all(
        engine,
        tables=[HyperliquidTrade.__table__, HyperliquidAccountSnapshot.__table__],
    )
    return sessionmaker(bind=engine)


@pytest.fixture()
def paper_account(db_session):
    """A PaperAccount with $10,000 initial capital (account_id=1, hyperliquid data)."""
    from database.models import PaperAccount
    paper = PaperAccount(account_id=1, data_exchange="hyperliquid")
    db_session.add(paper)
    db_session.flush()
    return paper
```

`backend/tests/test_paper_models.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'PaperAccount'`

- [ ] **Step 3: 添加 ORM 模型与字段**

`backend/database/models.py` — 在 `AccountStrategyConfig` 的 `exchange` 列（第 291 行）之后加：

```python
    execution_mode = Column(String(10), nullable=False, default="real")  # "real" or "paper"
```

文件末尾追加（import 已有 `Boolean`/`DECIMAL`/`UniqueConstraint` 等，缺什么补什么）：

```python
# ============================================================================
# Paper Trading Tables (internal simulated execution, mainnet read-only data)
# ============================================================================

class PaperAccount(Base):
    """Per-trader paper trading account (persistent simulated equity)."""
    __tablename__ = "paper_accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True, index=True)
    data_exchange = Column(String(20), nullable=False, default="hyperliquid")  # market data source
    initial_capital = Column(DECIMAL(18, 2), nullable=False, default=10000.00)
    realized_pnl_total = Column(DECIMAL(18, 6), nullable=False, default=0)
    total_fees = Column(DECIMAL(18, 6), nullable=False, default=0)
    total_funding = Column(DECIMAL(18, 6), nullable=False, default=0)  # positive = received
    cycle = Column(Integer, nullable=False, default=1)
    cycle_started_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    # Fee/slippage overrides (NULL = exchange defaults in paper_trading/fees.py)
    taker_fee_pct = Column(DECIMAL(10, 6), nullable=True)
    maker_fee_pct = Column(DECIMAL(10, 6), nullable=True)
    slippage_fallback_pct = Column(DECIMAL(10, 6), nullable=True)
    last_funding_at = Column(TIMESTAMP, nullable=True)
    last_monitor_at = Column(TIMESTAMP, nullable=True)  # for restart kline catch-up
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    account = relationship("Account")


class PaperPosition(Base):
    """Open paper position (netted per symbol, like Hyperliquid)."""
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "long" | "short"
    size = Column(DECIMAL(18, 8), nullable=False)
    entry_price = Column(DECIMAL(18, 6), nullable=False)  # weighted average on add
    leverage = Column(Integer, nullable=False, default=1)
    cycle = Column(Integer, nullable=False, default=1)
    opened_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('paper_account_id', 'symbol', name='uq_paper_positions_account_symbol'),
    )


class PaperOrder(Base):
    """Pending paper order: resting GTC limit, or independent TP/SL trigger order."""
    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    order_no = Column(String(40), unique=True, nullable=False, index=True)  # "P-<hex16>"
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # "buy" | "sell"
    order_type = Column(String(20), nullable=False)  # "limit" | "take_profit" | "stop_loss"
    exec_mode = Column(String(10), nullable=False, default="limit")  # "limit" (maker) | "market" (taker+slippage)
    trigger_price = Column(DECIMAL(18, 6), nullable=False)
    size = Column(DECIMAL(18, 8), nullable=False)
    entry_price = Column(DECIMAL(18, 6), nullable=True)  # entry px for TP/SL PnL attribution
    leverage = Column(Integer, nullable=False, default=1)
    reduce_only = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | filled | cancelled
    cycle = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    filled_at = Column(TIMESTAMP, nullable=True)


class PaperFundingRecord(Base):
    """Funding settlement ledger for paper positions."""
    __tablename__ = "paper_funding_records"

    id = Column(Integer, primary_key=True, index=True)
    paper_account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    funding_rate = Column(DECIMAL(18, 10), nullable=False)
    position_notional = Column(DECIMAL(18, 6), nullable=False)
    amount = Column(DECIMAL(18, 6), nullable=False)  # positive = received by account
    cycle = Column(Integer, nullable=False, default=1)
    settled_at = Column(TIMESTAMP, server_default=func.current_timestamp())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 写迁移脚本并注册**

`backend/database/migrations/add_paper_trading_tables.py`：

```python
"""
Migration: Paper trading tables + execution_mode on account_strategy_configs.

Creates: paper_accounts, paper_positions, paper_orders, paper_funding_records.
Adds: account_strategy_configs.execution_mode ('real' | 'paper', default 'real').
Idempotent: create_all(checkfirst) + information_schema column check.
"""
import logging
from sqlalchemy import text
from database.connection import engine, Base

logger = logging.getLogger(__name__)


def upgrade():
    from database.models import (  # noqa: F401 - ensure tables registered on Base
        PaperAccount, PaperPosition, PaperOrder, PaperFundingRecord,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            PaperAccount.__table__,
            PaperPosition.__table__,
            PaperOrder.__table__,
            PaperFundingRecord.__table__,
        ],
        checkfirst=True,
    )
    logger.info("✅ Paper trading tables ensured")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'account_strategy_configs'
                AND column_name = 'execution_mode'
            )
        """))
        if result.scalar():
            logger.info("⏭️  Column execution_mode already exists, skipping")
        else:
            conn.execute(text("""
                ALTER TABLE account_strategy_configs
                ADD COLUMN execution_mode VARCHAR(10) NOT NULL DEFAULT 'real'
            """))
            logger.info("✅ Added execution_mode to account_strategy_configs")
        conn.commit()
```

`backend/database/migration_manager.py` — MIGRATIONS 列表末尾（`"add_news_image_url.py",` 之后）追加：

```python
    "add_paper_trading_tables.py",
```

- [ ] **Step 6: 验证迁移可导入**

Run: `cd backend; uv run python -c "from database.migrations.add_paper_trading_tables import upgrade; print('ok')"`
Expected: 输出 `ok`（不实际连库执行；真实执行在应用启动时自动跑）

- [ ] **Step 7: Commit**

```bash
git add backend/database/models.py backend/database/migrations/add_paper_trading_tables.py backend/database/migration_manager.py backend/tests/
git commit -m "Add paper trading tables and execution_mode migration"
```

---

### Task 2: 费率与 funding 模块 `paper_trading/fees.py`

**Files:**
- Create: `backend/paper_trading/__init__.py`（空文件）
- Create: `backend/paper_trading/fees.py`
- Test: `backend/tests/test_paper_fees.py`

**Interfaces:**
- Produces: `DEFAULT_FEES: dict`、`FUNDING_INTERVAL_HOURS: dict`
- Produces: `get_fee_rates(data_exchange: str, paper_account=None) -> Dict[str, float]`（返回 `{"taker": pct, "maker": pct}`，pct 为百分数）
- Produces: `calc_fee(notional: float, rate_pct: float) -> float`
- Produces: `fetch_funding_rate(data_exchange: str, symbol: str) -> Optional[float]`（小数费率，如 0.0000125；失败返回 None）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_fees.py`：

```python
"""Fee schedule and funding rate tests."""


def test_default_fee_rates():
    from paper_trading.fees import get_fee_rates
    hl = get_fee_rates("hyperliquid")
    assert hl == {"taker": 0.045, "maker": 0.015}
    bn = get_fee_rates("binance")
    assert bn == {"taker": 0.05, "maker": 0.02}


def test_fee_rates_account_override(db_session, paper_account):
    from paper_trading.fees import get_fee_rates
    paper_account.taker_fee_pct = 0.03
    rates = get_fee_rates("hyperliquid", paper_account)
    assert rates["taker"] == 0.03
    assert rates["maker"] == 0.015  # not overridden


def test_calc_fee():
    from paper_trading.fees import calc_fee
    assert calc_fee(10000.0, 0.045) == 4.5
    assert calc_fee(-10000.0, 0.045) == 4.5  # absolute notional


def test_fetch_funding_rate_hyperliquid(monkeypatch):
    from paper_trading import fees
    monkeypatch.setattr(
        fees, "_hyperliquid_ticker",
        lambda symbol: {"price": 100.0, "funding_rate": 0.0000125},
    )
    assert fees.fetch_funding_rate("hyperliquid", "BTC") == 0.0000125


def test_fetch_funding_rate_failure_returns_none(monkeypatch):
    from paper_trading import fees
    def boom(symbol):
        raise RuntimeError("network down")
    monkeypatch.setattr(fees, "_hyperliquid_ticker", boom)
    assert fees.fetch_funding_rate("hyperliquid", "BTC") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_fees.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paper_trading'`

- [ ] **Step 3: 实现 fees.py**

`backend/paper_trading/__init__.py`：空文件。

`backend/paper_trading/fees.py`：

```python
"""Fee schedule and funding rates for paper trading (mainnet public data)."""
import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Percent rates (0.045 = 0.045%)
DEFAULT_FEES: Dict[str, Dict[str, float]] = {
    "hyperliquid": {"taker": 0.045, "maker": 0.015},
    "binance": {"taker": 0.05, "maker": 0.02},
}

FUNDING_INTERVAL_HOURS: Dict[str, int] = {"hyperliquid": 1, "binance": 8}

DEFAULT_SLIPPAGE_FALLBACK_PCT = 0.05


def get_fee_rates(data_exchange: str, paper_account=None) -> Dict[str, float]:
    rates = dict(DEFAULT_FEES.get(data_exchange, DEFAULT_FEES["hyperliquid"]))
    if paper_account is not None:
        if paper_account.taker_fee_pct is not None:
            rates["taker"] = float(paper_account.taker_fee_pct)
        if paper_account.maker_fee_pct is not None:
            rates["maker"] = float(paper_account.maker_fee_pct)
    return rates


def calc_fee(notional: float, rate_pct: float) -> float:
    return abs(notional) * rate_pct / 100.0


def _hyperliquid_ticker(symbol: str) -> Optional[dict]:
    from services.hyperliquid_market_data import get_ticker_data_from_hyperliquid
    return get_ticker_data_from_hyperliquid(symbol, environment="mainnet")


def _binance_funding(symbol: str) -> Optional[float]:
    from services.exchanges.symbol_mapper import SymbolMapper
    exchange_symbol = SymbolMapper.to_exchange(symbol, "binance")
    resp = requests.get(
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        params={"symbol": exchange_symbol},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return float(data["lastFundingRate"])


def fetch_funding_rate(data_exchange: str, symbol: str) -> Optional[float]:
    """Current funding rate as a decimal (e.g. 0.0000125). None on failure."""
    try:
        if data_exchange == "binance":
            return _binance_funding(symbol)
        ticker = _hyperliquid_ticker(symbol)
        if ticker and ticker.get("funding_rate") is not None:
            return float(ticker["funding_rate"])
        return None
    except Exception as e:
        logger.warning(f"[PAPER] Failed to fetch funding rate for {symbol} ({data_exchange}): {e}")
        return None
```

注意：`SymbolMapper.to_exchange` 的确切方法名在 `backend/services/exchanges/symbol_mapper.py` 中核实（若为 `to_exchange(symbol, exchange)` 之外的签名则按实际调整，保持"内部符号→币安合约符号（如 BTC→BTCUSDT）"的语义）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_fees.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/ backend/tests/test_paper_fees.py
git commit -m "Add paper trading fee schedule and funding rate module"
```

---

### Task 3: 滑点模块 `paper_trading/slippage.py`（订单簿逐档撮合）

**Files:**
- Create: `backend/paper_trading/slippage.py`
- Test: `backend/tests/test_paper_slippage.py`

**Interfaces:**
- Consumes: `fees.DEFAULT_SLIPPAGE_FALLBACK_PCT`
- Produces: `fetch_orderbook(data_exchange: str, symbol: str, depth: int = 50) -> Optional[Dict[str, list]]`（`{"bids": [(px, sz), ...], "asks": [(px, sz), ...]}`，价格降序 bids / 升序 asks；失败返回 None）
- Produces: `walk_the_book(levels: list, size: float, fallback_pct: float, side: str) -> Optional[float]`（逐档吃单加权均价；levels 为空返回 None；深度不足部分按最差档价 ± fallback，方向由显式 side "buy"/"sell" 决定——执行期修订：原 3 参签名无法从 levels 推断方向，单档订单簿会反转卖单滑点方向，Task 3 审查发现后改为显式传向。后续任务只调用 compute_fill_price，不受影响）
- Produces: `compute_fill_price(data_exchange, symbol, side: str, size: float, reference_price: float, fallback_pct: float) -> Tuple[float, str]`（返回 `(成交价, "orderbook"|"fallback")`）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_slippage.py`：

```python
"""Orderbook walk and slippage fallback tests."""
import pytest


def test_walk_the_book_single_level():
    from paper_trading.slippage import walk_the_book
    # 10 BTC available at 100, buying 5 -> avg 100
    assert walk_the_book([(100.0, 10.0)], 5.0, 0.05) == 100.0


def test_walk_the_book_multi_level_weighted_avg():
    from paper_trading.slippage import walk_the_book
    # buy 15: 10 @ 100 + 5 @ 101 -> (1000 + 505) / 15
    avg = walk_the_book([(100.0, 10.0), (101.0, 5.0)], 15.0, 0.05)
    assert avg == pytest.approx((100.0 * 10 + 101.0 * 5) / 15)


def test_walk_the_book_insufficient_depth():
    from paper_trading.slippage import walk_the_book
    # buy 20, only 10 available at 100: remainder at 100 * (1 + 0.05%)
    avg = walk_the_book([(100.0, 10.0)], 20.0, 0.05)
    expected = (100.0 * 10 + 100.0 * 1.0005 * 10) / 20
    assert avg == pytest.approx(expected)


def test_walk_the_book_empty():
    from paper_trading.slippage import walk_the_book
    assert walk_the_book([], 5.0, 0.05) is None


def test_compute_fill_price_uses_orderbook(monkeypatch):
    from paper_trading import slippage
    monkeypatch.setattr(
        slippage, "fetch_orderbook",
        lambda ex, sym, depth=50: {
            "bids": [(99.0, 100.0)],
            "asks": [(101.0, 100.0)],
        },
    )
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "buy", 1.0, 100.0, 0.05)
    assert source == "orderbook"
    assert price == 101.0  # buy fills against asks
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "sell", 1.0, 100.0, 0.05)
    assert price == 99.0  # sell fills against bids


def test_compute_fill_price_fallback(monkeypatch):
    from paper_trading import slippage
    monkeypatch.setattr(slippage, "fetch_orderbook", lambda ex, sym, depth=50: None)
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "buy", 1.0, 100.0, 0.05)
    assert source == "fallback"
    assert price == pytest.approx(100.0 * 1.0005)
    price, _ = slippage.compute_fill_price("hyperliquid", "BTC", "sell", 1.0, 100.0, 0.05)
    assert price == pytest.approx(100.0 * 0.9995)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_slippage.py -v`
Expected: FAIL — `ModuleNotFoundError` 或 `ImportError`

- [ ] **Step 3: 实现 slippage.py**

`backend/paper_trading/slippage.py`：

```python
"""Orderbook-walk fill pricing with fixed-percent fallback (mainnet public APIs)."""
import logging
from typing import Dict, List, Optional, Tuple

import requests

from paper_trading.fees import DEFAULT_SLIPPAGE_FALLBACK_PCT  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"


def fetch_orderbook(data_exchange: str, symbol: str, depth: int = 50) -> Optional[Dict[str, list]]:
    """Fetch mainnet L2 orderbook. Returns {"bids": [(px, sz)...], "asks": [(px, sz)...]} or None."""
    try:
        if data_exchange == "binance":
            from services.exchanges.symbol_mapper import SymbolMapper
            exchange_symbol = SymbolMapper.to_exchange(symbol, "binance")
            resp = requests.get(
                BINANCE_DEPTH_URL,
                params={"symbol": exchange_symbol, "limit": min(depth, 100)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            bids = [(float(px), float(sz)) for px, sz in data.get("bids", [])]
            asks = [(float(px), float(sz)) for px, sz in data.get("asks", [])]
        else:
            from services.exchanges.symbol_mapper import SymbolMapper
            coin = SymbolMapper.to_exchange(symbol, "hyperliquid")
            resp = requests.post(
                HYPERLIQUID_INFO_URL,
                json={"type": "l2Book", "coin": coin},
                timeout=10,
            )
            resp.raise_for_status()
            levels = resp.json().get("levels", [[], []])
            bids = [(float(l["px"]), float(l["sz"])) for l in levels[0]]
            asks = [(float(l["px"]), float(l["sz"])) for l in levels[1]]
        if not bids and not asks:
            return None
        return {"bids": bids, "asks": asks}
    except Exception as e:
        logger.warning(f"[PAPER] Orderbook fetch failed for {symbol} ({data_exchange}): {e}")
        return None


def walk_the_book(levels: List[Tuple[float, float]], size: float, fallback_pct: float) -> Optional[float]:
    """Weighted-average fill price walking price levels; leftover priced at worst level +/- fallback."""
    if not levels or size <= 0:
        return None
    remaining = size
    cost = 0.0
    worst_px = levels[0][0]
    for px, sz in levels:
        take = min(remaining, sz)
        cost += take * px
        remaining -= take
        worst_px = px
        if remaining <= 1e-12:
            break
    if remaining > 1e-12:
        # levels are ordered from best to worst; direction inferred from ordering
        is_ask_side = len(levels) < 2 or levels[-1][0] >= levels[0][0]
        adj = 1 + fallback_pct / 100 if is_ask_side else 1 - fallback_pct / 100
        cost += remaining * worst_px * adj
    return cost / size


def compute_fill_price(
    data_exchange: str, symbol: str, side: str, size: float,
    reference_price: float, fallback_pct: float,
) -> Tuple[float, str]:
    """Fill price via book walk; falls back to reference_price +/- fallback_pct."""
    book = fetch_orderbook(data_exchange, symbol)
    if book:
        levels = book["asks"] if side == "buy" else book["bids"]
        avg = walk_the_book(levels, size, fallback_pct)
        if avg is not None:
            return avg, "orderbook"
    if side == "buy":
        return reference_price * (1 + fallback_pct / 100), "fallback"
    return reference_price * (1 - fallback_pct / 100), "fallback"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_slippage.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/slippage.py backend/tests/test_paper_slippage.py
git commit -m "Add orderbook-walk slippage module for paper trading"
```

---

### Task 4: 撮合引擎（一）：账户状态、开仓、加仓、保证金拒单

**Files:**
- Create: `backend/paper_trading/engine.py`
- Test: `backend/tests/test_paper_engine_open.py`

**Interfaces:**
- Consumes: Task 1 模型、Task 2 `get_fee_rates/calc_fee`、Task 3 `compute_fill_price`
- Produces: `PaperEngine(db, snapshot_session_factory=None)` 类，本任务实现：
  - `get_or_create(account_id: int, data_exchange: str) -> PaperAccount`（行锁）
  - `positions(paper) -> List[PaperPosition]`、`pending_orders(paper, symbol=None) -> List[PaperOrder]`
  - `used_margin(paper) -> float`、`unrealized_pnl(paper, prices: Dict[str, float]) -> float`
  - `compute_state(paper, prices) -> Dict`（键与真实 client `get_account_state` 相同：environment/account_id/total_equity/available_balance/used_margin/maintenance_margin/margin_usage_percent/withdrawal_available/wallet_address/account_mode/timestamp）
  - `place_order(paper, symbol, is_buy, size, limit_price, market_price, leverage=1, time_in_force="Ioc", reduce_only=False, take_profit_price=None, stop_loss_price=None, tp_execution="limit", sl_execution="limit", mark_prices=None) -> Dict`（返回结构与真实 client `place_order_with_tpsl` 相同 + 额外 `fee`/`realized_pnl` 键；status: "filled"|"resting"|"error"。执行期修订：新增可选 `mark_prices` 参数——保证金校验必须计入其他持仓的实时未实现盈亏（规格权益公式要求），调用方（Task 7 client、Task 11 monitor）应传入全部持仓标记价）
  - 内部：`_fill(...)`、`_close_qty(...)`、`_register_tpsl(...)`、`_record_fill(...)`、`_new_order_no()`
- 常量：`MAINTENANCE_MARGIN_RATIO = 0.5`

**测试中一律 monkeypatch `paper_trading.slippage.compute_fill_price` 返回固定价（不触网）。**

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_engine_open.py`：

```python
"""PaperEngine: state computation, open, add-to-position, margin rejection."""
import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    # deterministic fill: exact reference price, source orderbook
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def test_initial_state(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == 10000.00
    assert state["available_balance"] == 10000.00
    assert state["used_margin"] == 0
    assert state["environment"] == "paper"
    assert state["wallet_address"] == "paper-1"


def test_open_long_position(engine, db_session):
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(
        paper, "BTC", is_buy=True, size=0.1, limit_price=100000.0,
        market_price=100000.0, leverage=2,
    )
    assert result["status"] == "filled"
    assert result["average_price"] == 100000.0
    assert result["filled_amount"] == 0.1
    assert result["order_id"].startswith("P-")
    # taker fee: 0.1 * 100000 * 0.045% = 4.5
    assert result["fee"] == pytest.approx(4.5)

    positions = engine.positions(paper)
    assert len(positions) == 1
    assert positions[0].side == "long"
    assert float(positions[0].size) == 0.1
    # margin = 10000 / 2 = 5000
    state = engine.compute_state(paper, {"BTC": 100000.0})
    assert state["used_margin"] == pytest.approx(5000.0)
    assert state["total_equity"] == pytest.approx(10000.0 - 4.5)


def test_add_to_position_weighted_average(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    engine.place_order(paper, "BTC", True, 0.1, 110000.0, 110000.0, leverage=2)
    pos = engine.positions(paper)[0]
    assert float(pos.size) == pytest.approx(0.2)
    assert float(pos.entry_price) == pytest.approx(105000.0)


def test_margin_rejection(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # margin needed: 1 BTC * 100000 / 1x = 100000 > 10000 equity
    result = engine.place_order(paper, "BTC", True, 1.0, 100000.0, 100000.0, leverage=1)
    assert result["status"] == "error"
    assert "Insufficient" in result["error"]
    assert engine.positions(paper) == []


def test_tpsl_orders_registered(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0, stop_loss_price=95000.0, sl_execution="market",
    )
    assert result["tp_order_id"].startswith("P-")
    assert result["sl_order_id"].startswith("P-")
    orders = engine.pending_orders(paper)
    assert len(orders) == 2
    tp = next(o for o in orders if o.order_type == "take_profit")
    sl = next(o for o in orders if o.order_type == "stop_loss")
    assert float(tp.trigger_price) == 110000.0
    assert tp.exec_mode == "limit"
    assert sl.exec_mode == "market"
    assert tp.side == "sell" and sl.side == "sell"
    assert float(tp.entry_price) == 100000.0


def test_fill_recorded_to_snapshot_db(engine, snapshot_session_factory):
    from database.snapshot_models import HyperliquidTrade
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    sdb = snapshot_session_factory()
    trades = sdb.query(HyperliquidTrade).all()
    assert len(trades) == 1
    assert trades[0].environment == "paper"
    assert trades[0].order_id == result["order_id"]
    assert float(trades[0].fee) == pytest.approx(4.5)
    sdb.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_engine_open.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paper_trading.engine'`

- [ ] **Step 3: 实现 engine.py（本任务范围）**

`backend/paper_trading/engine.py`：

```python
"""Paper trading engine: persistent matching and accounting.

Equity model (matches backtest VirtualAccount and Hyperliquid Account Value):
equity = initial_capital + realized_pnl_total + unrealized_pnl - total_fees + total_funding
"""
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models import PaperAccount, PaperPosition, PaperOrder, PaperFundingRecord
from paper_trading import fees as fee_mod
from paper_trading import slippage as slip_mod

logger = logging.getLogger(__name__)

MAINTENANCE_MARGIN_RATIO = 0.5  # maintenance = used_margin * 0.5 (matches real client estimate)
EPS = 1e-12


def _new_order_no() -> str:
    return "P-" + uuid.uuid4().hex[:16]


class PaperEngine:
    def __init__(self, db: Session, snapshot_session_factory=None):
        self.db = db
        if snapshot_session_factory is None:
            from database.snapshot_connection import SnapshotSessionLocal
            snapshot_session_factory = SnapshotSessionLocal
        self._snapshot_factory = snapshot_session_factory

    # ---------- account / queries ----------

    def get_or_create(self, account_id: int, data_exchange: str) -> PaperAccount:
        paper = (
            self.db.query(PaperAccount)
            .filter(PaperAccount.account_id == account_id)
            .with_for_update()
            .first()
        )
        if paper is None:
            paper = PaperAccount(account_id=account_id, data_exchange=data_exchange)
            self.db.add(paper)
            self.db.flush()
        elif paper.data_exchange != data_exchange:
            paper.data_exchange = data_exchange
            self.db.flush()
        return paper

    def positions(self, paper: PaperAccount) -> List[PaperPosition]:
        return (
            self.db.query(PaperPosition)
            .filter(PaperPosition.paper_account_id == paper.id)
            .all()
        )

    def pending_orders(self, paper: PaperAccount, symbol: Optional[str] = None) -> List[PaperOrder]:
        q = self.db.query(PaperOrder).filter(
            PaperOrder.paper_account_id == paper.id,
            PaperOrder.status == "pending",
        )
        if symbol:
            q = q.filter(PaperOrder.symbol == symbol)
        return q.all()

    def used_margin(self, paper: PaperAccount) -> float:
        total = 0.0
        for pos in self.positions(paper):
            total += float(pos.size) * float(pos.entry_price) / max(int(pos.leverage), 1)
        return total

    def unrealized_pnl(self, paper: PaperAccount, prices: Dict[str, float]) -> float:
        total = 0.0
        for pos in self.positions(paper):
            px = prices.get(pos.symbol)
            if not px:
                continue
            if pos.side == "long":
                total += (px - float(pos.entry_price)) * float(pos.size)
            else:
                total += (float(pos.entry_price) - px) * float(pos.size)
        return total

    def compute_state(self, paper: PaperAccount, prices: Dict[str, float]) -> Dict[str, Any]:
        equity = (
            float(paper.initial_capital)
            + float(paper.realized_pnl_total)
            + self.unrealized_pnl(paper, prices)
            - float(paper.total_fees)
            + float(paper.total_funding)
        )
        used = self.used_margin(paper)
        available = max(equity - used, 0.0)
        return {
            "environment": "paper",
            "account_id": paper.account_id,
            "total_equity": round(equity, 2),
            "available_balance": round(available, 2),
            "used_margin": round(used, 2),
            "maintenance_margin": round(used * MAINTENANCE_MARGIN_RATIO, 2),
            "margin_usage_percent": round(used / equity * 100, 2) if equity > 0 else 0,
            "withdrawal_available": round(available, 2),
            "wallet_address": f"paper-{paper.account_id}",
            "account_mode": "paper",
            "timestamp": int(time.time() * 1000),
        }

    # ---------- order placement ----------

    def place_order(
        self,
        paper: PaperAccount,
        symbol: str,
        is_buy: bool,
        size: float,
        limit_price: float,
        market_price: float,
        leverage: int = 1,
        time_in_force: str = "Ioc",
        reduce_only: bool = False,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        tp_execution: str = "limit",
        sl_execution: str = "limit",
    ) -> Dict[str, Any]:
        side = "buy" if is_buy else "sell"
        rates = fee_mod.get_fee_rates(paper.data_exchange, paper)
        fallback = (
            float(paper.slippage_fallback_pct)
            if paper.slippage_fallback_pct is not None
            else fee_mod.DEFAULT_SLIPPAGE_FALLBACK_PCT
        )

        fill_price, source = slip_mod.compute_fill_price(
            paper.data_exchange, symbol, side, size, market_price, fallback
        )
        marketable = (is_buy and fill_price <= limit_price) or (
            (not is_buy) and fill_price >= limit_price
        )

        if time_in_force == "Ioc" and not marketable:
            # mirror real error text so pipeline IOC->GTC fallback works
            return self._error(symbol, "Order could not immediately match against any resting orders")

        if not marketable:  # Gtc / Alo resting
            order = PaperOrder(
                paper_account_id=paper.id, order_no=_new_order_no(), symbol=symbol,
                side=side, order_type="limit", exec_mode="limit",
                trigger_price=limit_price, size=size, leverage=leverage,
                reduce_only=reduce_only, status="pending", cycle=paper.cycle,
            )
            self.db.add(order)
            self.db.flush()
            result = self._result(paper, symbol, is_buy, size, leverage, order.order_no,
                                  filled_amount=0.0, average_price=0.0, status="resting")
            result.update(self._register_tpsl(
                paper, symbol, is_buy, size, limit_price,
                take_profit_price, stop_loss_price, tp_execution, sl_execution,
            ))
            return result

        fill = self._fill(paper, symbol, side, size, leverage, reduce_only, fill_price, rates["taker"])
        if fill["status"] == "error":
            return self._error(symbol, fill["error"])

        result = self._result(
            paper, symbol, is_buy, size, leverage, fill["order_no"],
            filled_amount=fill["filled_qty"], average_price=fill["avg_price"],
            status="filled", fee=fill["fee"], realized_pnl=fill["realized_pnl"],
        )
        result.update(self._register_tpsl(
            paper, symbol, is_buy, fill["filled_qty"], fill["avg_price"],
            take_profit_price, stop_loss_price, tp_execution, sl_execution,
        ))
        return result

    # ---------- internals ----------

    def _fill(
        self, paper: PaperAccount, symbol: str, side: str, size: float,
        leverage: int, reduce_only: bool, fill_price: float, fee_rate_pct: float,
    ) -> Dict[str, Any]:
        pos = (
            self.db.query(PaperPosition)
            .filter(PaperPosition.paper_account_id == paper.id, PaperPosition.symbol == symbol)
            .first()
        )
        order_no = _new_order_no()
        opening_side = "long" if side == "buy" else "short"
        realized = 0.0
        total_fee = 0.0
        filled_qty = 0.0
        remaining = float(size)

        # 1) netting: opposite-side position closes first
        if pos and pos.side != opening_side:
            close_qty = min(float(pos.size), remaining)
            pnl, fee = self._close_qty(paper, pos, close_qty, fill_price, fee_rate_pct, order_no)
            realized += pnl
            total_fee += fee
            filled_qty += close_qty
            remaining -= close_qty
        elif reduce_only and (pos is None or pos.side == opening_side):
            return {"status": "error", "error": f"No opposite position to reduce for {symbol}"}

        if reduce_only:
            remaining = 0.0

        # 2) open new / add to same-side position
        if remaining > EPS:
            notional = remaining * fill_price
            margin_needed = notional / max(leverage, 1)
            state = self.compute_state(paper, {symbol: fill_price})
            if state["available_balance"] < margin_needed:
                if filled_qty <= EPS:
                    return {
                        "status": "error",
                        "error": (
                            f"Insufficient available balance: need ${margin_needed:.2f}, "
                            f"have ${state['available_balance']:.2f}"
                        ),
                    }
                remaining = 0.0  # netting part already filled; skip the new open
            else:
                fee = fee_mod.calc_fee(notional, fee_rate_pct)
                paper.total_fees = float(paper.total_fees) + fee
                total_fee += fee
                self._record_fill(paper, symbol, side, remaining, fill_price, leverage, order_no, fee)
                pos = (
                    self.db.query(PaperPosition)
                    .filter(PaperPosition.paper_account_id == paper.id, PaperPosition.symbol == symbol)
                    .first()
                )
                if pos and pos.side == opening_side:
                    old_size = float(pos.size)
                    new_size = old_size + remaining
                    pos.entry_price = (float(pos.entry_price) * old_size + fill_price * remaining) / new_size
                    pos.size = new_size
                    pos.leverage = leverage
                else:
                    self.db.add(PaperPosition(
                        paper_account_id=paper.id, symbol=symbol, side=opening_side,
                        size=remaining, entry_price=fill_price, leverage=leverage,
                        cycle=paper.cycle, opened_at=datetime.utcnow(),
                    ))
                filled_qty += remaining

        self.db.flush()
        return {
            "status": "filled", "order_no": order_no, "avg_price": fill_price,
            "filled_qty": filled_qty, "fee": total_fee, "realized_pnl": realized,
        }

    def _close_qty(
        self, paper: PaperAccount, pos: PaperPosition, qty: float,
        exit_price: float, fee_rate_pct: float, order_no: str,
    ) -> tuple:
        """Close qty of pos at exit_price. Returns (gross_pnl, fee). Deletes position when emptied."""
        qty = min(qty, float(pos.size))
        entry = float(pos.entry_price)
        pnl = (exit_price - entry) * qty if pos.side == "long" else (entry - exit_price) * qty
        fee = fee_mod.calc_fee(qty * exit_price, fee_rate_pct)
        paper.realized_pnl_total = float(paper.realized_pnl_total) + pnl
        paper.total_fees = float(paper.total_fees) + fee
        close_side = "sell" if pos.side == "long" else "buy"
        self._record_fill(paper, pos.symbol, close_side, qty, exit_price, int(pos.leverage), order_no, fee)
        new_size = float(pos.size) - qty
        if new_size <= EPS:
            self.db.delete(pos)
        else:
            pos.size = new_size
        self.db.flush()
        return pnl, fee

    def _register_tpsl(
        self, paper: PaperAccount, symbol: str, is_buy: bool, size: float, entry_price: float,
        take_profit_price: Optional[float], stop_loss_price: Optional[float],
        tp_execution: str = "limit", sl_execution: str = "limit",
    ) -> Dict[str, Any]:
        close_side = "sell" if is_buy else "buy"
        out: Dict[str, Any] = {
            "tp_order_id": None, "tp_trigger_price": take_profit_price,
            "sl_order_id": None, "sl_trigger_price": stop_loss_price,
        }
        if take_profit_price:
            tp = PaperOrder(
                paper_account_id=paper.id, order_no=_new_order_no(), symbol=symbol,
                side=close_side, order_type="take_profit", exec_mode=tp_execution,
                trigger_price=take_profit_price, size=size, entry_price=entry_price,
                reduce_only=True, status="pending", cycle=paper.cycle,
            )
            self.db.add(tp)
            out["tp_order_id"] = tp.order_no
        if stop_loss_price:
            sl = PaperOrder(
                paper_account_id=paper.id, order_no=_new_order_no(), symbol=symbol,
                side=close_side, order_type="stop_loss", exec_mode=sl_execution,
                trigger_price=stop_loss_price, size=size, entry_price=entry_price,
                reduce_only=True, status="pending", cycle=paper.cycle,
            )
            self.db.add(sl)
            out["sl_order_id"] = sl.order_no
        self.db.flush()
        return out

    def _record_fill(
        self, paper: PaperAccount, symbol: str, side: str, qty: float,
        price: float, leverage: int, order_no: str, fee: float,
    ) -> None:
        """Write fill to snapshot DB HyperliquidTrade with environment='paper'."""
        try:
            from decimal import Decimal
            from database.snapshot_models import HyperliquidTrade
            sdb = self._snapshot_factory()
            try:
                sdb.add(HyperliquidTrade(
                    account_id=paper.account_id,
                    environment="paper",
                    wallet_address=f"paper-{paper.account_id}",
                    symbol=symbol,
                    side=side,
                    quantity=Decimal(str(qty)),
                    price=Decimal(str(price)),
                    leverage=leverage,
                    order_id=order_no,
                    order_status="filled",
                    trade_value=Decimal(str(qty)) * Decimal(str(price)),
                    fee=Decimal(str(fee)),
                ))
                sdb.commit()
            finally:
                sdb.close()
        except Exception as e:
            logger.warning(f"[PAPER] Failed to record fill: {e}")

    def _result(
        self, paper: PaperAccount, symbol: str, is_buy: bool, size: float, leverage: int,
        order_no: str, filled_amount: float, average_price: float, status: str,
        fee: float = 0.0, realized_pnl: float = 0.0,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "environment": "paper",
            "symbol": symbol,
            "is_buy": is_buy,
            "size": size,
            "leverage": leverage,
            "order_id": order_no,
            "filled_amount": filled_amount,
            "average_price": average_price,
            "wallet_address": f"paper-{paper.account_id}",
            "timestamp": int(time.time() * 1000),
            "tp_order_id": None,
            "tp_trigger_price": None,
            "sl_order_id": None,
            "sl_trigger_price": None,
            "fee": fee,
            "realized_pnl": realized_pnl,
        }

    def _error(self, symbol: str, message: str) -> Dict[str, Any]:
        return {"status": "error", "error": message, "environment": "paper", "symbol": symbol}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_engine_open.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/engine.py backend/tests/test_paper_engine_open.py
git commit -m "Add paper trading engine: state, open, add, margin checks"
```

---

### Task 5: 撮合引擎（二）：平仓/反向净额/挂单撮合/撤单

**Files:**
- Modify: `backend/paper_trading/engine.py`（追加方法）
- Test: `backend/tests/test_paper_engine_close.py`

**Interfaces:**
- Produces（追加到 PaperEngine）：
  - `cancel_order(paper, order_no: str) -> bool`
  - `open_orders_as_client_format(paper, symbol=None) -> List[Dict]`（键：order_id/symbol/side/order_type/trigger_price/size/reduce_only/created_at）
  - `trigger_order(paper, order: PaperOrder, mark_price: float) -> Optional[Dict]`（监控服务调用；触发则返回 `{"order_no", "symbol", "qty", "price", "fee", "realized_pnl", "exit_reason"}`，未触发返回 None）
  - `positions_as_client_format(paper, prices) -> List[Dict]`（键与真实 client `get_positions` 相同：coin/szi/entry_px/position_value/unrealized_pnl/margin_used/liquidation_px/leverage/side）
- 语义：reduce_only 单走净额平仓；反向开仓先平后开；TP limit 按触发价 maker 费率成交、SL/market 按触发价 ± 回退滑点 taker 费率成交；position 消失时 TP/SL 挂单自动取消

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_engine_close.py`：

```python
"""PaperEngine: close, reverse-netting, pending order triggers, cancel."""
import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def _open_long(engine, paper, size=0.1, price=100000.0, leverage=2, **kw):
    return engine.place_order(paper, "BTC", True, size, price, price, leverage=leverage, **kw)


def test_reduce_only_close_realizes_pnl(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper)
    # close at 110000: pnl = (110000-100000)*0.1 = 1000
    result = engine.place_order(paper, "BTC", False, 0.1, 110000.0, 110000.0, reduce_only=True)
    assert result["status"] == "filled"
    assert result["realized_pnl"] == pytest.approx(1000.0)
    assert engine.positions(paper) == []
    state = engine.compute_state(paper, {})
    # fees: open 4.5 + close 0.1*110000*0.045% = 4.95
    assert state["total_equity"] == pytest.approx(10000 + 1000 - 4.5 - 4.95)


def test_partial_close(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, size=0.2)
    result = engine.place_order(paper, "BTC", False, 0.1, 110000.0, 110000.0, reduce_only=True)
    assert result["realized_pnl"] == pytest.approx(1000.0)
    pos = engine.positions(paper)[0]
    assert float(pos.size) == pytest.approx(0.1)


def test_reverse_position_nets_then_opens(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, size=0.1)
    # sell 0.3 at 110000: closes 0.1 long (pnl 1000), opens 0.2 short
    result = engine.place_order(paper, "BTC", False, 0.3, 110000.0, 110000.0, leverage=2)
    assert result["status"] == "filled"
    assert result["realized_pnl"] == pytest.approx(1000.0)
    pos = engine.positions(paper)[0]
    assert pos.side == "short"
    assert float(pos.size) == pytest.approx(0.2)
    assert float(pos.entry_price) == pytest.approx(110000.0)


def test_gtc_resting_then_trigger(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # buy limit 90000 while market at 100000 -> resting
    result = engine.place_order(
        paper, "BTC", True, 0.1, 90000.0, 100000.0, leverage=2, time_in_force="Gtc",
    )
    assert result["status"] == "resting"
    order = engine.pending_orders(paper)[0]
    # price hasn't crossed: no trigger
    assert engine.trigger_order(paper, order, 95000.0) is None
    # price crossed: fills at limit price with maker fee (0.1*90000*0.015% = 1.35)
    fill = engine.trigger_order(paper, order, 89999.0)
    assert fill is not None
    assert fill["price"] == pytest.approx(90000.0)
    assert fill["fee"] == pytest.approx(1.35)
    assert order.status == "filled"
    assert engine.positions(paper)[0].side == "long"


def test_tp_trigger_limit_exec(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    tp = next(o for o in engine.pending_orders(paper) if o.order_type == "take_profit")
    assert engine.trigger_order(paper, tp, 109000.0) is None
    fill = engine.trigger_order(paper, tp, 110500.0)
    assert fill["exit_reason"] == "tp"
    assert fill["price"] == pytest.approx(110000.0)  # limit exec at trigger
    assert fill["realized_pnl"] == pytest.approx(1000.0)
    assert engine.positions(paper) == []


def test_sl_trigger_market_exec_with_slippage(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, stop_loss_price=95000.0, sl_execution="market")
    sl = next(o for o in engine.pending_orders(paper) if o.order_type == "stop_loss")
    fill = engine.trigger_order(paper, sl, 94900.0)
    assert fill["exit_reason"] == "sl"
    # market exec: trigger price minus fallback slippage (sell side)
    assert fill["price"] == pytest.approx(95000.0 * (1 - 0.05 / 100))
    assert engine.positions(paper) == []


def test_orphan_tpsl_cancelled_when_no_position(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    engine.place_order(paper, "BTC", False, 0.1, 100000.0, 100000.0, reduce_only=True)
    tp = next(o for o in engine.pending_orders(paper) if o.order_type == "take_profit")
    assert engine.trigger_order(paper, tp, 111000.0) is None
    assert tp.status == "cancelled"


def test_cancel_order(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    tp = engine.pending_orders(paper)[0]
    assert engine.cancel_order(paper, tp.order_no) is True
    assert engine.pending_orders(paper) == []
    assert engine.cancel_order(paper, "P-nonexistent") is False


def test_positions_client_format(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper)
    out = engine.positions_as_client_format(paper, {"BTC": 105000.0})
    assert out[0]["coin"] == "BTC"
    assert out[0]["szi"] == pytest.approx(0.1)
    assert out[0]["entry_px"] == pytest.approx(100000.0)
    assert out[0]["unrealized_pnl"] == pytest.approx(500.0)
    assert out[0]["leverage"] == 2
    assert out[0]["side"] == "Long"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_engine_close.py -v`
Expected: FAIL — `AttributeError: 'PaperEngine' object has no attribute 'trigger_order'`（前 3 个用例应已通过）

- [ ] **Step 3: 追加实现**

在 `backend/paper_trading/engine.py` 的 PaperEngine 类中追加：

```python
    # ---------- pending order lifecycle (monitor entry points) ----------

    def cancel_order(self, paper: PaperAccount, order_no: str) -> bool:
        order = (
            self.db.query(PaperOrder)
            .filter(
                PaperOrder.paper_account_id == paper.id,
                PaperOrder.order_no == str(order_no),
                PaperOrder.status == "pending",
            )
            .first()
        )
        if not order:
            return False
        order.status = "cancelled"
        self.db.flush()
        return True

    def open_orders_as_client_format(self, paper: PaperAccount, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            {
                "order_id": o.order_no,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "trigger_price": float(o.trigger_price),
                "size": float(o.size),
                "reduce_only": bool(o.reduce_only),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in self.pending_orders(paper, symbol)
        ]

    def trigger_order(self, paper: PaperAccount, order: PaperOrder, mark_price: float) -> Optional[Dict[str, Any]]:
        """Check and execute one pending order against mark_price. Returns fill info or None."""
        rates = fee_mod.get_fee_rates(paper.data_exchange, paper)
        fallback = (
            float(paper.slippage_fallback_pct)
            if paper.slippage_fallback_pct is not None
            else fee_mod.DEFAULT_SLIPPAGE_FALLBACK_PCT
        )
        trigger_px = float(order.trigger_price)

        if order.order_type == "limit":
            crossed = (order.side == "buy" and mark_price <= trigger_px) or (
                order.side == "sell" and mark_price >= trigger_px
            )
            if not crossed:
                return None
            fill = self._fill(
                paper, order.symbol, order.side, float(order.size),
                int(order.leverage), bool(order.reduce_only), trigger_px, rates["maker"],
            )
            if fill["status"] == "error":
                order.status = "cancelled"
                self.db.flush()
                return None
            order.status = "filled"
            order.filled_at = datetime.utcnow()
            self.db.flush()
            return {
                "order_no": order.order_no, "symbol": order.symbol,
                "qty": fill["filled_qty"], "price": trigger_px,
                "fee": fill["fee"], "realized_pnl": fill["realized_pnl"],
                "exit_reason": "limit",
            }

        # take_profit / stop_loss (reduce-only trigger orders)
        pos = (
            self.db.query(PaperPosition)
            .filter(PaperPosition.paper_account_id == paper.id, PaperPosition.symbol == order.symbol)
            .first()
        )
        if not pos:
            order.status = "cancelled"
            self.db.flush()
            return None

        is_long = pos.side == "long"
        is_tp = order.order_type == "take_profit"
        triggered = (
            (is_tp and is_long and mark_price >= trigger_px)
            or (is_tp and not is_long and mark_price <= trigger_px)
            or ((not is_tp) and is_long and mark_price <= trigger_px)
            or ((not is_tp) and not is_long and mark_price >= trigger_px)
        )
        if not triggered:
            return None

        if order.exec_mode == "market":
            close_is_sell = is_long
            exit_px = trigger_px * (1 - fallback / 100) if close_is_sell else trigger_px * (1 + fallback / 100)
            fee_rate = rates["taker"]
        else:
            exit_px = trigger_px
            fee_rate = rates["maker"]

        qty = min(float(order.size), float(pos.size))
        pnl, fee = self._close_qty(paper, pos, qty, exit_px, fee_rate, order.order_no)
        order.status = "filled"
        order.filled_at = datetime.utcnow()
        self.db.flush()
        return {
            "order_no": order.order_no, "symbol": order.symbol,
            "qty": qty, "price": exit_px, "fee": fee, "realized_pnl": pnl,
            "exit_reason": "tp" if is_tp else "sl",
        }

    def positions_as_client_format(self, paper: PaperAccount, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        out = []
        for pos in self.positions(paper):
            px = prices.get(pos.symbol, float(pos.entry_price))
            size = float(pos.size)
            entry = float(pos.entry_price)
            upnl = (px - entry) * size if pos.side == "long" else (entry - px) * size
            out.append({
                "coin": pos.symbol,
                "szi": size if pos.side == "long" else -size,
                "entry_px": entry,
                "position_value": size * px,
                "unrealized_pnl": upnl,
                "margin_used": size * entry / max(int(pos.leverage), 1),
                "liquidation_px": 0.0,
                "leverage": int(pos.leverage),
                "side": "Long" if pos.side == "long" else "Short",
                "opened_at": int(pos.opened_at.timestamp() * 1000) if pos.opened_at else None,
            })
        return out
```

- [ ] **Step 4: 运行全部引擎测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_engine_open.py tests/test_paper_engine_close.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/engine.py backend/tests/test_paper_engine_close.py
git commit -m "Add paper engine close, netting, pending order triggers"
```

---

### Task 6: 撮合引擎（三）：全仓清算、funding 结算、周期重置

**Files:**
- Modify: `backend/paper_trading/engine.py`（追加方法）
- Test: `backend/tests/test_paper_engine_risk.py`

**Interfaces:**
- Produces（追加到 PaperEngine）：
  - `check_liquidation(paper, prices) -> Optional[Dict]`（`equity < used_margin * 0.5` 时按市价±回退滑点强平全部持仓并取消全部挂单；返回 `{"order_no", "closed": [{"symbol", "pnl", "fee"}]}` 或 None）
  - `apply_funding(paper, prices, now=None) -> float`（按 FUNDING_INTERVAL_HOURS 到期结算，写 PaperFundingRecord，更新 total_funding/last_funding_at；返回本次结算净额）
  - `reset_cycle(paper, initial_capital: Optional[float] = None) -> None`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_engine_risk.py`：

```python
"""PaperEngine: liquidation, funding settlement, cycle reset."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def test_no_liquidation_when_healthy(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    assert engine.check_liquidation(paper, {"BTC": 99000.0}) is None


def test_liquidation_closes_all_and_cancels_orders(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # 10x leverage: margin 5000, position 0.5 BTC @ 100000
    engine.place_order(
        paper, "BTC", True, 0.5, 100000.0, 100000.0, leverage=10,
        stop_loss_price=80000.0,
    )
    # equity at 85000: 10000 - 0.5*15000 - fees < maintenance (5000*0.5=2500)
    result = engine.check_liquidation(paper, {"BTC": 85000.0})
    assert result is not None
    assert len(result["closed"]) == 1
    assert result["closed"][0]["symbol"] == "BTC"
    assert engine.positions(paper) == []
    assert engine.pending_orders(paper) == []
    # realized loss applied
    state = engine.compute_state(paper, {})
    assert state["total_equity"] < 3000


def test_funding_not_due(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(minutes=30)
    assert engine.apply_funding(paper, {"BTC": 100000.0}) == 0.0


def test_funding_settlement_long_pays(engine, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(engine_mod.fee_mod, "fetch_funding_rate", lambda ex, sym: 0.0001)
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(hours=2)
    amount = engine.apply_funding(paper, {"BTC": 100000.0})
    # long pays positive rate: -0.0001 * 10000 = -1.0
    assert amount == pytest.approx(-1.0)
    assert float(paper.total_funding) == pytest.approx(-1.0)

    from database.models import PaperFundingRecord
    records = engine.db.query(PaperFundingRecord).all()
    assert len(records) == 1
    assert float(records[0].amount) == pytest.approx(-1.0)


def test_funding_settlement_short_receives(engine, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(engine_mod.fee_mod, "fetch_funding_rate", lambda ex, sym: 0.0001)
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", False, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(hours=2)
    amount = engine.apply_funding(paper, {"BTC": 100000.0})
    assert amount == pytest.approx(1.0)


def test_reset_cycle(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    engine.reset_cycle(paper, initial_capital=20000.0)
    assert engine.positions(paper) == []
    assert engine.pending_orders(paper) == []
    assert paper.cycle == 2
    assert float(paper.initial_capital) == 20000.0
    assert float(paper.realized_pnl_total) == 0
    assert float(paper.total_fees) == 0
    assert float(paper.total_funding) == 0
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == 20000.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_engine_risk.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'check_liquidation'`

- [ ] **Step 3: 追加实现**

在 PaperEngine 类中追加：

```python
    # ---------- risk: liquidation / funding / reset ----------

    def check_liquidation(self, paper: PaperAccount, prices: Dict[str, float]) -> Optional[Dict[str, Any]]:
        state = self.compute_state(paper, prices)
        if state["used_margin"] <= 0:
            return None
        if state["total_equity"] >= state["maintenance_margin"]:
            return None

        rates = fee_mod.get_fee_rates(paper.data_exchange, paper)
        fallback = (
            float(paper.slippage_fallback_pct)
            if paper.slippage_fallback_pct is not None
            else fee_mod.DEFAULT_SLIPPAGE_FALLBACK_PCT
        )
        order_no = _new_order_no()
        closed = []
        for pos in list(self.positions(paper)):
            px = prices.get(pos.symbol)
            if not px:
                continue
            exit_px = px * (1 - fallback / 100) if pos.side == "long" else px * (1 + fallback / 100)
            pnl, fee = self._close_qty(paper, pos, float(pos.size), exit_px, rates["taker"], order_no)
            closed.append({"symbol": pos.symbol, "pnl": pnl, "fee": fee})
        for o in self.pending_orders(paper):
            o.status = "cancelled"
        self.db.flush()
        logger.warning(
            f"[PAPER] LIQUIDATION account={paper.account_id} equity=${state['total_equity']:.2f} "
            f"< maintenance=${state['maintenance_margin']:.2f}, closed {len(closed)} positions"
        )
        return {"order_no": order_no, "closed": closed}

    def apply_funding(self, paper: PaperAccount, prices: Dict[str, float], now: Optional[datetime] = None) -> float:
        now = now or datetime.utcnow()
        interval_h = fee_mod.FUNDING_INTERVAL_HOURS.get(paper.data_exchange, 1)
        last = paper.last_funding_at or paper.cycle_started_at
        if last is not None and (now - last).total_seconds() < interval_h * 3600:
            return 0.0

        total = 0.0
        for pos in self.positions(paper):
            px = prices.get(pos.symbol)
            rate = fee_mod.fetch_funding_rate(paper.data_exchange, pos.symbol)
            if not px or rate is None:
                continue
            notional = float(pos.size) * px
            # long pays positive funding, short receives
            amount = -rate * notional if pos.side == "long" else rate * notional
            paper.total_funding = float(paper.total_funding) + amount
            self.db.add(PaperFundingRecord(
                paper_account_id=paper.id, symbol=pos.symbol, funding_rate=rate,
                position_notional=notional, amount=amount, cycle=paper.cycle, settled_at=now,
            ))
            total += amount
        paper.last_funding_at = now
        self.db.flush()
        return total

    def reset_cycle(self, paper: PaperAccount, initial_capital: Optional[float] = None) -> None:
        for o in self.pending_orders(paper):
            o.status = "cancelled"
        for p in self.positions(paper):
            self.db.delete(p)
        if initial_capital is not None:
            paper.initial_capital = initial_capital
        paper.realized_pnl_total = 0
        paper.total_fees = 0
        paper.total_funding = 0
        paper.cycle = int(paper.cycle) + 1
        paper.cycle_started_at = datetime.utcnow()
        paper.last_funding_at = None
        self.db.flush()
        logger.info(f"[PAPER] Reset account {paper.account_id} to cycle {paper.cycle}")
```

注意 `apply_funding` 中 `paper.cycle_started_at` 在 SQLite 测试里由 `server_default` 生成，flush 后需 `db.refresh` 才有值——若测试中 `cycle_started_at` 为 None，`last is None` 时视为到期结算（保持上面代码的 None 分支语义：`last is not None and ...` 为 False → 直接结算）。

- [ ] **Step 4: 运行全部引擎测试**

Run: `cd backend; uv run pytest tests/test_paper_engine_open.py tests/test_paper_engine_close.py tests/test_paper_engine_risk.py -v`
Expected: PASS (21 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/engine.py backend/tests/test_paper_engine_risk.py
git commit -m "Add paper engine liquidation, funding settlement, cycle reset"
```

---

### Task 7: 客户端适配器 `paper_trading/client.py`

**Files:**
- Create: `backend/paper_trading/client.py`
- Test: `backend/tests/test_paper_client.py`

**Interfaces:**
- Consumes: PaperEngine 全部方法
- Produces: `PaperTradingClient(account_id: int, data_exchange: str)`，与真实 client 同签名的方法（管线用到的全部）：
  - 属性 `environment = "paper"`、`wallet_address = f"paper-{account_id}"`
  - `get_account_state(db) -> Dict`
  - `get_positions(db, include_timing=False) -> List[Dict]`
  - `place_order_with_tpsl(db, symbol, is_buy, size, price, leverage=1, time_in_force="Ioc", reduce_only=False, take_profit_price=None, stop_loss_price=None, tp_execution="limit", sl_execution="limit") -> Dict`
  - `get_open_orders(db, symbol=None) -> List[Dict]`
  - `cancel_order(db, order_id, symbol) -> bool`
- 价格来源：`services.market_data.get_last_price(symbol, market)`，hyperliquid 用 `market="CRYPTO"`（默认主网 client），binance 用 `market="binance"`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_client.py`：

```python
"""PaperTradingClient interface parity tests."""
import pytest


@pytest.fixture()
def client(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading import client as client_mod
    monkeypatch.setattr(client_mod, "_get_last_price", lambda symbol, exchange: 100000.0)
    from paper_trading.client import PaperTradingClient
    c = PaperTradingClient(account_id=1, data_exchange="hyperliquid")
    monkeypatch.setattr(c, "_session_factory", lambda: db_session)
    c._snapshot_factory = snapshot_session_factory
    return c


def test_client_attributes(client):
    assert client.environment == "paper"
    assert client.wallet_address == "paper-1"


def test_account_state_shape(client, db_session):
    state = client.get_account_state(db_session)
    for key in ("total_equity", "available_balance", "used_margin",
                "maintenance_margin", "margin_usage_percent", "wallet_address"):
        assert key in state
    assert state["total_equity"] == 10000.0


def test_place_order_and_positions(client, db_session):
    result = client.place_order_with_tpsl(
        db=db_session, symbol="BTC", is_buy=True, size=0.1, price=100000.0,
        leverage=2, take_profit_price=110000.0, stop_loss_price=95000.0,
    )
    assert result["status"] == "filled"
    assert result["order_id"].startswith("P-")
    assert result["tp_order_id"].startswith("P-")

    positions = client.get_positions(db_session, include_timing=True)
    assert positions[0]["coin"] == "BTC"
    assert positions[0]["szi"] == pytest.approx(0.1)
    assert "opened_at_str" in positions[0]

    orders = client.get_open_orders(db_session, symbol="BTC")
    assert len(orders) == 2
    assert client.cancel_order(db_session, orders[0]["order_id"], "BTC") is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paper_trading.client'`

- [ ] **Step 3: 实现 client.py**

`backend/paper_trading/client.py`：

```python
"""PaperTradingClient - drop-in client with the same interface as real trading clients.

Reads mainnet market data (read-only); all order operations go to PaperEngine.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from paper_trading.engine import PaperEngine

logger = logging.getLogger(__name__)


def _get_last_price(symbol: str, data_exchange: str) -> Optional[float]:
    from services.market_data import get_last_price
    market = "binance" if data_exchange == "binance" else "CRYPTO"
    try:
        price = get_last_price(symbol, market)
        return float(price) if price else None
    except Exception as e:
        logger.warning(f"[PAPER] Failed to get price for {symbol}: {e}")
        return None


class PaperTradingClient:
    def __init__(self, account_id: int, data_exchange: str = "hyperliquid"):
        self.account_id = account_id
        self.data_exchange = data_exchange
        self.environment = "paper"
        self.wallet_address = f"paper-{account_id}"
        self._snapshot_factory = None  # test override; None = default snapshot DB

    def _session_factory(self):
        """Overridable in tests; production uses caller-provided db sessions directly."""
        raise NotImplementedError

    def _engine(self, db: Session) -> PaperEngine:
        return PaperEngine(db, snapshot_session_factory=self._snapshot_factory)

    def _prices_for(self, db: Session, symbols: List[str]) -> Dict[str, float]:
        prices = {}
        for s in symbols:
            px = _get_last_price(s, self.data_exchange)
            if px:
                prices[s] = px
        return prices

    # ---------- interface parity with real clients ----------

    def get_account_state(self, db: Session) -> Dict[str, Any]:
        engine = self._engine(db)
        paper = engine.get_or_create(self.account_id, self.data_exchange)
        symbols = [p.symbol for p in engine.positions(paper)]
        prices = self._prices_for(db, symbols)
        state = engine.compute_state(paper, prices)
        db.commit()
        return state

    def get_positions(self, db: Session, include_timing: bool = False) -> List[Dict[str, Any]]:
        engine = self._engine(db)
        paper = engine.get_or_create(self.account_id, self.data_exchange)
        symbols = [p.symbol for p in engine.positions(paper)]
        prices = self._prices_for(db, symbols)
        positions = engine.positions_as_client_format(paper, prices)
        if include_timing:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            for pos in positions:
                opened = pos.get("opened_at")
                if opened:
                    dt = datetime.fromtimestamp(opened / 1000, tz=timezone.utc)
                    pos["opened_at_str"] = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    seconds = (now_ms - opened) / 1000
                    pos["holding_duration_seconds"] = seconds
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    pos["holding_duration_str"] = f"{hours}h {minutes}m"
                else:
                    pos["opened_at_str"] = None
                    pos["holding_duration_seconds"] = None
                    pos["holding_duration_str"] = None
        db.commit()
        return positions

    def place_order_with_tpsl(
        self,
        db: Session,
        symbol: str,
        is_buy: bool,
        size: float,
        price: float,
        leverage: int = 1,
        time_in_force: str = "Ioc",
        reduce_only: bool = False,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        tp_execution: str = "limit",
        sl_execution: str = "limit",
    ) -> Dict[str, Any]:
        market_price = _get_last_price(symbol, self.data_exchange)
        if not market_price:
            return {
                "status": "error",
                "error": f"Unable to get market price for {symbol}",
                "environment": "paper",
                "symbol": symbol,
            }
        engine = self._engine(db)
        paper = engine.get_or_create(self.account_id, self.data_exchange)
        result = engine.place_order(
            paper, symbol, is_buy, size,
            limit_price=price, market_price=market_price,
            leverage=leverage, time_in_force=time_in_force, reduce_only=reduce_only,
            take_profit_price=take_profit_price, stop_loss_price=stop_loss_price,
            tp_execution=tp_execution, sl_execution=sl_execution,
        )
        db.commit()
        logger.info(
            f"[PAPER {self.data_exchange.upper()}] {('BUY' if is_buy else 'SELL')} {symbol} "
            f"size={size} status={result.get('status')} avg={result.get('average_price')}"
        )
        return result

    def get_open_orders(self, db: Session, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        engine = self._engine(db)
        paper = engine.get_or_create(self.account_id, self.data_exchange)
        orders = engine.open_orders_as_client_format(paper, symbol)
        db.commit()
        return orders

    def cancel_order(self, db: Session, order_id: Any, symbol: str) -> bool:
        engine = self._engine(db)
        paper = engine.get_or_create(self.account_id, self.data_exchange)
        ok = engine.cancel_order(paper, str(order_id))
        db.commit()
        return ok
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/paper_trading/client.py backend/tests/test_paper_client.py
git commit -m "Add PaperTradingClient with real-client interface parity"
```

---

### Task 8: execution_mode 配置链路（schema → repo → 序列化 → StrategyState）

**Files:**
- Modify: `backend/schemas/account.py:48-58`（StrategyConfigBase 加字段）
- Modify: `backend/repositories/strategy_repo.py:39-85`（upsert_strategy 加参数）
- Modify: `backend/api/account_routes.py:57-110`（_serialize_strategy 输出）与 `:365-375`（update 路由传参）
- Modify: `backend/services/trading_strategy.py:48-59`（StrategyState 加字段）与 `_load_strategies`（读取 execution_mode）
- Test: `backend/tests/test_execution_mode_config.py`

**Interfaces:**
- Produces: `StrategyConfigBase.execution_mode: str = "real"`（Pydantic）
- Produces: `upsert_strategy(..., execution_mode: str = "real")`
- Produces: `StrategyState.execution_mode: str = "real"`
- 校验：execution_mode 只接受 "real"/"paper"，非法值按 "real" 处理

- [ ] **Step 1: 写失败测试**

`backend/tests/test_execution_mode_config.py`：

```python
"""execution_mode propagation: schema -> repo -> ORM."""


def test_upsert_strategy_execution_mode(db_session):
    from repositories.strategy_repo import upsert_strategy
    strategy = upsert_strategy(
        db_session, account_id=1, trigger_interval=150,
        exchange="hyperliquid", execution_mode="paper",
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


def test_schema_has_execution_mode():
    from schemas.account import StrategyConfigUpdate
    payload = StrategyConfigUpdate(exchange="hyperliquid", execution_mode="paper")
    assert payload.execution_mode == "paper"
    assert StrategyConfigUpdate(exchange="hyperliquid").execution_mode == "real"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_execution_mode_config.py -v`
Expected: FAIL — `TypeError: upsert_strategy() got an unexpected keyword argument 'execution_mode'`

- [ ] **Step 3: 实现四处修改**

`backend/schemas/account.py` — `StrategyConfigBase` 的 `exchange` 字段之后加：

```python
    execution_mode: str = "real"  # "real" or "paper"
```

`backend/repositories/strategy_repo.py` — `upsert_strategy` 签名 `exchange` 参数后加 `execution_mode: str = "real"`；函数体 `strategy.exchange = exchange` 之后加：

```python
    strategy.execution_mode = execution_mode if execution_mode in ("real", "paper") else "real"
```

`backend/api/account_routes.py` — `update` 路由（:365-375）`upsert_strategy(...)` 调用加：

```python
        execution_mode=payload.execution_mode,
```

`_serialize_strategy`（:57 起）返回的 `StrategyConfig(...)` 构造中加：

```python
        execution_mode=getattr(strategy, "execution_mode", None) or "real",
```

`backend/services/trading_strategy.py` — `StrategyState`（:48）的 `exchange` 字段后加：

```python
    execution_mode: str = "real"  # "real" or "paper"
```

`_load_strategies` 中构造 `StrategyState(...)` 处（搜索 `exchange=`，约 :420-440）同步加：

```python
                    execution_mode=getattr(strategy, "execution_mode", None) or "real",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_execution_mode_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/account.py backend/repositories/strategy_repo.py backend/api/account_routes.py backend/services/trading_strategy.py backend/tests/test_execution_mode_config.py
git commit -m "Plumb execution_mode through strategy config chain"
```

---

### Task 9: AI 管线集成（Hyperliquid + Binance 分支）

**Files:**
- Modify: `backend/services/trading_commands.py`（hyperliquid 管线 :499-517；binance 管线 :1344-1375；两处 close 后 PnL 即时回填）
- Modify: `backend/services/ai_decision_service.py:2514-2530`（save_ai_decision 返回创建的日志对象）
- Test: `backend/tests/test_pipeline_paper_branch.py`

**Interfaces:**
- Consumes: `PaperTradingClient`、`AccountStrategyConfig.execution_mode`
- Produces: 辅助函数 `get_execution_mode(db, account_id) -> str`（放在 `backend/paper_trading/__init__.py`）
- Produces: `save_ai_decision(...) -> Optional[AIDecisionLog]`（原返回 None，改为返回创建的日志对象；所有现有调用方忽略返回值，兼容）
- 行为：paper 模式下 environment="paper"、跳过钱包校验、行情用 mainnet、成交后 order_result 含 `realized_pnl` 时立即写回决策日志

- [ ] **Step 1: 写失败测试**

`backend/tests/test_pipeline_paper_branch.py`：

```python
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
    from database.models import User, Account
    from services.ai_decision_service import save_ai_decision
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
```

注意：`User` 模型的必填字段以 `backend/database/models.py:9-32` 实际定义为准（若 `username` 之外还有 NOT NULL 字段，测试里补上）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_pipeline_paper_branch.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_execution_mode'`

- [ ] **Step 3: 实现辅助函数与 save_ai_decision 返回值**

`backend/paper_trading/__init__.py` 改为：

```python
"""Paper trading package: internal simulated execution over mainnet read-only data."""


def get_execution_mode(db, account_id: int) -> str:
    """Return 'paper' or 'real' for an account based on its strategy config."""
    from database.models import AccountStrategyConfig
    cfg = (
        db.query(AccountStrategyConfig)
        .filter(AccountStrategyConfig.account_id == account_id)
        .first()
    )
    mode = getattr(cfg, "execution_mode", None) if cfg else None
    return "paper" if mode == "paper" else "real"
```

`backend/services/ai_decision_service.py` `save_ai_decision`：
- 签名返回类型 `-> None` 改为 `-> Optional["AIDecisionLog"]`
- 函数内创建 `AIDecisionLog(...)`（搜索 `decision_log = AIDecisionLog(` 或 `db.add(`）后，确保函数末尾 `return decision_log`；异常分支 `return None`

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_pipeline_paper_branch.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Hyperliquid 管线分支**

`backend/services/trading_commands.py` `place_ai_driven_hyperliquid_order`：

(a) 环境与 client 获取处（:499-517，`environment = get_global_trading_mode(db)` 与 `get_hyperliquid_client` 的 try/except 块）改为：

```python
            from services.hyperliquid_environment import get_global_trading_mode, get_leverage_settings
            from paper_trading import get_execution_mode

            is_paper = get_execution_mode(db, account.id) == "paper"
            if is_paper:
                environment = "paper"
                from paper_trading.client import PaperTradingClient
                client = PaperTradingClient(account.id, "hyperliquid")
                logger.info(f"Processing PAPER trading for account: {account.name} (hyperliquid data)")
            else:
                environment = get_global_trading_mode(db)
                logger.info(f"Processing Hyperliquid trading for account: {account.name} (environment: {environment})")
                try:
                    client = get_hyperliquid_client(db, account.id, override_environment=environment)
                except ValueError as wallet_err:
                    logger.info(
                        f"AI Trader '{account.name}' (ID: {account.id}) skipped - "
                        f"Hyperliquid wallet not configured. {str(wallet_err)} "
                        f"Please configure wallet in AI Traders management page."
                    )
                    continue
                except Exception as client_err:
                    logger.error(f"Failed to get Hyperliquid client for {account.name}: {client_err}")
                    continue
```

(b) paper 模式行情强制主网——在 per-account 循环内、`call_ai_for_decision` 之前（prices 使用处），加：

```python
            if is_paper and prompt_environment != "mainnet":
                paper_tickers = _get_realtime_ticker_snapshot(selected_symbols, environment="mainnet")
                paper_prices = {
                    s: float(t.get("price", 0) or 0)
                    for s, t in paper_tickers.items()
                    if float(t.get("price", 0) or 0) > 0
                }
                if paper_prices:
                    prices = paper_prices
```

(c) 杠杆设置（:666 `get_leverage_settings(db, account.id, environment)`）在 paper 模式下 environment="paper" 无对应钱包记录——该函数已有 Account 表回退逻辑（hyperliquid_environment.py:186-193），无需改动，但确认调用不抛异常（回退返回 Account.max_leverage/default_leverage）。

(d) 成交后 PnL 即时回填——`save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)`（:1186，filled 分支）改为：

```python
                        decision_log = save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)
                        if environment == "paper" and decision_log is not None and order_result.get("realized_pnl"):
                            from datetime import datetime as _dt
                            decision_log.realized_pnl = order_result["realized_pnl"]
                            decision_log.pnl_updated_at = _dt.utcnow()
                            db.commit()
```

(e) 成交记录写入（:1215-1228）已使用 `environment` 变量和 `order_result.get('fee', 0)`——paper 模式自动写出 environment="paper" 且 fee 为引擎真实计算值，**无需改动**（确认即可）。

- [ ] **Step 6: Binance 管线分支**

`place_ai_driven_binance_order`（:1344-1375）钱包检查与 client 初始化处改为：

```python
            from services.hyperliquid_environment import get_global_trading_mode
            from paper_trading import get_execution_mode

            is_paper = get_execution_mode(db, account.id) == "paper"
            if is_paper:
                environment = "paper"
                from paper_trading.client import PaperTradingClient
                client = PaperTradingClient(account.id, "binance")
                decision_kwargs = {"wallet_address": f"paper-{account.id}", "exchange": "binance"}
                logger.info(f"Processing PAPER trading for account: {account.name} (binance data)")
            else:
                environment = get_global_trading_mode(db)
                if not environment:
                    logger.info(f"AI Trader '{account.name}' skipped - No trading environment configured")
                    continue

                wallet = db.query(BinanceWallet).filter(
                    BinanceWallet.account_id == account.id,
                    BinanceWallet.environment == environment,
                    BinanceWallet.is_active == "true"
                ).first()

                if not wallet or not wallet.api_key_encrypted or not wallet.secret_key_encrypted:
                    logger.info(
                        f"AI Trader '{account.name}' (ID: {account.id}) skipped - "
                        f"Binance wallet not configured."
                    )
                    continue

                from utils.encryption import decrypt_private_key
                api_key = decrypt_private_key(wallet.api_key_encrypted)
                secret_key = decrypt_private_key(wallet.secret_key_encrypted)
                client = BinanceTradingClient(
                    api_key=api_key,
                    secret_key=secret_key,
                    environment=wallet.environment or "testnet"
                )
                decision_kwargs = {"wallet_address": str(wallet.id), "exchange": "binance"}
```

（原 `decision_kwargs = {...}` 行删除，注意保留其后 prompt_template_id/signal_trigger_id 的填充代码。）

binance 管线中 Binance 每日配额检查（`_check_binance_daily_quota` 调用处，条件含 `environment == "mainnet"`）在 paper 下自然跳过——搜索确认条件里用的是 `environment` 变量后无需改动；若有无条件调用处则包一层 `if not is_paper`。

binance 管线的 filled 分支同样加 PnL 即时回填——搜索该函数内 `save_ai_decision(db, account, decision, portfolio, executed=True` 的 filled 调用点，改为：

```python
                        decision_log = save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)
                        if environment == "paper" and decision_log is not None and order_result.get("realized_pnl"):
                            from datetime import datetime as _dt
                            decision_log.realized_pnl = order_result["realized_pnl"]
                            decision_log.pnl_updated_at = _dt.utcnow()
                            db.commit()
```

binance 管线的成交记录写入（:1674/:1735 `HyperliquidTrade(...)`）使用 `environment` 变量——paper 自动生效，确认即可。

- [ ] **Step 7: 手动验证分支不破坏现有路径**

Run: `cd backend; uv run python -c "import services.trading_commands; import services.ai_decision_service; print('ok')"`
Expected: `ok`（无导入错误）

Run: `cd backend; uv run pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/trading_commands.py backend/services/ai_decision_service.py backend/paper_trading/__init__.py backend/tests/test_pipeline_paper_branch.py
git commit -m "Route AI trading pipelines through PaperTradingClient in paper mode"
```

---

### Task 10: 程序化交易管线集成

**Files:**
- Modify: `backend/services/program_execution_service.py`（两处 client 创建：:340-376 与 :860-901 附近）
- Test: 复用 Task 9 的 import 冒烟验证

**Interfaces:**
- Consumes: `get_execution_mode`、`PaperTradingClient`
- 行为：paper 模式下 `environment = "paper"`、`trading_client = PaperTradingClient(account.id, exchange)`，杠杆设置走既有回退

- [ ] **Step 1: 修改第一处 client 创建（:340-376）**

`environment = get_global_trading_mode(db)` 与其后的 if/else 整块改为：

```python
            from paper_trading import get_execution_mode

            is_paper = get_execution_mode(db, account.id) == "paper"
            if is_paper:
                environment = "paper"
                from paper_trading.client import PaperTradingClient
                trading_client = PaperTradingClient(account.id, exchange)
                if exchange == "binance":
                    leverage_settings = self._get_binance_leverage_settings(db, account.id, "mainnet")
                else:
                    leverage_settings = get_leverage_settings(db, account.id, "mainnet")
            else:
                environment = get_global_trading_mode(db)
                trading_client = None

                if exchange == "binance":
                    # ... 原有 Binance client 创建代码原样保留 ...
                    leverage_settings = self._get_binance_leverage_settings(db, account.id, environment or "mainnet")
                else:
                    # ... 原有 Hyperliquid client 创建代码原样保留 ...
                    leverage_settings = get_leverage_settings(db, account.id, environment or "mainnet")
```

（"原样保留"指把现有 :345-376 的两个分支体整体移进 else 内，不改内容。）

- [ ] **Step 2: 修改第二处 client 创建（:860-901 附近）**

同一模式：先 `is_paper = get_execution_mode(db, binding.account_id) == "paper"`；paper 时 `client = PaperTradingClient(binding.account_id, exchange)`、`environment = "paper"`，否则走原有分支。

- [ ] **Step 3: DataProvider 兼容确认**

`DataProvider(db, account.id, environment or "mainnet", trading_client, ...)`（:382-385）在 paper 下收到 environment="paper"。检查 `backend/program_trader/data_provider.py` 中 environment 的用途：若仅用于行情接口选择（testnet/mainnet），把 paper 管线传入的值改为 `"mainnet" if is_paper else (environment or "mainnet")`：

```python
            data_provider = DataProvider(
                db, account.id, "mainnet" if is_paper else (environment or "mainnet"), trading_client,
                record_queries=True, exchange=exchange
            )
```

程序执行日志（ProgramExecutionLog）写入处使用 `environment` 变量——确认 paper 模式下记录的 environment 字段为 "paper"（搜索该文件内 `ProgramExecutionLog(`，若 environment 取值来自局部变量则已生效）。

- [ ] **Step 4: 验证**

Run: `cd backend; uv run python -c "import services.program_execution_service; print('ok')"`
Expected: `ok`

Run: `cd backend; uv run pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/program_execution_service.py
git commit -m "Route program trader execution through paper client in paper mode"
```

---

### Task 11: 后台监控服务 `paper_trading/monitor.py` + 启动注册

**Files:**
- Create: `backend/paper_trading/monitor.py`
- Modify: `backend/services/startup.py:140` 附近（market flow collector 启动后注册）
- Test: `backend/tests/test_paper_monitor.py`

**Interfaces:**
- Consumes: PaperEngine 全部方法、`fees.FUNDING_INTERVAL_HOURS`
- Produces: `PaperMonitor(poll_interval_seconds=3, snapshot_interval_seconds=60)` 单例 `paper_monitor`：
  - `async start()` — 常驻循环（模式同 `hyperliquid_snapshot_service.start`）
  - `run_once(db) -> None` — 单轮检查（同步、可测）：遍历有 paper 账户的交易员 → 拉价格 → `trigger_order` 全部 pending → `check_liquidation` → `apply_funding` → 更新 `last_monitor_at`
  - `catch_up(db, paper) -> None` — 启动补检：用 1 分钟 K 线（`services.market_data.get_kline_data(symbol, "CRYPTO", "1m", count, "mainnet", persist=False)`；binance 用 `https://fapi.binance.com/fapi/v1/klines`）按时间顺序对 `last_monitor_at` 以来的每根 K 线以 high/low 依次调 `trigger_order`
  - `_backfill_decision_pnl(db, fill: dict) -> None` — 按 order_no 匹配 `AIDecisionLog.tp_order_id/sl_order_id/hyperliquid_order_id` 与 `ProgramExecutionLog` 同名字段，写 realized_pnl/pnl_updated_at
  - `_write_snapshot(paper, state) -> None` — 写 `HyperliquidAccountSnapshot(environment="paper", trigger_event="scheduled")`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_monitor.py`：

```python
"""PaperMonitor: trigger sweep and decision PnL backfill."""
import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def test_backfill_decision_pnl_matches_tp_order(db_session, engine):
    from database.models import User, Account, AIDecisionLog
    from paper_trading.monitor import PaperMonitor

    u = User(username="t2")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="T", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    log = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper",
        tp_order_id="P-tp1", exchange="hyperliquid",
    )
    db_session.add(log)
    db_session.flush()

    monitor = PaperMonitor()
    monitor._backfill_decision_pnl(db_session, {
        "order_no": "P-tp1", "symbol": "BTC", "qty": 0.1, "price": 110000.0,
        "fee": 1.65, "realized_pnl": 1000.0, "exit_reason": "tp",
    })
    db_session.flush()
    assert float(log.realized_pnl) == pytest.approx(1000.0)
    assert log.pnl_updated_at is not None


def test_sweep_account_triggers_tp(db_session, engine, monkeypatch):
    from paper_trading.monitor import PaperMonitor
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    monitor = PaperMonitor()
    fills = monitor._sweep_account(db_session, engine, paper, {"BTC": 111000.0})
    assert len(fills) == 1
    assert fills[0]["exit_reason"] == "tp"
    assert engine.positions(paper) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paper_trading.monitor'`

- [ ] **Step 3: 实现 monitor.py**

`backend/paper_trading/monitor.py`：

```python
"""PaperMonitor: background service for pending orders, liquidation, funding, snapshots."""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PaperMonitor:
    def __init__(self, poll_interval_seconds: int = 3, snapshot_interval_seconds: int = 60):
        self.poll_interval = poll_interval_seconds
        self.snapshot_interval = snapshot_interval_seconds
        self.running = False
        self._last_snapshot_at = 0.0
        self._did_catch_up = False

    async def start(self):
        self.running = True
        logger.info(f"[PAPER MONITOR] Started, poll={self.poll_interval}s")
        while self.running:
            try:
                await asyncio.to_thread(self._tick)
            except Exception as e:
                logger.error(f"[PAPER MONITOR] Tick error: {e}", exc_info=True)
            await asyncio.sleep(self.poll_interval)

    def _tick(self):
        import time
        from database.connection import SessionLocal
        db = SessionLocal()
        try:
            if not self._did_catch_up:
                self._catch_up_all(db)
                self._did_catch_up = True
            self.run_once(db)
            if time.time() - self._last_snapshot_at >= self.snapshot_interval:
                self._snapshot_all(db)
                self._last_snapshot_at = time.time()
        finally:
            db.close()

    # ---------- core sweep ----------

    def run_once(self, db: Session) -> None:
        from database.models import PaperAccount
        from paper_trading.engine import PaperEngine

        engine = PaperEngine(db)
        papers = db.query(PaperAccount).all()
        for paper in papers:
            try:
                symbols = {p.symbol for p in engine.positions(paper)}
                symbols |= {o.symbol for o in engine.pending_orders(paper)}
                if not symbols:
                    paper.last_monitor_at = datetime.utcnow()
                    continue
                prices = self._get_prices(paper.data_exchange, sorted(symbols))
                if not prices:
                    continue
                fills = self._sweep_account(db, engine, paper, prices)
                for fill in fills:
                    self._backfill_decision_pnl(db, fill)
                liq = engine.check_liquidation(paper, prices)
                if liq:
                    logger.warning(f"[PAPER MONITOR] Liquidated account {paper.account_id}")
                engine.apply_funding(paper, prices)
                paper.last_monitor_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"[PAPER MONITOR] Account {paper.account_id} sweep failed: {e}", exc_info=True)

    def _sweep_account(self, db: Session, engine, paper, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        fills = []
        for order in list(engine.pending_orders(paper)):
            px = prices.get(order.symbol)
            if not px:
                continue
            fill = engine.trigger_order(paper, order, px)
            if fill:
                fills.append(fill)
                logger.info(
                    f"[PAPER MONITOR] Order {fill['order_no']} filled: {fill['exit_reason']} "
                    f"{fill['symbol']} qty={fill['qty']} @ {fill['price']:.2f} pnl={fill['realized_pnl']:.2f}"
                )
        return fills

    # ---------- PnL backfill ----------

    def _backfill_decision_pnl(self, db: Session, fill: Dict[str, Any]) -> None:
        from sqlalchemy import or_
        from database.models import AIDecisionLog, ProgramExecutionLog
        order_no = fill["order_no"]
        now = datetime.utcnow()

        decision = db.query(AIDecisionLog).filter(
            or_(
                AIDecisionLog.tp_order_id == order_no,
                AIDecisionLog.sl_order_id == order_no,
                AIDecisionLog.hyperliquid_order_id == order_no,
            )
        ).first()
        if decision is not None:
            decision.realized_pnl = fill["realized_pnl"]
            decision.pnl_updated_at = now

        prog = db.query(ProgramExecutionLog).filter(
            or_(
                ProgramExecutionLog.tp_order_id == order_no,
                ProgramExecutionLog.sl_order_id == order_no,
                ProgramExecutionLog.hyperliquid_order_id == order_no,
            )
        ).first()
        if prog is not None:
            prog.realized_pnl = fill["realized_pnl"]
            prog.pnl_updated_at = now

    # ---------- prices / klines ----------

    def _get_prices(self, data_exchange: str, symbols: List[str]) -> Dict[str, float]:
        from paper_trading.client import _get_last_price
        prices = {}
        for s in symbols:
            px = _get_last_price(s, data_exchange)
            if px:
                prices[s] = px
        return prices

    def _get_1m_klines(self, data_exchange: str, symbol: str, count: int) -> List[Dict[str, float]]:
        """Returns [{timestamp(s), high, low, close}] oldest-first. Empty list on failure."""
        try:
            if data_exchange == "binance":
                import requests
                from services.exchanges.symbol_mapper import SymbolMapper
                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/klines",
                    params={"symbol": SymbolMapper.to_exchange(symbol, "binance"),
                            "interval": "1m", "limit": min(count, 1000)},
                    timeout=10,
                )
                resp.raise_for_status()
                return [
                    {"timestamp": k[0] // 1000, "high": float(k[2]),
                     "low": float(k[3]), "close": float(k[4])}
                    for k in resp.json()
                ]
            from services.hyperliquid_market_data import get_kline_data_from_hyperliquid
            klines = get_kline_data_from_hyperliquid(
                symbol, period="1m", count=count, persist=False, environment="mainnet",
            )
            return [
                {"timestamp": int(k["timestamp"]), "high": float(k["high"]),
                 "low": float(k["low"]), "close": float(k["close"])}
                for k in klines
            ]
        except Exception as e:
            logger.warning(f"[PAPER MONITOR] Kline fetch failed for {symbol}: {e}")
            return []

    # ---------- restart catch-up ----------

    def _catch_up_all(self, db: Session) -> None:
        from database.models import PaperAccount
        from paper_trading.engine import PaperEngine
        engine = PaperEngine(db)
        for paper in db.query(PaperAccount).all():
            try:
                self.catch_up(db, engine, paper)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"[PAPER MONITOR] Catch-up failed for {paper.account_id}: {e}")

    def catch_up(self, db: Session, engine, paper) -> None:
        """Replay 1m kline highs/lows since last_monitor_at through pending orders."""
        if not paper.last_monitor_at:
            return
        gap_minutes = int((datetime.utcnow() - paper.last_monitor_at).total_seconds() // 60)
        if gap_minutes < 2:
            return
        count = min(gap_minutes + 1, 1000)
        symbols = {o.symbol for o in engine.pending_orders(paper)}
        for symbol in symbols:
            klines = self._get_1m_klines(paper.data_exchange, symbol, count)
            for k in klines:
                for order in list(engine.pending_orders(paper, symbol)):
                    for probe in (k["low"], k["high"]):
                        fill = engine.trigger_order(paper, order, probe)
                        if fill:
                            self._backfill_decision_pnl(db, fill)
                            break
        logger.info(f"[PAPER MONITOR] Catch-up done for account {paper.account_id} ({gap_minutes}min gap)")

    # ---------- snapshots ----------

    def _snapshot_all(self, db: Session) -> None:
        from database.models import PaperAccount
        from database.snapshot_connection import SnapshotSessionLocal
        from database.snapshot_models import HyperliquidAccountSnapshot
        from paper_trading.engine import PaperEngine

        engine = PaperEngine(db)
        sdb = SnapshotSessionLocal()
        try:
            for paper in db.query(PaperAccount).all():
                symbols = [p.symbol for p in engine.positions(paper)]
                prices = self._get_prices(paper.data_exchange, symbols) if symbols else {}
                state = engine.compute_state(paper, prices)
                sdb.add(HyperliquidAccountSnapshot(
                    account_id=paper.account_id,
                    environment="paper",
                    wallet_address=f"paper-{paper.account_id}",
                    total_equity=state["total_equity"],
                    available_balance=state["available_balance"],
                    used_margin=state["used_margin"],
                    maintenance_margin=state["maintenance_margin"],
                    trigger_event="scheduled",
                ))
            sdb.commit()
        except Exception as e:
            sdb.rollback()
            logger.error(f"[PAPER MONITOR] Snapshot failed: {e}")
        finally:
            sdb.close()


paper_monitor = PaperMonitor()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_monitor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 启动注册**

`backend/services/startup.py` — 在 market flow collector 启动之后（:140 附近）加：

```python
        # Start paper trading monitor (pending orders / liquidation / funding / snapshots)
        from paper_trading.monitor import paper_monitor
        asyncio.create_task(paper_monitor.start())
        logger.info("Paper trading monitor started (3-second interval)")
```

Run: `cd backend; uv run python -c "import services.startup; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add backend/paper_trading/monitor.py backend/services/startup.py backend/tests/test_paper_monitor.py
git commit -m "Add paper trading monitor with catch-up, funding, snapshots"
```

---

### Task 12: Paper API 路由（状态/配置/重置）

**Files:**
- Create: `backend/api/paper_trading_routes.py`
- Modify: `backend/main.py`（import + `app.include_router(paper_trading_router)`，:766 附近）
- Test: `backend/tests/test_paper_routes.py`

**Interfaces:**
- Produces REST 路由（prefix `/api/paper-trading`）：
  - `GET /{account_id}/state` → `{configured, account_id, data_exchange, cycle, initial_capital, total_equity, available_balance, used_margin, unrealized_pnl, realized_pnl_total, total_fees, total_funding, cycle_return_pct, positions: [...], pending_orders: [...]}`
  - `PUT /{account_id}/config` body `{initial_capital?, taker_fee_pct?, maker_fee_pct?, slippage_fallback_pct?}` → 更新覆盖项（initial_capital 仅在无持仓时允许改，且同步调整权益基线）
  - `POST /{account_id}/reset` body `{initial_capital?}` → `reset_cycle`，返回新 state

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_routes.py`：

```python
"""Paper trading API routes (logic-level, using route handler functions directly)."""
import pytest


def test_get_state_unconfigured(db_session):
    from api.paper_trading_routes import build_state
    state = build_state(db_session, account_id=42, create=False)
    assert state == {"configured": False, "account_id": 42}


def test_get_state_and_reset(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from api import paper_trading_routes as routes
    monkeypatch.setattr(routes, "_prices_for", lambda db, paper, engine: {"BTC": 100000.0})

    from paper_trading.engine import PaperEngine
    engine = PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)
    paper = engine.get_or_create(7, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)

    state = routes.build_state(db_session, account_id=7, create=False)
    assert state["configured"] is True
    assert state["cycle"] == 1
    assert len(state["positions"]) == 1
    assert state["total_equity"] == pytest.approx(10000 - 4.5)

    result = routes.do_reset(db_session, account_id=7, initial_capital=15000.0)
    assert result["cycle"] == 2
    assert result["total_equity"] == 15000.0
    assert result["positions"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; uv run pytest tests/test_paper_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.paper_trading_routes'`

- [ ] **Step 3: 实现路由**

`backend/api/paper_trading_routes.py`：

```python
"""Paper trading account API: state, config, reset."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _prices_for(db: Session, paper, engine) -> dict:
    from paper_trading.client import _get_last_price
    prices = {}
    for pos in engine.positions(paper):
        px = _get_last_price(pos.symbol, paper.data_exchange)
        if px:
            prices[pos.symbol] = px
    return prices


def build_state(db: Session, account_id: int, create: bool = False) -> dict:
    from database.models import PaperAccount
    from paper_trading.engine import PaperEngine

    engine = PaperEngine(db)
    paper = db.query(PaperAccount).filter(PaperAccount.account_id == account_id).first()
    if paper is None:
        if not create:
            return {"configured": False, "account_id": account_id}
        paper = engine.get_or_create(account_id, "hyperliquid")

    prices = _prices_for(db, paper, engine)
    state = engine.compute_state(paper, prices)
    initial = float(paper.initial_capital)
    return {
        "configured": True,
        "account_id": account_id,
        "data_exchange": paper.data_exchange,
        "cycle": paper.cycle,
        "cycle_started_at": paper.cycle_started_at.isoformat() if paper.cycle_started_at else None,
        "initial_capital": initial,
        "total_equity": state["total_equity"],
        "available_balance": state["available_balance"],
        "used_margin": state["used_margin"],
        "unrealized_pnl": round(engine.unrealized_pnl(paper, prices), 2),
        "realized_pnl_total": float(paper.realized_pnl_total),
        "total_fees": float(paper.total_fees),
        "total_funding": float(paper.total_funding),
        "cycle_return_pct": round((state["total_equity"] - initial) / initial * 100, 2) if initial > 0 else 0,
        "taker_fee_pct": float(paper.taker_fee_pct) if paper.taker_fee_pct is not None else None,
        "maker_fee_pct": float(paper.maker_fee_pct) if paper.maker_fee_pct is not None else None,
        "slippage_fallback_pct": float(paper.slippage_fallback_pct) if paper.slippage_fallback_pct is not None else None,
        "positions": engine.positions_as_client_format(paper, prices),
        "pending_orders": engine.open_orders_as_client_format(paper),
    }


def do_reset(db: Session, account_id: int, initial_capital: Optional[float] = None) -> dict:
    from database.models import PaperAccount
    from paper_trading.engine import PaperEngine

    engine = PaperEngine(db)
    paper = db.query(PaperAccount).filter(PaperAccount.account_id == account_id).first()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper account not found")
    engine.reset_cycle(paper, initial_capital=initial_capital)
    db.commit()
    return build_state(db, account_id)


class PaperConfigUpdate(BaseModel):
    initial_capital: Optional[float] = None
    taker_fee_pct: Optional[float] = None
    maker_fee_pct: Optional[float] = None
    slippage_fallback_pct: Optional[float] = None


class PaperResetRequest(BaseModel):
    initial_capital: Optional[float] = None


@router.get("/{account_id}/state")
def get_paper_state(account_id: int, db: Session = Depends(get_db)):
    return build_state(db, account_id)


@router.put("/{account_id}/config")
def update_paper_config(account_id: int, payload: PaperConfigUpdate, db: Session = Depends(get_db)):
    from database.models import PaperAccount
    from paper_trading.engine import PaperEngine

    engine = PaperEngine(db)
    paper = db.query(PaperAccount).filter(PaperAccount.account_id == account_id).first()
    if paper is None:
        paper = engine.get_or_create(account_id, "hyperliquid")

    if payload.initial_capital is not None:
        if payload.initial_capital <= 0:
            raise HTTPException(status_code=400, detail="initial_capital must be > 0")
        if engine.positions(paper):
            raise HTTPException(status_code=400, detail="Cannot change initial capital with open positions; reset instead")
        paper.initial_capital = payload.initial_capital
    if payload.taker_fee_pct is not None:
        paper.taker_fee_pct = payload.taker_fee_pct
    if payload.maker_fee_pct is not None:
        paper.maker_fee_pct = payload.maker_fee_pct
    if payload.slippage_fallback_pct is not None:
        paper.slippage_fallback_pct = payload.slippage_fallback_pct
    db.commit()
    return build_state(db, account_id)


@router.post("/{account_id}/reset")
def reset_paper_account(account_id: int, payload: PaperResetRequest, db: Session = Depends(get_db)):
    return do_reset(db, account_id, initial_capital=payload.initial_capital)
```

`backend/main.py` — 在其他 router import 处加 `from api.paper_trading_routes import router as paper_trading_router`，`app.include_router(market_intelligence_router)`（:766）后加：

```python
app.include_router(paper_trading_router)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; uv run pytest tests/test_paper_routes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/api/paper_trading_routes.py backend/main.py backend/tests/test_paper_routes.py
git commit -m "Add paper trading state/config/reset API routes"
```

---

### Task 13: 盈亏刷新与同步状态接口的 paper 语义

**Files:**
- Modify: `backend/api/arena_routes.py:1398-1404` 与 `:1420-1426`（check-pnl-status 的 "paper" 分支）
- Modify: `backend/api/arena_routes.py` `update_pnl_data`（:1440 起，函数开头加 paper 处理段）

**Interfaces:**
- 行为变更：`trading_mode == "paper"` 的语义从"environment 为 NULL（旧废弃纸交易）"改为 `environment == "paper"`
- `update_pnl_data` 新增：对 environment="paper" 且 `pnl_updated_at IS NULL` 的已执行决策，从快照库 `HyperliquidTrade`（environment="paper"）按 order_id 汇总回填 fee 已有链路（`get_fees_for_decisions` 复用），realized_pnl 从决策自身的 TP/SL 成交记录回填（监控服务已实时回填，此处兜底扫描）

- [ ] **Step 1: 修改 check-pnl-status**

`:1398-1404` 改为：

```python
    if trading_mode:
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment == trading_mode)
    else:
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment.isnot(None))
```

`:1420-1426` 同样改为：

```python
    if trading_mode:
        prog_query = prog_query.filter(ProgramExecutionLog.environment == trading_mode)
    else:
        prog_query = prog_query.filter(ProgramExecutionLog.environment.isnot(None))
```

（regex 校验 `^(paper|testnet|mainnet)$` 不变，"paper" 现在指新纸交易。）

- [ ] **Step 2: update_pnl_data 加 paper 兜底回填**

在 `update_pnl_data`（:1440）函数体开头、处理 Hyperliquid 钱包之前加：

```python
    # ---- Paper trading backfill (no exchange API; fills already in snapshot DB) ----
    try:
        paper_updated = 0
        paper_decisions = db.query(AIDecisionLog).filter(
            AIDecisionLog.hyperliquid_environment == "paper",
            AIDecisionLog.executed == "true",
            AIDecisionLog.operation.in_(["buy", "sell", "close"]),
            AIDecisionLog.pnl_updated_at == None,
        ).all()
        paper_programs = db.query(ProgramExecutionLog).filter(
            ProgramExecutionLog.environment == "paper",
            ProgramExecutionLog.success == True,
            ProgramExecutionLog.decision_action.in_(["buy", "sell", "close"]),
            ProgramExecutionLog.pnl_updated_at == None,
        ).all()

        from database.models import PaperOrder as _PaperOrder

        def _paper_fill_time(order_no):
            if not order_no:
                return None
            po = db.query(_PaperOrder).filter(
                _PaperOrder.order_no == order_no,
                _PaperOrder.status == "filled",
            ).first()
            return po.filled_at if po else None

        for rec in list(paper_decisions) + list(paper_programs):
            # entry orders with TP/SL still pending stay unsynced (position not closed yet)
            filled_time = (
                _paper_fill_time(rec.tp_order_id)
                or _paper_fill_time(rec.sl_order_id)
            )
            if filled_time is not None and rec.realized_pnl is None:
                # monitor normally backfills; this is the safety net for missed fills
                rec.pnl_updated_at = filled_time
                paper_updated += 1
        if paper_updated:
            db.commit()
        result["paper"] = {"backfilled": paper_updated}
    except Exception as e:
        result["errors"].append(f"paper backfill: {e}")
```

- [ ] **Step 3: 验证**

Run: `cd backend; uv run python -c "import api.arena_routes; print('ok')"`
Expected: `ok`

Run: `cd backend; uv run pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/api/arena_routes.py
git commit -m "Point PnL sync paper mode at new paper environment"
```

---

### Task 14: 资产曲线合并 paper + Attribution AI 提示词

**Files:**
- Modify: `backend/services/asset_curve_calculator.py:116-147`（hyperliquid 模式分支合并 paper 曲线）
- Modify: `backend/services/ai_attribution_service.py:36-64`（系统提示词环境枚举加 paper）

**Interfaces:**
- 行为：看板曲线（testnet/mainnet 模式下）额外并入 environment="paper" 的快照曲线；每个 paper 条目带 `"is_paper": True` 且 `username` 后缀 `" [PAPER]"`

- [ ] **Step 1: 合并 paper 曲线**

`backend/services/asset_curve_calculator.py` `get_all_asset_curves_data_new` 的 hyperliquid 分支（:144 `combined = hl_data + binance_data` 之前）加：

```python
        # Paper trading curves always shown alongside real ones (marked)
        paper_data = _build_hyperliquid_asset_curve(
            db,
            bucket_minutes,
            environment="paper",
            wallet_address=None,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
        )
        for item in paper_data:
            item["is_paper"] = True
            if item.get("username") and not str(item["username"]).endswith(" [PAPER]"):
                item["username"] = f"{item['username']} [PAPER]"
```

并把合并行改为：

```python
        combined = hl_data + binance_data + paper_data
```

注意 `_build_hyperliquid_asset_curve`（:225 起）内部若对 environment 做了 `in ("testnet", "mainnet")` 之类的白名单校验，需放行 "paper"（实现时检查该函数体，按需放宽过滤条件——它按 `HyperliquidAccountSnapshot.environment == environment` 查询即可命中 paper 快照）。

- [ ] **Step 2: Attribution AI 提示词**

`backend/services/ai_attribution_service.py` ATTRIBUTION_SYSTEM_PROMPT 中：

`2. **Environment** (for both exchanges):` 小节的两行改为三行：

```
   - **testnet**: Test network trades (exchange test funds)
   - **mainnet**: Real money trades
   - **paper**: Internal paper trading (simulated fills on mainnet data)
```

同文件中 `Ask the user: "Which exchange do you want to analyze ..."` 的引导句和 `GUIDED CONVERSATION` 小节里的 `(testnet or mainnet)` 全部改为 `(testnet, mainnet or paper)`。同时全文搜索该文件内工具参数描述中的 `"testnet" | "mainnet"` 或 `testnet/mainnet` 枚举字样，追加 paper。

- [ ] **Step 3: 验证**

Run: `cd backend; uv run python -c "import services.asset_curve_calculator, services.ai_attribution_service; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/services/asset_curve_calculator.py backend/services/ai_attribution_service.py
git commit -m "Show paper curves on dashboard and teach attribution AI paper env"
```

---

### Task 15: 前端（执行模式开关、纸交易账户卡片、归因筛选、i18n）

**Files:**
- Modify: `frontend/app/components/portfolio/StrategyPanel.tsx`（:17-28 接口、:82 状态、:125 加载、:256 保存、:388-398 之后新增执行模式 UI）
- Create: `frontend/app/components/trader/PaperAccountSection.tsx`
- Modify: `frontend/app/components/trader/ExchangeWalletsPanel.tsx`（面板末尾渲染 PaperAccountSection）
- Modify: `frontend/app/components/analytics/AttributionAnalysis.tsx:380-386`（环境筛选加 Paper）
- Modify: `frontend/app/i18n.ts`（中英文案）

**Interfaces:**
- Consumes: Task 8 的 `execution_mode` 字段（GET/PUT 策略配置）、Task 12 的 `/api/paper-trading/*` 路由

- [ ] **Step 1: StrategyPanel 执行模式**

`StrategyConfig` 接口（:17-28）加：

```typescript
  execution_mode?: string  // "real" or "paper"
```

状态（:82 附近）加：

```typescript
  const [executionMode, setExecutionMode] = useState<string>('real')
```

加载（:125 后）加：

```typescript
        setExecutionMode(strategy.execution_mode ?? 'real')
```

保存 payload（:256 `exchange: exchange,` 后）加：

```typescript
        execution_mode: executionMode,
```

保存成功回填处（:278 附近，`setExchange(result.exchange ?? 'hyperliquid')` 后）加：

```typescript
      setExecutionMode(result.execution_mode ?? 'real')
```

useEffect 依赖数组（:287）加 `executionMode`。

交易所 Select 块（:388-398）之后新增：

```tsx
                <div className="space-y-1.5">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">
                    {t('strategy.executionMode', 'Execution Mode')}
                  </div>
                  <Select value={executionMode} onValueChange={(value) => { setExecutionMode(value); resetMessages() }}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('strategy.selectExecutionMode', 'Select execution mode')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="real">{t('strategy.executionReal', 'Live Trading')}</SelectItem>
                      <SelectItem value="paper">{t('strategy.executionPaper', 'Paper Trading')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {executionMode === 'paper'
                      ? t('strategy.executionPaperHint', 'Simulated fills on live mainnet data. No wallet required.')
                      : t('strategy.executionRealHint', 'Orders are sent to the real exchange.')}
                  </p>
                </div>
```

- [ ] **Step 2: PaperAccountSection 组件**

`frontend/app/components/trader/PaperAccountSection.tsx`：

```tsx
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { RefreshCw, RotateCcw } from 'lucide-react'

interface PaperState {
  configured: boolean
  account_id: number
  data_exchange?: string
  cycle?: number
  initial_capital?: number
  total_equity?: number
  available_balance?: number
  unrealized_pnl?: number
  cycle_return_pct?: number
  positions?: any[]
}

export default function PaperAccountSection({ accountId }: { accountId: number }) {
  const { t } = useTranslation()
  const [state, setState] = useState<PaperState | null>(null)
  const [loading, setLoading] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [initialCapital, setInitialCapital] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`/api/paper-trading/${accountId}/state`)
      if (resp.ok) {
        const data = await resp.json()
        setState(data)
        if (data.initial_capital) setInitialCapital(String(data.initial_capital))
      }
    } catch (e) {
      console.error('Failed to load paper state:', e)
    } finally {
      setLoading(false)
    }
  }, [accountId])

  useEffect(() => { load() }, [load])

  const handleReset = async () => {
    const confirmed = window.confirm(
      t('paper.resetConfirm',
        'Reset paper account? Positions and pending orders are cleared, equity returns to initial capital, and a new cycle starts. History is preserved.')
    )
    if (!confirmed) return
    setResetting(true)
    try {
      const capital = parseFloat(initialCapital)
      const resp = await fetch(`/api/paper-trading/${accountId}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Number.isFinite(capital) && capital > 0 ? { initial_capital: capital } : {}),
      })
      if (resp.ok) setState(await resp.json())
    } catch (e) {
      console.error('Failed to reset paper account:', e)
    } finally {
      setResetting(false)
    }
  }

  if (!state?.configured) {
    return (
      <div className="border rounded-lg p-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="secondary" className="text-[10px]">PAPER</Badge>
          <span className="font-medium text-foreground">{t('paper.title', 'Paper Trading Account')}</span>
        </div>
        {t('paper.notConfigured', 'Enable Paper Trading in the strategy config. The account is created on first trade.')}
      </div>
    )
  }

  const pnlColor = (state.cycle_return_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-[10px]">PAPER</Badge>
          <span className="text-sm font-medium">{t('paper.title', 'Paper Trading Account')}</span>
          <span className="text-xs text-muted-foreground">
            {t('paper.cycle', 'Cycle')} #{state.cycle} · {state.data_exchange}
          </span>
        </div>
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={load} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">{t('paper.equity', 'Equity')}</div>
          <div className="font-mono font-medium">${state.total_equity?.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t('paper.available', 'Available')}</div>
          <div className="font-mono">${state.available_balance?.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t('paper.cycleReturn', 'Cycle Return')}</div>
          <div className={`font-mono font-medium ${pnlColor}`}>
            {(state.cycle_return_pct ?? 0) >= 0 ? '+' : ''}{state.cycle_return_pct}%
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <input
          type="number"
          value={initialCapital}
          onChange={(e) => setInitialCapital(e.target.value)}
          className="w-28 border border-border rounded px-2 py-1 text-xs bg-background"
          placeholder="10000"
        />
        <span className="text-xs text-muted-foreground">{t('paper.initialCapital', 'Initial capital (USD)')}</span>
        <Button variant="outline" size="sm" className="h-7 ml-auto text-xs" onClick={handleReset} disabled={resetting}>
          <RotateCcw className="h-3 w-3 mr-1" />
          {t('paper.reset', 'Reset')}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 挂载到 ExchangeWalletsPanel**

`frontend/app/components/trader/ExchangeWalletsPanel.tsx`：顶部 `import PaperAccountSection from './PaperAccountSection'`；组件 JSX 中 Binance 钱包 section 之后（面板根容器内最后）加：

```tsx
      <PaperAccountSection accountId={accountId} />
```

（该组件的 props 中已有交易员 account id——以文件内实际 prop 名为准，若为 `traderId`/`account.id` 则相应传入。）

- [ ] **Step 4: 归因分析筛选加 Paper**

`frontend/app/components/analytics/AttributionAnalysis.tsx` :385-386 的两个 SelectItem 后加：

```tsx
              <SelectItem value="paper">Paper</SelectItem>
```

- [ ] **Step 5: i18n 文案**

`frontend/app/i18n.ts` 中文资源块加（英文块加对应英文；键名与上面组件一致）：

```typescript
      strategy: {
        // ...existing keys...
        executionMode: '执行模式',
        selectExecutionMode: '选择执行模式',
        executionReal: '实盘交易',
        executionPaper: '纸交易',
        executionPaperHint: '使用主网实时行情模拟撮合，无需配置钱包。',
        executionRealHint: '订单发送到真实交易所。',
      },
      paper: {
        title: '纸交易账户',
        notConfigured: '在策略配置中选择"纸交易"执行模式，首次交易时自动创建账户。',
        cycle: '周期',
        equity: '模拟权益',
        available: '可用余额',
        cycleReturn: '本周期收益',
        initialCapital: '初始资金 (USD)',
        reset: '重置',
        resetConfirm: '确定重置纸交易账户？将清空持仓和挂单、权益回到初始资金并开启新周期，历史记录保留。',
      },
```

（按 i18n.ts 实际结构合并——若已有 `strategy` 命名空间则只追加新键。）

- [ ] **Step 6: 构建验证**

Run: `cd frontend; npm run build`
Expected: 构建成功无 TS 错误

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/portfolio/StrategyPanel.tsx frontend/app/components/trader/PaperAccountSection.tsx frontend/app/components/trader/ExchangeWalletsPanel.tsx frontend/app/components/analytics/AttributionAnalysis.tsx frontend/app/i18n.ts
git commit -m "Add paper trading UI: execution mode, account card, filters"
```

---

### Task 16: 端到端集成验证

**Files:**
- Test: `backend/tests/test_paper_integration.py`
- 手动验证清单（无代码）

**Interfaces:** 无新接口；串联验证 Task 1-15。

- [ ] **Step 1: 写集成测试（决策→引擎→日志→归因数据一致）**

`backend/tests/test_paper_integration.py`：

```python
"""End-to-end: paper order -> decision log -> TP trigger -> PnL backfill consistency."""
import pytest


def test_full_paper_trade_lifecycle(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from database.models import User, Account, AIDecisionLog
    from database.snapshot_models import HyperliquidTrade
    from paper_trading.engine import PaperEngine
    from paper_trading.monitor import PaperMonitor

    u = User(username="e2e")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="E2E", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    engine = PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)
    paper = engine.get_or_create(account.id, "hyperliquid")

    # 1. open with TP (as the AI pipeline would)
    result = engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    assert result["status"] == "filled"

    # 2. decision log records paper environment + order ids (as pipeline does)
    log = AIDecisionLog(
        account_id=account.id, reason="e2e", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper", exchange="hyperliquid",
        hyperliquid_order_id=result["order_id"], tp_order_id=result["tp_order_id"],
    )
    db_session.add(log)
    db_session.flush()

    # 3. monitor sweep triggers TP and backfills PnL
    monitor = PaperMonitor()
    fills = monitor._sweep_account(db_session, engine, paper, {"BTC": 111000.0})
    for f in fills:
        monitor._backfill_decision_pnl(db_session, f)
    db_session.flush()

    assert float(log.realized_pnl) == pytest.approx(1000.0)
    assert log.pnl_updated_at is not None

    # 4. fills in snapshot DB carry environment=paper and fees (attribution source)
    sdb = snapshot_session_factory()
    trades = sdb.query(HyperliquidTrade).all()
    assert all(t.environment == "paper" for t in trades)
    assert len(trades) == 2  # open fill + tp close fill
    total_fee = sum(float(t.fee) for t in trades)
    sdb.close()

    # 5. equity accounting consistent: 10000 + 1000 - fees
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == pytest.approx(10000 + 1000 - total_fee)
```

- [ ] **Step 2: 运行全量测试**

Run: `cd backend; uv run pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 手动端到端验证（应用运行于 http://127.0.0.1:8802）**

1. 重启后端使迁移生效，确认日志出现 `Paper trading monitor started`
2. AI交易员页 → 策略配置 → 某交易员选"执行模式：纸交易"并保存
3. 交易员卡片出现"纸交易账户"卡片，权益 $10,000
4. 手动触发一次该交易员决策（策略配置页的触发按钮或等定时触发），确认：决策日志生成、纸交易卡片权益/持仓变化
5. 归因分析页 → 环境选 Paper → 能看到该笔决策，手续费非零
6. 数据看板资产曲线出现 `<名称> [PAPER]` 曲线
7. 纸交易卡片点"重置"→ 权益回到初始资金、周期 #2、归因历史仍在

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_paper_integration.py
git commit -m "Add paper trading end-to-end integration test"
```

---

## Self-Review 记录

- **规格覆盖**：spec §3 模块（Task 2/3/4-6/7/11）、§4 数据模型（Task 1）、§5 撮合规则（Task 4/5/6）、§6 管线（Task 9/10）、§6.4 盈亏回填（Task 9 Step 5d + Task 11 + Task 13）、§7 归因（Task 13/14/15）、§8 看板（Task 11 快照 + Task 14）、§9 前端（Task 15）、§10 错误处理（引擎 error 结构/监控 catch-up/行锁贯穿各任务）、§11 测试（各任务 TDD + Task 16）
- **范围界定（spec §9 徽章）**：数据看板曲线的 PAPER 标识由后端 `is_paper` 字段 + `username` 后缀 `" [PAPER]"` 实现（Task 14），交易员管理页由纸交易账户卡片承担标识（Task 15）；Arena 像素视图与排行榜内的独立 PAPER 徽章依赖对 arena/ranking 数据源的进一步梳理，不在本计划任务内——如需补齐，在 Task 16 手动验证发现缺口后追加独立小任务
- **已知留给执行者核实的点**（均在任务内标注）：`SymbolMapper.to_exchange` 确切签名、`User` 模型必填字段、`_load_strategies` 中 StrategyState 构造的确切行号、ExchangeWalletsPanel 的 account id prop 名、i18n.ts 资源结构、`_build_hyperliquid_asset_curve` 内部 environment 白名单
- **类型一致性**：`place_order(paper, symbol, is_buy, size, limit_price, market_price, ...)`、`trigger_order(paper, order, mark_price)`、fill dict 键 `{order_no, symbol, qty, price, fee, realized_pnl, exit_reason}`、client 返回键与真实 client 对齐——已在 Task 4/5/7/11/16 间交叉核对
