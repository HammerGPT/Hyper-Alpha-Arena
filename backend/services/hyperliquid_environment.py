"""
Hyperliquid Environment Management

Provides functions for:
- Account setup for Hyperliquid trading
- Environment switching (testnet <-> mainnet)
- Client factory with automatic environment detection
"""
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

from database.models import Account, HyperliquidPosition
from services.hyperliquid_trading_client import (
    HyperliquidTradingClient,
    create_hyperliquid_client
)
from utils.encryption import encrypt_private_key, decrypt_private_key

logger = logging.getLogger(__name__)


def setup_hyperliquid_account(
    db: Session,
    account_id: int,
    environment: str,
    private_key: str,
    max_leverage: int = 3,
    default_leverage: int = 1
) -> Dict[str, Any]:
    """
    Setup Hyperliquid trading for an account

    Args:
        db: Database session
        account_id: Target account ID
        environment: "testnet" or "mainnet"
        private_key: Hyperliquid private key (will be encrypted)
        max_leverage: Maximum allowed leverage (1-50)
        default_leverage: Default leverage for orders (1-50)

    Returns:
        Setup result dict

    Raises:
        ValueError: If parameters invalid or account not found
    """
    if environment not in ["testnet", "mainnet"]:
        raise ValueError("Environment must be 'testnet' or 'mainnet'")

    if max_leverage < 1 or max_leverage > 50:
        raise ValueError("max_leverage must be between 1 and 50")

    if default_leverage < 1 or default_leverage > max_leverage:
        raise ValueError(f"default_leverage must be between 1 and {max_leverage}")

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    # Encrypt private key
    try:
        encrypted_key = encrypt_private_key(private_key)
    except Exception as e:
        logger.error(f"Failed to encrypt private key: {e}")
        raise ValueError(f"Private key encryption failed: {e}")

    # Store in environment-specific field
    if environment == "testnet":
        account.hyperliquid_testnet_private_key = encrypted_key
    else:
        account.hyperliquid_mainnet_private_key = encrypted_key

    # Configure account
    account.hyperliquid_environment = environment
    account.hyperliquid_enabled = "true"
    account.max_leverage = max_leverage
    account.default_leverage = default_leverage

    try:
        db.commit()
        logger.info(
            f"Account {account.name} (ID: {account_id}) configured for Hyperliquid {environment.upper()}: "
            f"max_leverage={max_leverage}x, default_leverage={default_leverage}x"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save account configuration: {e}")
        raise

    return {
        'success': True,
        'message': f'Account {account.name} configured for Hyperliquid {environment.upper()}',
        'account_id': account_id,
        'account_name': account.name,
        'environment': environment,
        'max_leverage': max_leverage,
        'default_leverage': default_leverage,
        'status': 'configured'
    }


def get_hyperliquid_client(db: Session, account_id: int) -> HyperliquidTradingClient:
    """
    Get Hyperliquid trading client for an account

    Automatically detects environment from account configuration and
    retrieves correct private key.

    Args:
        db: Database session
        account_id: Target account ID

    Returns:
        Initialized HyperliquidTradingClient

    Raises:
        ValueError: If account not configured or private key missing
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    if account.hyperliquid_enabled != "true":
        raise ValueError(f"Account {account.name} not enabled for Hyperliquid trading")

    environment = account.hyperliquid_environment
    if not environment:
        raise ValueError(f"Account {account.name} has no environment configured")

    # Get private key for environment
    if environment == "testnet":
        encrypted_key = account.hyperliquid_testnet_private_key
    else:
        encrypted_key = account.hyperliquid_mainnet_private_key

    if not encrypted_key:
        raise ValueError(
            f"No private key configured for {environment}. "
            f"Please setup {environment} credentials first."
        )

    # Decrypt private key
    try:
        private_key = decrypt_private_key(encrypted_key)
    except Exception as e:
        logger.error(f"Failed to decrypt private key: {e}")
        raise ValueError(f"Private key decryption failed: {e}")

    # Create and return client
    return create_hyperliquid_client(
        account_id=account_id,
        private_key=private_key,
        environment=environment
    )


def switch_hyperliquid_environment(
    db: Session,
    account_id: int,
    target_environment: str,
    confirm_switch: bool = False
) -> Dict[str, Any]:
    """
    Switch account between testnet and mainnet

    Safety measures:
    - Requires explicit confirmation (confirm_switch=True)
    - Checks for open positions (blocks switch if any exist)
    - Verifies target environment has private key configured
    - Logs the switch action

    Args:
        db: Database session
        account_id: Target account ID
        target_environment: "testnet" or "mainnet"
        confirm_switch: Must be True to proceed (safety check)

    Returns:
        Switch result dict

    Raises:
        ValueError: If validation fails or open positions exist
    """
    if not confirm_switch:
        raise ValueError(
            "Must explicitly confirm environment switch by setting confirm_switch=True. "
            "This is a safety measure to prevent accidental switches."
        )

    if target_environment not in ["testnet", "mainnet"]:
        raise ValueError("Target environment must be 'testnet' or 'mainnet'")

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    current_env = account.hyperliquid_environment
    if current_env == target_environment:
        return {
            'status': 'no_change',
            'message': f'Account already on {target_environment}',
            'current_environment': current_env
        }

    # Safety check: No open positions on current environment
    if current_env:
        logger.info(f"Checking for open positions on {current_env} before switch...")

        # Query recent positions
        recent_positions = (
            db.query(HyperliquidPosition)
            .filter(
                HyperliquidPosition.account_id == account_id,
                HyperliquidPosition.environment == current_env
            )
            .order_by(HyperliquidPosition.snapshot_time.desc())
            .limit(20)
            .all()
        )

        # Check if any positions have non-zero size
        open_positions = [
            pos for pos in recent_positions
            if pos.position_size and float(pos.position_size) != 0
        ]

        if open_positions:
            position_details = [
                f"{pos.symbol}: {float(pos.position_size)}" for pos in open_positions[:5]
            ]
            raise ValueError(
                f"Cannot switch environment: Account has {len(open_positions)} open positions on {current_env}. "
                f"Positions: {', '.join(position_details)}. "
                f"Please close all positions before switching environments."
            )

        logger.info(f"No open positions found on {current_env}, safe to switch")

    # Verify target environment has private key configured
    if target_environment == "testnet":
        if not account.hyperliquid_testnet_private_key:
            raise ValueError(
                "No testnet private key configured. "
                "Please setup testnet credentials first using setup_hyperliquid_account()."
            )
    else:
        if not account.hyperliquid_mainnet_private_key:
            raise ValueError(
                "No mainnet private key configured. "
                "Please setup mainnet credentials first using setup_hyperliquid_account()."
            )

    # Perform switch
    old_env = account.hyperliquid_environment
    account.hyperliquid_environment = target_environment

    try:
        db.commit()
        logger.warning(
            f"ENVIRONMENT SWITCH: Account {account.name} (ID: {account_id}) "
            f"switched from {old_env} to {target_environment.upper()}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to switch environment: {e}")
        raise

    return {
        'status': 'success',
        'account_id': account_id,
        'account_name': account.name,
        'old_environment': old_env,
        'new_environment': target_environment,
        'message': f'Successfully switched from {old_env} to {target_environment}'
    }


def get_account_hyperliquid_config(db: Session, account_id: int) -> Dict[str, Any]:
    """
    Get Hyperliquid configuration for an account

    Args:
        db: Database session
        account_id: Target account ID

    Returns:
        Configuration dict
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    return {
        'account_id': account_id,
        'account_name': account.name,
        'hyperliquid_enabled': account.hyperliquid_enabled == "true",
        'environment': account.hyperliquid_environment,
        'max_leverage': account.max_leverage,
        'default_leverage': account.default_leverage,
        'testnet_configured': bool(account.hyperliquid_testnet_private_key),
        'mainnet_configured': bool(account.hyperliquid_mainnet_private_key)
    }


def disable_hyperliquid_trading(db: Session, account_id: int) -> Dict[str, Any]:
    """
    Disable Hyperliquid trading for an account

    Note: This does NOT delete private keys, only disables trading.
    Keys remain encrypted in database for potential re-enable.

    Args:
        db: Database session
        account_id: Target account ID

    Returns:
        Disable result dict
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    if account.hyperliquid_enabled != "true":
        return {
            'status': 'already_disabled',
            'message': 'Hyperliquid trading already disabled'
        }

    account.hyperliquid_enabled = "false"

    try:
        db.commit()
        logger.info(f"Hyperliquid trading disabled for account {account.name}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to disable Hyperliquid trading: {e}")
        raise

    return {
        'status': 'success',
        'account_id': account_id,
        'account_name': account.name,
        'message': 'Hyperliquid trading disabled successfully'
    }


def enable_hyperliquid_trading(db: Session, account_id: int) -> Dict[str, Any]:
    """
    Re-enable Hyperliquid trading for an account

    Args:
        db: Database session
        account_id: Target account ID

    Returns:
        Enable result dict

    Raises:
        ValueError: If account has no environment or private keys configured
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    if account.hyperliquid_enabled == "true":
        return {
            'status': 'already_enabled',
            'message': 'Hyperliquid trading already enabled'
        }

    # Verify configuration exists
    if not account.hyperliquid_environment:
        raise ValueError(
            "No environment configured. "
            "Please setup Hyperliquid first using setup_hyperliquid_account()."
        )

    env = account.hyperliquid_environment
    if env == "testnet":
        if not account.hyperliquid_testnet_private_key:
            raise ValueError(f"No testnet private key configured")
    else:
        if not account.hyperliquid_mainnet_private_key:
            raise ValueError(f"No mainnet private key configured")

    account.hyperliquid_enabled = "true"

    try:
        db.commit()
        logger.info(f"Hyperliquid trading enabled for account {account.name} on {env}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to enable Hyperliquid trading: {e}")
        raise

    return {
        'status': 'success',
        'account_id': account_id,
        'account_name': account.name,
        'environment': env,
        'message': f'Hyperliquid trading enabled on {env}'
    }
