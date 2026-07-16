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
