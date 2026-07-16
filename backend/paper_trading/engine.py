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
        # Deterministic order: when a single candle's low/high could trigger both
        # a TP and an SL for the same position, order-creation order decides which
        # fires first, rather than arbitrary row order.
        return q.order_by(PaperOrder.id).all()

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
        mark_prices: Optional[Dict[str, float]] = None,
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

        fill = self._fill(paper, symbol, side, size, leverage, reduce_only, fill_price, rates["taker"],
                          mark_prices=mark_prices)
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
        mark_prices: Optional[Dict[str, float]] = None,
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
            gate_prices = dict(mark_prices or {})
            gate_prices[symbol] = fill_price
            state = self.compute_state(paper, gate_prices)
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
        record_status: str = "filled",
    ) -> tuple:
        """Close qty of pos at exit_price. Returns (gross_pnl, fee). Deletes position when emptied."""
        qty = min(qty, float(pos.size))
        entry = float(pos.entry_price)
        pnl = (exit_price - entry) * qty if pos.side == "long" else (entry - exit_price) * qty
        fee = fee_mod.calc_fee(qty * exit_price, fee_rate_pct)
        paper.realized_pnl_total = float(paper.realized_pnl_total) + pnl
        paper.total_fees = float(paper.total_fees) + fee
        close_side = "sell" if pos.side == "long" else "buy"
        self._record_fill(
            paper, pos.symbol, close_side, qty, exit_price, int(pos.leverage), order_no, fee,
            order_status=record_status,
        )
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
        order_status: str = "filled",
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
                    order_status=order_status,
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

    def trigger_order(self, paper: PaperAccount, order: PaperOrder, mark_price: float, mark_prices: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
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
                mark_prices=mark_prices,
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
            pnl, fee = self._close_qty(
                paper, pos, float(pos.size), exit_px, rates["taker"], order_no,
                record_status="liquidation",
            )
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
