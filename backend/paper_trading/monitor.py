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
        # Collect ids first, then re-fetch each account row-locked inside its own
        # try block. Locking the plain query result directly would hold every
        # account's row for the whole sweep and doesn't protect against another
        # writer (e.g. a route handler) racing a single account between the
        # initial query and this account's turn -- re-fetching per-account with
        # with_for_update() closes that lost-update window.
        paper_ids = [p.id for p in db.query(PaperAccount.id).all()]
        for paper_id in paper_ids:
            try:
                paper = (
                    db.query(PaperAccount)
                    .filter(PaperAccount.id == paper_id)
                    .with_for_update()
                    .first()
                )
                if paper is None:
                    continue
                symbols = {p.symbol for p in engine.positions(paper)}
                symbols |= {o.symbol for o in engine.pending_orders(paper)}
                if not symbols:
                    paper.last_monitor_at = datetime.utcnow()
                    db.commit()
                    continue
                prices = self._get_prices(paper.data_exchange, sorted(symbols))
                if not prices:
                    # Price outage: don't advance last_monitor_at so a later
                    # catch-up can replay this window once prices recover.
                    logger.warning(
                        f"[PAPER MONITOR] Account {paper.account_id} sweep skipped: "
                        f"no prices for symbols {sorted(symbols)}"
                    )
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
                logger.error(f"[PAPER MONITOR] Account (paper_id={paper_id}) sweep failed: {e}", exc_info=True)

    def _sweep_account(self, db: Session, engine, paper, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        fills = []
        for order in list(engine.pending_orders(paper)):
            px = prices.get(order.symbol)
            if not px:
                continue
            fill = engine.trigger_order(paper, order, px, mark_prices=prices)
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
        # Same lost-update guard as run_once: collect ids first, then re-fetch
        # each account row-locked inside its own try block.
        paper_ids = [p.id for p in db.query(PaperAccount.id).all()]
        for paper_id in paper_ids:
            try:
                paper = (
                    db.query(PaperAccount)
                    .filter(PaperAccount.id == paper_id)
                    .with_for_update()
                    .first()
                )
                if paper is None:
                    continue
                self.catch_up(db, engine, paper)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"[PAPER MONITOR] Catch-up failed for paper_id={paper_id}: {e}")

    def catch_up(self, db: Session, engine, paper) -> None:
        """Replay 1m kline highs/lows since last_monitor_at through pending orders.

        Note: at 1m kline granularity, the intra-candle path (whether price hit
        the low or high first) is unknowable, so if both a TP and an SL could
        trigger within the same candle, resolution falls back to
        PaperEngine.pending_orders' deterministic order-by-id ordering rather
        than the true (unknown) intra-candle sequence.
        """
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
                try:
                    symbols = [p.symbol for p in engine.positions(paper)]
                    prices = self._get_prices(paper.data_exchange, symbols) if symbols else {}
                    # Price outage: an account with open positions whose prices we
                    # couldn't fetch would otherwise snapshot with those positions'
                    # unrealized PnL silently dropped (missing price -> excluded
                    # from unrealized_pnl/used_margin), distorting equity for this
                    # round. Accounts with no positions have nothing that needs a
                    # price, so an empty prices dict is fine for them.
                    missing = [s for s in symbols if s not in prices]
                    if missing:
                        logger.debug(
                            f"[PAPER MONITOR] Snapshot skipped for account {paper.account_id}: "
                            f"no prices for {missing}"
                        )
                        continue
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
                except Exception as e:
                    logger.error(f"[PAPER MONITOR] Snapshot failed for account {paper.account_id}: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
            sdb.commit()
        except Exception as e:
            sdb.rollback()
            logger.error(f"[PAPER MONITOR] Snapshot commit failed: {e}")
        finally:
            sdb.close()


paper_monitor = PaperMonitor()
