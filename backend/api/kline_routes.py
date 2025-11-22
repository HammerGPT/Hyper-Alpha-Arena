"""
K线数据管理API路由
"""

import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from database.connection import SessionLocal
from database.models import KlineCollectionTask
from services.kline_data_service import kline_service
from services.kline_backfill_manager import BackfillManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/klines", tags=["klines"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic模型
class BackfillRequest(BaseModel):
    exchange: Optional[str] = None  # 如果不指定，使用当前配置的交易所
    symbols: List[str]
    start_time: datetime
    end_time: datetime
    period: str = "1m"


class BackfillTaskResponse(BaseModel):
    task_id: int
    exchange: str
    symbol: str
    start_time: datetime
    end_time: datetime
    period: str
    status: str
    progress: int
    total_records: int
    collected_records: int
    error_message: Optional[str]
    created_at: datetime


class CoverageResponse(BaseModel):
    exchange: str
    symbol: str
    period: str
    earliest_time: Optional[int]
    latest_time: Optional[int]
    total_records: int
    time_span_seconds: Optional[int]
    coverage_percentage: Optional[float]


@router.get("/coverage", response_model=List[CoverageResponse])
async def get_data_coverage(
    symbols: Optional[str] = None,  # 逗号分隔的交易对列表
    db: Session = Depends(get_db)
):
    """获取K线数据覆盖情况"""
    try:
        # 确保服务已初始化
        await kline_service.initialize()

        # 解析交易对参数
        symbol_list = None
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",")]

        # 获取覆盖情况
        coverage_data = await kline_service.get_data_coverage(symbol_list)

        return [CoverageResponse(**item) for item in coverage_data]

    except Exception as e:
        logger.error(f"Failed to get data coverage: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get data coverage: {str(e)}")


@router.get("/backfill-tasks")
async def get_backfill_tasks(db: Session = Depends(get_db)):
    """获取补漏任务列表"""
    try:
        tasks = db.query(KlineCollectionTask).order_by(KlineCollectionTask.created_at.desc()).limit(50).all()
        return {"tasks": [{"task_id": t.id, "symbol": t.symbol, "status": t.status, "progress": t.progress or 0, "total_records": t.total_records or 0, "collected_records": t.collected_records or 0} for t in tasks]}
    except Exception as e:
        return {"tasks": []}

@router.get("/data")
async def get_kline_data(symbol: str, period: str = "1m", limit: int = 1000):
    """获取K线数据"""
    return {"success": False, "data": [], "message": "K-line data service not implemented yet"}

@router.post("/backfill", response_model=Dict[str, Any])
async def create_backfill_task(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """创建补漏任务"""
    try:
        # 确保服务已初始化
        await kline_service.initialize()

        # 使用当前配置的交易所（如果未指定）
        exchange = request.exchange or kline_service.exchange_id

        # 验证时间范围
        if request.start_time >= request.end_time:
            raise HTTPException(status_code=400, detail="start_time must be before end_time")

        # 限制时间范围（最多30天）
        max_days = 30
        if (request.end_time - request.start_time).days > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"Time range too large. Maximum {max_days} days allowed."
            )

        # 检查是否有任何任务正在运行（全局只允许一个任务）
        existing_active_task = db.query(KlineCollectionTask).filter(
            KlineCollectionTask.status.in_(["pending", "running"])
        ).first()

        if existing_active_task:
            raise HTTPException(
                status_code=400,
                detail=f"A backfill task is already running for {existing_active_task.symbol}. Please wait for it to complete."
            )

        # 创建补漏任务记录
        task_ids = []
        skipped_symbols = []
        for symbol in request.symbols:
            symbol_upper = symbol.upper()

            # 检查是否有相同 symbol 的任务正在运行
            existing_task = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.symbol == symbol_upper,
                KlineCollectionTask.status.in_(["pending", "running"])
            ).first()

            if existing_task:
                skipped_symbols.append(symbol_upper)
                continue

            task = KlineCollectionTask(
                exchange=exchange,
                symbol=symbol_upper,
                start_time=request.start_time,
                end_time=request.end_time,
                period=request.period,
                status="pending"
            )
            db.add(task)
            db.flush()  # 获取ID
            task_ids.append(task.id)

        db.commit()

        # 启动后台补漏任务
        backfill_manager = BackfillManager()
        for task_id in task_ids:
            background_tasks.add_task(backfill_manager.process_task, task_id)

        message = f"Created {len(task_ids)} backfill tasks"
        if skipped_symbols:
            message += f". Skipped {len(skipped_symbols)} symbols with existing tasks: {', '.join(skipped_symbols)}"

        return {
            "message": message,
            "task_ids": task_ids,
            "skipped_symbols": skipped_symbols,
            "exchange": exchange,
            "symbols": request.symbols,
            "time_range": f"{request.start_time} to {request.end_time}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create backfill task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create backfill task: {str(e)}")


