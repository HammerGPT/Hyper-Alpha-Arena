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
    paper = (
        db.query(PaperAccount)
        .filter(PaperAccount.account_id == account_id)
        .with_for_update()
        .first()
    )
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
    paper = (
        db.query(PaperAccount)
        .filter(PaperAccount.account_id == account_id)
        .with_for_update()
        .first()
    )
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
