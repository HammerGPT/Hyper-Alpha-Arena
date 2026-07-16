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
