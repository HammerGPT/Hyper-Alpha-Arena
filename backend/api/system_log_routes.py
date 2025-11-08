"""
System Log API Routes
提供系统日志查询接口
"""

from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from services.system_logger import system_logger

router = APIRouter(prefix="/api/system-logs", tags=["System Logs"])


@router.get("/")
async def get_system_logs(
    level: Optional[str] = Query(None, description="日志级别过滤: INFO, WARNING, ERROR"),
    category: Optional[str] = Query(None, description="日志分类过滤: price_update, ai_decision, system_error"),
    limit: int = Query(100, ge=1, le=500, description="返回的最大日志数量")
) -> Dict[str, Any]:
    """
    获取系统日志列表

    参数:
    - level: 过滤日志级别 (INFO, WARNING, ERROR)
    - category: 过滤日志分类 (price_update, ai_decision, system_error)
    - limit: 返回的最大日志数量 (1-500)

    返回:
    - logs: 日志列表
    - total: 返回的日志数量
    """
    min_level = None if level else "WARNING"
    logs = system_logger.get_logs(
        level=level,
        category=category,
        limit=limit,
        min_level=min_level,
    )
    return {
        "logs": logs,
        "total": len(logs)
    }


@router.get("/categories")
async def get_log_categories() -> Dict[str, List[str]]:
    """
    获取可用的日志分类和级别

    返回:
    - categories: 日志分类列表
    - levels: 日志级别列表
    """
    return {
        "categories": ["price_update", "ai_decision", "system_error"],
        "levels": ["INFO", "WARNING", "ERROR"]
    }


@router.delete("/")
async def clear_system_logs() -> Dict[str, str]:
    """
    清空所有系统日志

    返回:
    - message: 操作结果消息
    """
    system_logger.clear_logs()
    return {"message": "All system logs cleared successfully"}


@router.get("/stats")
async def get_log_stats() -> Dict[str, Any]:
    """
    获取日志统计信息

    返回:
    - total_logs: 总日志数量
    - by_level: 按级别分组的统计
    - by_category: 按分类分组的统计
    """
    all_logs = system_logger.get_logs(limit=500, min_level="WARNING")

    stats = {
        "total_logs": len(all_logs),
        "by_level": {
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0
        },
        "by_category": {
            "price_update": 0,
            "ai_decision": 0,
            "system_error": 0
        }
    }

    for log in all_logs:
        level = log.get("level", "INFO")
        category = log.get("category", "system_error")

        if level in stats["by_level"]:
            stats["by_level"][level] += 1
        if category in stats["by_category"]:
            stats["by_category"][category] += 1

    return stats
