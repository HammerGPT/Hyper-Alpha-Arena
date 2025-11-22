#!/usr/bin/env python3
"""
Migration: Add kline collection system tables and optimize crypto_klines
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from database.connection import DATABASE_URL

def migrate():
    """Add kline collection system tables and optimize existing ones"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # 1. 为crypto_klines表添加唯一约束（如果不存在）
        conn.execute(text("""
            DO $$
            BEGIN
                -- 检查唯一约束是否已存在
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_crypto_klines_unique'
                ) THEN
                    -- 添加唯一约束防止重复数据
                    ALTER TABLE crypto_klines
                    ADD CONSTRAINT uq_crypto_klines_unique
                    UNIQUE (exchange, symbol, timestamp, period);
                END IF;
            END $$;
        """))

        # 2. 优化crypto_klines表的索引
        conn.execute(text("""
            -- 为常用查询创建复合索引
            CREATE INDEX IF NOT EXISTS idx_crypto_klines_exchange_symbol_time
            ON crypto_klines(exchange, symbol, timestamp DESC);

            -- 为时间范围查询优化
            CREATE INDEX IF NOT EXISTS idx_crypto_klines_timestamp_range
            ON crypto_klines(timestamp DESC) WHERE exchange IS NOT NULL;
        """))

        # 3. 创建K线采集任务表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kline_collection_tasks (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(20) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                period VARCHAR(10) NOT NULL DEFAULT '1m',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                total_records INTEGER DEFAULT 0,
                collected_records INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 4. 为任务表创建索引
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_kline_tasks_status
            ON kline_collection_tasks(status, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_kline_tasks_exchange_symbol
            ON kline_collection_tasks(exchange, symbol);
        """))

        # 5. 创建数据覆盖统计视图（用于快速查询数据完整性）
        conn.execute(text("""
            CREATE OR REPLACE VIEW kline_coverage_stats AS
            SELECT
                exchange,
                symbol,
                period,
                MIN(timestamp) as earliest_time,
                MAX(timestamp) as latest_time,
                COUNT(*) as total_records,
                (MAX(timestamp) - MIN(timestamp)) as time_span_seconds,
                ROUND(
                    (COUNT(*) * 60.0) / NULLIF((MAX(timestamp) - MIN(timestamp)), 0) * 100, 2
                ) as coverage_percentage
            FROM crypto_klines
            WHERE period = '1m' AND timestamp IS NOT NULL
            GROUP BY exchange, symbol, period
            HAVING COUNT(*) > 1;
        """))

        conn.commit()
        print("✅ K线采集系统数据库结构创建成功")
        print("   - crypto_klines表添加唯一约束")
        print("   - 创建kline_collection_tasks任务表")
        print("   - 添加性能优化索引")
        print("   - 创建数据覆盖统计视图")

if __name__ == "__main__":
    migrate()