@router.get("/backfill/status/{task_id}", response_model=BackfillTaskResponse)
async def get_backfill_status(task_id: int, db: Session = Depends(get_db)):
    """获取补漏任务状态"""
    try:
        task = db.query(KlineCollectionTask).filter(KlineCollectionTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return BackfillTaskResponse(
            task_id=task.id,
            exchange=task.exchange,
            symbol=task.symbol,
            start_time=task.start_time,
            end_time=task.end_time,
            period=task.period,
            status=task.status,
            progress=task.progress,
            total_records=task.total_records or 0,
            collected_records=task.collected_records or 0,
            error_message=task.error_message,
            created_at=task.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@router.get("/backfill/tasks", response_model=List[BackfillTaskResponse])
async def list_backfill_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """获取补漏任务列表"""
    try:
        query = db.query(KlineCollectionTask)

        if status:
            query = query.filter(KlineCollectionTask.status == status)

        tasks = query.order_by(KlineCollectionTask.created_at.desc()).limit(limit).all()

        return [
            BackfillTaskResponse(
                task_id=task.id,
                exchange=task.exchange,
                symbol=task.symbol,
                start_time=task.start_time,
                end_time=task.end_time,
                period=task.period,
                status=task.status,
                progress=task.progress,
                total_records=task.total_records or 0,
                collected_records=task.collected_records or 0,
                error_message=task.error_message,
                created_at=task.created_at
            )
            for task in tasks
        ]

    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@router.delete("/backfill-tasks/{task_id}")
async def delete_backfill_task(task_id: int, db: Session = Depends(get_db)):
    """删除补漏任务"""
    try:
        task = db.query(KlineCollectionTask).filter(KlineCollectionTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        db.delete(task)
        db.commit()

        return {"message": f"Task {task_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")


@router.get("/gaps/{symbol}")
async def detect_data_gaps(
    symbol: str,
    days: int = 7,  # 检查最近几天的数据
    db: Session = Depends(get_db)
):
    """检测指定交易对的数据缺失"""
    try:
        # 确保服务已初始化
        await kline_service.initialize()

        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        # 检测缺失范围
        missing_ranges = await kline_service.detect_missing_ranges(
            symbol.upper(), start_time, end_time, "1m"
        )

        return {
            "symbol": symbol.upper(),
            "exchange": kline_service.exchange_id,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "missing_ranges": [
                {
                    "start": range_start.isoformat(),
                    "end": range_end.isoformat(),
                    "duration_minutes": int((range_end - range_start).total_seconds() / 60)
                }
                for range_start, range_end in missing_ranges
            ],
            "total_missing_minutes": sum(
                int((range_end - range_start).total_seconds() / 60)
                for range_start, range_end in missing_ranges
            )
        }

    except Exception as e:
        logger.error(f"Failed to detect gaps for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to detect gaps: {str(e)}")


@router.get("/supported-symbols")
async def get_supported_symbols():
    """获取当前交易所支持的交易对"""
    try:
        await kline_service.initialize()
        symbols = kline_service.get_supported_symbols()

        return {
            "exchange": kline_service.exchange_id,
            "symbols": symbols,
            "count": len(symbols)
        }

    except Exception as e:
        logger.error(f"Failed to get supported symbols: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get supported symbols: {str(e)}")