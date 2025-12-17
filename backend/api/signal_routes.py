"""Signal system API routes"""
from __future__ import annotations

from typing import List, Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import SignalDefinition, SignalPool, SignalTriggerLog, User
from schemas.signal import (
    SignalDefinitionCreate,
    SignalDefinitionUpdate,
    SignalDefinitionResponse,
    SignalPoolCreate,
    SignalPoolUpdate,
    SignalPoolResponse,
    SignalListResponse,
    SignalTriggerLogResponse,
    SignalTriggerLogsResponse,
)

router = APIRouter(prefix="/api/signals", tags=["Signal System"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============ Signal Definitions ============

@router.get("", response_model=SignalListResponse)
@router.get("/", response_model=SignalListResponse)
def list_signals(db: Session = Depends(get_db)) -> SignalListResponse:
    """List all signal definitions and pools"""
    signals_result = db.query(SignalDefinition).order_by(SignalDefinition.id).all()
    signals = []
    for row in signals_result:
        # Parse trigger_condition from JSON string if needed
        trigger_condition = row.trigger_condition
        if isinstance(trigger_condition, str):
            trigger_condition = json.loads(trigger_condition)
        signals.append(SignalDefinitionResponse(
            id=row.id, signal_name=row.signal_name, description=row.description,
            trigger_condition=trigger_condition, enabled=row.enabled,
            created_at=row.created_at, updated_at=row.updated_at
        ))

    pools_result = db.query(SignalPool).order_by(SignalPool.id).all()
    pools = []
    for row in pools_result:
        # Parse JSON fields if they are strings
        signal_ids = row.signal_ids
        if isinstance(signal_ids, str):
            signal_ids = json.loads(signal_ids)
        symbols = row.symbols
        if isinstance(symbols, str):
            symbols = json.loads(symbols)
        pools.append(SignalPoolResponse(
            id=row.id, pool_name=row.pool_name, signal_ids=signal_ids or [],
            symbols=symbols or [], enabled=row.enabled, created_at=row.created_at,
            logic=row.logic or "OR"
        ))

    return SignalListResponse(signals=signals, pools=pools)


@router.post("/definitions", response_model=SignalDefinitionResponse)
def create_signal(payload: SignalDefinitionCreate, db: Session = Depends(get_db)):
    """Create a new signal definition"""
    result = SignalDefinition(
        signal_name=payload.signal_name,
        description=payload.description,
        trigger_condition=json.dumps(payload.trigger_condition),
        enabled=payload.enabled
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    
    trigger_condition = result.trigger_condition
    if isinstance(trigger_condition, str):
        trigger_condition = json.loads(trigger_condition)
    return SignalDefinitionResponse(
        id=result.id, signal_name=result.signal_name, description=result.description,
        trigger_condition=trigger_condition, enabled=result.enabled,
        created_at=result.created_at, updated_at=result.updated_at
    )


@router.get("/definitions/{signal_id}", response_model=SignalDefinitionResponse)
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    """Get a signal definition by ID"""
    result = db.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found")
    
    trigger_condition = result.trigger_condition
    if isinstance(trigger_condition, str):
        trigger_condition = json.loads(trigger_condition)
    return SignalDefinitionResponse(
        id=result.id, signal_name=result.signal_name, description=result.description,
        trigger_condition=trigger_condition, enabled=result.enabled,
        created_at=result.created_at, updated_at=result.updated_at
    )


@router.put("/definitions/{signal_id}", response_model=SignalDefinitionResponse)
def update_signal(signal_id: int, payload: SignalDefinitionUpdate, db: Session = Depends(get_db)):
    """Update a signal definition"""
    result = db.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found")
    
    if payload.signal_name is not None:
        result.signal_name = payload.signal_name
    if payload.description is not None:
        result.description = payload.description
    if payload.trigger_condition is not None:
        result.trigger_condition = json.dumps(payload.trigger_condition)
    if payload.enabled is not None:
        result.enabled = payload.enabled
    
    db.commit()
    db.refresh(result)
    
    trigger_condition = result.trigger_condition
    if isinstance(trigger_condition, str):
        trigger_condition = json.loads(trigger_condition)
    return SignalDefinitionResponse(
        id=result.id, signal_name=result.signal_name, description=result.description,
        trigger_condition=trigger_condition, enabled=result.enabled,
        created_at=result.created_at, updated_at=result.updated_at
    )


@router.delete("/definitions/{signal_id}")
def delete_signal(signal_id: int, db: Session = Depends(get_db)):
    """Delete a signal definition"""
    result = db.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found")
    db.delete(result)
    db.commit()
    return {"message": "Signal deleted successfully"}


# ============ Signal Pools ============

@router.post("/pools", response_model=SignalPoolResponse)
def create_pool(payload: SignalPoolCreate, db: Session = Depends(get_db)):
    """Create a new signal pool"""
    result = SignalPool(
        pool_name=payload.pool_name,
        signal_ids=json.dumps(payload.signal_ids),
        symbols=json.dumps(payload.symbols),
        enabled=payload.enabled,
        logic=payload.logic
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    
    signal_ids = result.signal_ids
    if isinstance(signal_ids, str):
        signal_ids = json.loads(signal_ids)
    symbols = result.symbols
    if isinstance(symbols, str):
        symbols = json.loads(symbols)
    return SignalPoolResponse(
        id=result.id, pool_name=result.pool_name, signal_ids=signal_ids or [],
        symbols=symbols or [], enabled=result.enabled, created_at=result.created_at,
        logic=result.logic or "OR"
    )


@router.get("/pools/{pool_id}", response_model=SignalPoolResponse)
def get_pool(pool_id: int, db: Session = Depends(get_db)):
    """Get a signal pool by ID"""
    result = db.query(SignalPool).filter(SignalPool.id == pool_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    signal_ids = result.signal_ids
    if isinstance(signal_ids, str):
        signal_ids = json.loads(signal_ids)
    symbols = result.symbols
    if isinstance(symbols, str):
        symbols = json.loads(symbols)
    return SignalPoolResponse(
        id=result.id, pool_name=result.pool_name, signal_ids=signal_ids or [],
        symbols=symbols or [], enabled=result.enabled, created_at=result.created_at,
        logic=result.logic or "OR"
    )


@router.put("/pools/{pool_id}", response_model=SignalPoolResponse)
def update_pool(pool_id: int, payload: SignalPoolUpdate, db: Session = Depends(get_db)):
    """Update a signal pool"""
    result = db.query(SignalPool).filter(SignalPool.id == pool_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    if payload.pool_name is not None:
        result.pool_name = payload.pool_name
    if payload.signal_ids is not None:
        result.signal_ids = json.dumps(payload.signal_ids)
    if payload.symbols is not None:
        result.symbols = json.dumps(payload.symbols)
    if payload.enabled is not None:
        result.enabled = payload.enabled
    if payload.logic is not None:
        result.logic = payload.logic
    
    db.commit()
    db.refresh(result)
    
    signal_ids = result.signal_ids
    if isinstance(signal_ids, str):
        signal_ids = json.loads(signal_ids)
    symbols = result.symbols
    if isinstance(symbols, str):
        symbols = json.loads(symbols)
    return SignalPoolResponse(
        id=result.id, pool_name=result.pool_name, signal_ids=signal_ids or [],
        symbols=symbols or [], enabled=result.enabled, created_at=result.created_at,
        logic=result.logic or "OR"
    )


@router.delete("/pools/{pool_id}")
def delete_pool(pool_id: int, db: Session = Depends(get_db)):
    """Delete a signal pool"""
    result = db.query(SignalPool).filter(SignalPool.id == pool_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Pool not found")
    db.delete(result)
    db.commit()
    return {"message": "Pool deleted successfully"}


# ============ Metric Analysis ============

@router.get("/analyze")
def analyze_metric(
    symbol: str = Query(..., description="Trading symbol (e.g., BTC)"),
    metric: str = Query(..., description="Metric type (e.g., oi_delta_percent)"),
    period: str = Query("5m", description="Time period (e.g., 5m, 15m)"),
    days: int = Query(7, le=30, description="Days of history to analyze"),
    db: Session = Depends(get_db)
):
    """
    Analyze a metric and provide statistical summary with threshold suggestions.

    Returns statistics and suggested thresholds based on historical data.
    """
    from services.signal_analysis_service import signal_analysis_service

    result = signal_analysis_service.analyze_metric(db, symbol, metric, period, days)
    return result


# ============ Signal Backtest Preview ============

@router.get("/backtest/{signal_id}")
def backtest_signal(
    signal_id: int,
    symbol: str = Query(..., description="Trading symbol (e.g., BTC)"),
    kline_min_ts: int = Query(None, description="Min K-line timestamp in ms (for filtering triggers)"),
    kline_max_ts: int = Query(None, description="Max K-line timestamp in ms (for filtering triggers)"),
    db: Session = Depends(get_db)
):
    """
    Backtest a signal against historical data.
    Returns only trigger points - K-lines should be fetched via /api/market/kline-with-indicators.
    """
    from services.signal_backtest_service import signal_backtest_service

    result = signal_backtest_service.backtest_signal(db, signal_id, symbol, kline_min_ts, kline_max_ts)
    return result


from pydantic import BaseModel, Field


class TempBacktestRequest(BaseModel):
    """Request for temporary signal backtest (without saving to database)"""
    symbol: str = Field(..., description="Trading symbol (e.g., BTC)")
    trigger_condition: dict = Field(..., alias="triggerCondition", description="Signal trigger condition")
    kline_min_ts: Optional[int] = Field(None, alias="klineMinTs", description="Min K-line timestamp in ms")
    kline_max_ts: Optional[int] = Field(None, alias="klineMaxTs", description="Max K-line timestamp in ms")

    class Config:
        populate_by_name = True


@router.post("/backtest-preview")
def backtest_preview(
    request: TempBacktestRequest,
    db: Session = Depends(get_db)
):
    """
    Backtest a signal configuration without saving to database.
    Used for AI signal creation preview before actually creating the signal.
    """
    from services.signal_backtest_service import signal_backtest_service

    result = signal_backtest_service.backtest_temp_signal(
        db=db,
        symbol=request.symbol,
        trigger_condition=request.trigger_condition,
        kline_min_ts=request.kline_min_ts,
        kline_max_ts=request.kline_max_ts
    )
    return result


@router.get("/pool-backtest/{pool_id}")
def backtest_pool(
    pool_id: int,
    symbol: str = Query(..., description="Trading symbol (e.g., BTC)"),
    kline_min_ts: int = Query(None, description="Min K-line timestamp in ms"),
    kline_max_ts: int = Query(None, description="Max K-line timestamp in ms"),
    db: Session = Depends(get_db)
):
    """
    Backtest a signal pool against historical data.
    Combines triggers from multiple signals based on pool logic (AND/OR).
    """
    from services.signal_backtest_service import signal_backtest_service

    result = signal_backtest_service.backtest_pool(db, pool_id, symbol, kline_min_ts, kline_max_ts)
    return result


# ============ Trigger Logs ============

@router.get("/logs", response_model=SignalTriggerLogsResponse)
def get_trigger_logs(
    pool_id: Optional[int] = Query(None),
    signal_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    """Get signal trigger logs with optional filters"""
    result = db.query(SignalTriggerLog)
    
    if pool_id is not None:
        result = result.filter(SignalTriggerLog.pool_id == pool_id)
    if signal_id is not None:
        result = result.filter(SignalTriggerLog.signal_id == signal_id)
    if symbol is not None:
        result = result.filter(SignalTriggerLog.symbol == symbol)
    
    total = result.count()
    result = result.order_by(SignalTriggerLog.triggered_at.desc()).limit(limit).all()
    
    logs = []
    for row in result:
        logs.append(SignalTriggerLogResponse(
            id=row.id, signal_id=row.signal_id, pool_id=row.pool_id,
            symbol=row.symbol, trigger_value=row.trigger_value, triggered_at=row.triggered_at
        ))

    return SignalTriggerLogsResponse(logs=logs, total=total)


# ============ Signal Testing & Monitoring ============

@router.get("/test/{signal_id}")
def test_signal(
    signal_id: int,
    symbol: str = Query(..., description="Symbol to test against"),
    db: Session = Depends(get_db)
):
    """
    Test a signal against current market data.
    Returns the current metric value and whether the condition is met.
    """
    from services.signal_detection_service import signal_detection_service
    from services.market_flow_collector import market_flow_collector

    # Get signal definition
    result = db.query(SignalDefinition).filter(SignalDefinition.id == signal_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_def = {
        "id": result.id,
        "signal_name": result.signal_name,
        "description": result.description,
        "trigger_condition": result.trigger_condition,
        "enabled": result.enabled
    }

    # Get current market data from collector
    market_data = {
        "asset_ctx": market_flow_collector.latest_asset_ctx.get(symbol, {}),
        "orderbook": market_flow_collector.latest_orderbook.get(symbol, {}),
    }

    condition = signal_def.get("trigger_condition", {})
    metric = condition.get("metric")
    operator = condition.get("operator")
    threshold = condition.get("threshold")
    time_window = condition.get("time_window", 60)

    # Get current metric value
    current_value = signal_detection_service._get_metric_value(
        metric, symbol, market_data, time_window
    )

    # Evaluate condition
    condition_met = False
    if current_value is not None:
        condition_met = signal_detection_service._evaluate_condition(
            current_value, operator, threshold
        )

    # Get signal state
    state_key = (signal_id, symbol)
    state = signal_detection_service.signal_states.get(state_key)

    return {
        "signal_id": signal_id,
        "signal_name": signal_def["signal_name"],
        "symbol": symbol,
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "time_window": time_window,
        "current_value": current_value,
        "condition_met": condition_met,
        "is_active": state.is_active if state else False,
        "would_trigger": condition_met and (not state or not state.is_active),
        "market_data_available": bool(market_data.get("asset_ctx")),
    }


@router.get("/states")
def get_signal_states():
    """Get current signal states for monitoring"""
    from services.signal_detection_service import signal_detection_service
    return {
        "states": signal_detection_service.get_signal_states(),
        "cache_info": {
            "pools_count": len(signal_detection_service._signal_pools_cache),
            "signals_count": len(signal_detection_service._signals_cache),
        }
    }


@router.post("/states/reset")
def reset_signal_states(
    signal_id: Optional[int] = Query(None),
    pool_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None)
):
    """Reset signal and pool states (useful for testing)"""
    from services.signal_detection_service import signal_detection_service
    signal_detection_service.reset_state(signal_id, pool_id, symbol)
    return {"message": "Signal and pool states reset successfully"}


# ============ AI Signal Generation Chat APIs ============

from fastapi.responses import StreamingResponse
from services.ai_signal_generation_service import (
    generate_signal_with_ai,
    generate_signal_with_ai_stream,
    get_signal_conversation_history,
    get_signal_conversation_messages
)


class AiSignalChatRequest(BaseModel):
    """Request to send a message to AI signal generation chat"""
    account_id: int = Field(..., alias="accountId")
    user_message: str = Field(..., alias="userMessage")
    conversation_id: Optional[int] = Field(None, alias="conversationId")

    class Config:
        populate_by_name = True


class AiSignalChatResponse(BaseModel):
    """Response from AI signal generation chat"""
    success: bool
    conversation_id: Optional[int] = Field(None, alias="conversationId")
    message_id: Optional[int] = Field(None, alias="messageId")
    content: Optional[str] = None
    signal_configs: Optional[List[dict]] = Field(None, alias="signalConfigs")
    error: Optional[str] = None

    class Config:
        populate_by_name = True


@router.post("/ai-chat", response_model=AiSignalChatResponse)
def ai_signal_chat(
    request: AiSignalChatRequest,
    db: Session = Depends(get_db)
) -> AiSignalChatResponse:
    """Send a message to AI signal generation assistant"""
    # Get user (default user for now)
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = generate_signal_with_ai(
        db=db,
        account_id=request.account_id,
        user_message=request.user_message,
        conversation_id=request.conversation_id,
        user_id=user.id
    )

    return AiSignalChatResponse(
        success=result.get("success", False),
        conversation_id=result.get("conversation_id"),
        message_id=result.get("message_id"),
        content=result.get("content"),
        signal_configs=result.get("signal_configs"),
        error=result.get("error")
    )


@router.get("/ai-conversations")
def list_ai_signal_conversations(
    limit: int = 20,
    db: Session = Depends(get_db)
) -> dict:
    """Get list of AI signal generation conversations"""
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    conversations = get_signal_conversation_history(
        db=db,
        user_id=user.id,
        limit=limit
    )

    return {"conversations": conversations}


@router.get("/ai-conversations/{conversation_id}/messages")
def get_ai_signal_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """Get all messages in a specific conversation"""
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    messages = get_signal_conversation_messages(
        db=db,
        conversation_id=conversation_id,
        user_id=user.id
    )

    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"messages": messages}


# ============ AI Signal Generation SSE Streaming ============

@router.post("/ai-chat-stream")
async def ai_signal_chat_stream(
    request: AiSignalChatRequest,
    db: Session = Depends(get_db)
):
    """
    Send a message to AI signal generation assistant with SSE streaming.

    Returns a Server-Sent Events stream with the following event types:
    - status: Progress status message
    - tool_call: Tool being called with arguments
    - tool_result: Result from tool execution
    - reasoning: AI reasoning content (for reasoning models)
    - content: AI response content chunk
    - signal_config: Parsed signal configuration
    - done: Completion with final result
    - error: Error occurred
    """
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    def event_generator():
        for event in generate_signal_with_ai_stream(
            db=db,
            account_id=request.account_id,
            user_message=request.user_message,
            conversation_id=request.conversation_id,
            user_id=user.id
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ============ AI Signal Pool Creation ============

class SignalPoolConfigRequest(BaseModel):
    """Request for creating signal pool from AI-generated config"""
    name: str = Field(..., description="Pool name")
    symbol: str = Field(..., description="Trading symbol (e.g., BTC)")
    description: Optional[str] = Field(None, description="Pool description")
    logic: str = Field("AND", description="Combination logic: AND or OR")
    signals: List[dict] = Field(..., description="List of signal configurations")

    class Config:
        populate_by_name = True


@router.post("/create-pool-from-config")
def create_pool_from_config(
    request: SignalPoolConfigRequest,
    db: Session = Depends(get_db)
):
    """
    Create a signal pool from AI-generated configuration.
    Creates individual signals and combines them into a pool.
    """
    if not request.signals:
        raise HTTPException(status_code=400, detail="No signals provided")

    if len(request.signals) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 signals per pool")

    created_signal_ids = []
    created_signals = []

    try:
        # Create each signal
        for i, sig in enumerate(request.signals):
            # Generate signal name if not provided
            sig_name = sig.get("name") or f"{request.name}_{i+1}"

            # Build trigger condition
            trigger_condition = {
                "metric": sig.get("metric") or sig.get("indicator"),
                "operator": sig.get("operator"),
                "threshold": sig.get("threshold"),
                "time_window": sig.get("time_window")
            }

            # Validate required fields
            if not all([trigger_condition["metric"], trigger_condition["operator"],
                       trigger_condition["threshold"] is not None, trigger_condition["time_window"]]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Signal {i+1} missing required fields (metric, operator, threshold, time_window)"
                )

            # Create signal
            result = SignalDefinition(
                signal_name=sig_name,
                description=sig.get("description") or f"Part of {request.name}",
                trigger_condition=json.dumps(trigger_condition),
                enabled=True
            )
            db.add(result)
            db.flush()
            
            created_signal_ids.append(result.id)
            created_signals.append({
                "id": result.id,
                "signal_name": result.signal_name,
                "trigger_condition": trigger_condition
            })

        # Create the pool
        pool_result = SignalPool(
            pool_name=request.name,
            signal_ids=json.dumps(created_signal_ids),
            symbols=json.dumps([request.symbol]),
            enabled=True,
            logic=request.logic
        )
        db.add(pool_result)
        db.commit()

        return {
            "success": True,
            "pool": {
                "id": pool_result.id,
                "pool_name": pool_result.pool_name,
                "signal_ids": created_signal_ids,
                "symbols": [request.symbol],
                "logic": request.logic
            },
            "signals": created_signals
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create pool: {str(e)}")
