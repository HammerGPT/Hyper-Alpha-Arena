from sqlalchemy.orm import Session
from typing import Optional, List
from database.models import Account, User
from decimal import Decimal


def create_account(
    db: Session,
    user_id: int,
    name: str,
    account_type: str = "AI",
    initial_capital: float = 10000.0,
    model: str = "gpt-4-turbo",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = None
) -> Account:
    """Create a new trading account"""
    account = Account(
        user_id=user_id,
        version="v1",
        name=name,
        account_type=account_type,
        model=model if account_type == "AI" else None,
        base_url=base_url if account_type == "AI" else None,
        api_key=api_key if account_type == "AI" else None,
        initial_capital=initial_capital,
        current_cash=initial_capital,
        frozen_cash=0.0,
        is_active="true"
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: int) -> Optional[Account]:
    """Get account by ID"""
    return db.query(Account).filter(Account.id == account_id).first()


def get_accounts_by_user(db: Session, user_id: int, active_only: bool = True) -> List[Account]:
    """Get all accounts for a user"""
    query = db.query(Account).filter(Account.user_id == user_id)
    if active_only:
        query = query.filter(Account.is_active == "true")
    return query.all()


def get_or_create_default_account(
    db: Session,
    user_id: int,
    account_name: str = "Default AI Trader",
    initial_capital: float = 10000.0,
    model: str = "gpt-4-turbo",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "default-key-please-update-in-settings"
) -> Optional[Account]:
    """Get existing account (no longer creates default account automatically)"""
    # Check if user has any accounts
    existing_accounts = get_accounts_by_user(db, user_id, active_only=True)
    if existing_accounts:
        return existing_accounts[0]  # Return first active account

    # No longer auto-create default account
    return None


def update_account(
    db: Session,
    account_id: int,
    name: str = None,
    model: str = None,
    base_url: str = None,
    api_key: str = None
) -> Optional[Account]:
    """Update account information"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    if name is not None:
        account.name = name
    if model is not None:
        account.model = model
    if base_url is not None:
        account.base_url = base_url
    if api_key is not None:
        account.api_key = api_key
    
    db.commit()
    db.refresh(account)
    return account


def update_account_cash(
    db: Session,
    account_id: int,
    current_cash: float,
    frozen_cash: float = None
) -> Optional[Account]:
    """Update account cash balance"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.current_cash = current_cash
    if frozen_cash is not None:
        account.frozen_cash = frozen_cash
    
    db.commit()
    db.refresh(account)
    return account


def deactivate_account(db: Session, account_id: int) -> Optional[Account]:
    """Deactivate an account"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.is_active = "false"
    db.commit()
    db.refresh(account)
    return account


def activate_account(db: Session, account_id: int) -> Optional[Account]:
    """Activate an account"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.is_active = "true"
    db.commit()
    db.refresh(account)
    return account