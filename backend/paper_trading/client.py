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
        position_symbols = [p.symbol for p in engine.positions(paper) if p.symbol != symbol]
        mark_prices = self._prices_for(db, position_symbols) if position_symbols else None
        result = engine.place_order(
            paper, symbol, is_buy, size,
            limit_price=price, market_price=market_price,
            leverage=leverage, time_in_force=time_in_force, reduce_only=reduce_only,
            take_profit_price=take_profit_price, stop_loss_price=stop_loss_price,
            tp_execution=tp_execution, sl_execution=sl_execution,
            mark_prices=mark_prices,
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

    def close_position(
        self,
        symbol: str,
        cancel_tpsl: bool = True,
        db: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Close the entire position for `symbol` via a reduce-only IOC order.

        Mirrors BinanceTradingClient.close_position's call signature
        (symbol, cancel_tpsl), but pipeline call sites invoke it without a
        db session (`client.close_position(symbol, cancel_tpsl=True)`), so
        this method self-manages one when the caller doesn't supply it.
        """
        owns_session = db is None
        if owns_session:
            from database.connection import SessionLocal
            db = SessionLocal()
        try:
            symbol = symbol.upper()
            engine = self._engine(db)
            paper = engine.get_or_create(self.account_id, self.data_exchange)
            position = next((p for p in engine.positions(paper) if p.symbol == symbol), None)
            if position is None:
                logger.info(f"[PAPER {self.data_exchange.upper()}] No position to close for {symbol}")
                return None

            is_long = position.side == "long"
            size = float(position.size)
            leverage = int(position.leverage)

            market_price = _get_last_price(symbol, self.data_exchange)
            if not market_price:
                return {
                    "status": "error",
                    "error": f"Unable to get market price for {symbol}",
                    "environment": "paper",
                    "symbol": symbol,
                }

            position_symbols = [p.symbol for p in engine.positions(paper) if p.symbol != symbol]
            mark_prices = self._prices_for(db, position_symbols) if position_symbols else None

            # Apply 1% tolerance in fill direction to account for real orderbook slippage.
            # Closing a LONG (sell): buyer walks the bid side, so limit lower (0.99).
            # Closing a SHORT (buy): seller walks the ask side, so limit higher (1.01).
            # This mirrors the trading pipeline's ±1% oracle price window.
            limit_price = market_price * 0.99 if is_long else market_price * 1.01

            fill = engine.place_order(
                paper, symbol, is_buy=not is_long, size=size,
                limit_price=limit_price, market_price=market_price,
                leverage=leverage, time_in_force="Ioc", reduce_only=True,
                mark_prices=mark_prices,
            )

            if cancel_tpsl:
                for order in engine.pending_orders(paper, symbol):
                    engine.cancel_order(paper, order.order_no)

            db.commit()
            logger.info(
                f"[PAPER {self.data_exchange.upper()}] CLOSE {symbol} "
                f"status={fill.get('status')} avg={fill.get('average_price')}"
            )

            return {
                "status": fill.get("status"),
                "order_id": fill.get("order_id"),
                "symbol": symbol,
                "side": "sell" if is_long else "buy",
                "filled_qty": fill.get("filled_amount", 0.0),
                "avg_price": fill.get("average_price", 0.0),
                "quantity": size,
                "environment": "paper",
                "realized_pnl": fill.get("realized_pnl", 0.0),
                "fee": fill.get("fee", 0.0),
                "error": fill.get("error"),
            }
        finally:
            if owns_session:
                db.close()
