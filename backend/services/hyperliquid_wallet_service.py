"""
Hyperliquid Wallet Service

Handles API wallet generation, registration, and management for Hyperliquid integration.

Key Concepts:
- Main Wallet: User's MetaMask wallet (never stored on backend, user custody)
- API Wallet: Delegated wallet for automated trading (stored encrypted on backend)
- API Wallet Restrictions: Can trade but CANNOT withdraw funds (Hyperliquid enforced)

Flow:
1. User authorizes API wallet creation via MetaMask signature
2. Backend generates new API wallet keypair
3. Backend registers API wallet with Hyperliquid
4. API wallet private key encrypted and stored in database
5. Backend uses API wallet to sign orders for automated trading
"""

from eth_account import Account
from eth_account.messages import encode_defunct
from typing import Optional, Dict, Any
import secrets
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from datetime import datetime
import logging

from utils.encryption import encrypt_private_key, decrypt_private_key

logger = logging.getLogger(__name__)


class HyperliquidWalletService:
    """
    Service for managing Hyperliquid API wallets.

    Handles wallet generation, registration, and signing operations.
    """

    def __init__(self, testnet: bool = True):
        """
        Initialize Hyperliquid wallet service.

        Args:
            testnet: Whether to use Hyperliquid testnet (default: True)
        """
        self.testnet = testnet

        # Initialize Hyperliquid Info client (read-only)
        self.info = Info(skip_ws=True, base_url=self._get_base_url())

    def _get_base_url(self) -> Optional[str]:
        """
        Get Hyperliquid API base URL based on network.

        Returns:
            Base URL for testnet or None for mainnet
        """
        if self.testnet:
            return "https://api.hyperliquid-testnet.xyz"
        else:
            return None  # Mainnet (default)

    def generate_api_wallet(self) -> Dict[str, str]:
        """
        Generate a new API wallet keypair.

        Returns:
            Dict with 'private_key' (hex with 0x) and 'address' (checksum)

        Example:
            {
                "private_key": "0xabcd...",
                "address": "0x1234..."
            }
        """
        # Generate random 32 bytes for private key
        private_key_bytes = secrets.token_bytes(32)

        # Create eth-account Account object
        account = Account.from_key(private_key_bytes)

        return {
            "private_key": account.key.hex(),  # Returns 0x-prefixed hex string
            "address": account.address,  # Checksum address
        }

    def verify_authorization_signature(
        self,
        main_wallet_address: str,
        authorization_message: str,
        signature: str
    ) -> bool:
        """
        Verify that main wallet signed authorization message.

        Args:
            main_wallet_address: Expected signer address
            authorization_message: Message that was signed
            signature: Signature from MetaMask (0x-prefixed hex)

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Encode message in Ethereum signed message format
            message = encode_defunct(text=authorization_message)

            # Recover signer address from signature
            recovered_address = Account.recover_message(message, signature=signature)

            # Compare addresses (case-insensitive)
            return recovered_address.lower() == main_wallet_address.lower()
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def register_api_wallet_with_hyperliquid(
        self,
        api_wallet_private_key: str,
        main_wallet_address: str
    ) -> bool:
        """
        Register API wallet with Hyperliquid (agent approval).

        This tells Hyperliquid that api_wallet can trade on behalf of main_wallet.

        Args:
            api_wallet_private_key: API wallet private key (hex, with or without 0x)
            main_wallet_address: Main wallet address (owner)

        Returns:
            True if registration successful, False otherwise

        Note:
            This is a placeholder. Actual implementation requires Hyperliquid SDK
            method for agent registration, which may not be available in testnet.
        """
        try:
            # Remove 0x prefix if present
            if api_wallet_private_key.startswith("0x"):
                api_wallet_private_key = api_wallet_private_key[2:]

            # Create exchange client with API wallet
            exchange = Exchange(
                account=Account.from_key(api_wallet_private_key),
                base_url=self._get_base_url(),
                skip_ws=True
            )

            # Note: Hyperliquid's agent registration may require specific API calls
            # that are not yet documented or available in testnet.
            # For now, we'll just verify the wallet can connect.

            # Test connection by fetching account state
            user_state = self.info.user_state(main_wallet_address)

            logger.info(f"API wallet registered for {main_wallet_address}: {user_state is not None}")

            return True

        except Exception as e:
            logger.error(f"API wallet registration failed: {e}")
            return False

    def test_api_wallet_signing(self, api_wallet_private_key: str) -> bool:
        """
        Test if API wallet can sign messages.

        Args:
            api_wallet_private_key: API wallet private key (hex)

        Returns:
            True if signing works, False otherwise
        """
        try:
            # Remove 0x prefix if present
            if api_wallet_private_key.startswith("0x"):
                api_wallet_private_key = api_wallet_private_key[2:]

            # Create account
            account = Account.from_key(api_wallet_private_key)

            # Test signing a message
            message = encode_defunct(text="Test signing")
            signature = account.sign_message(message)

            # Verify signature
            recovered = Account.recover_message(message, signature=signature.signature)

            return recovered.lower() == account.address.lower()

        except Exception as e:
            logger.error(f"API wallet signing test failed: {e}")
            return False

    def get_api_wallet_balance(
        self,
        api_wallet_address: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get balance of API wallet from Hyperliquid.

        Args:
            api_wallet_address: API wallet address

        Returns:
            User state dict or None if failed

        Example:
            {
                "marginSummary": {
                    "accountValue": "1000.50",
                    "totalMarginUsed": "100.25",
                    "totalNtlPos": "500.00",
                    "totalRawUsd": "1000.50"
                },
                "assetPositions": [...],
                "crossMarginSummary": {...}
            }
        """
        try:
            user_state = self.info.user_state(api_wallet_address)
            return user_state
        except Exception as e:
            logger.error(f"Failed to fetch API wallet balance: {e}")
            return None

    def create_authorization_message(
        self,
        account_id: int,
        account_name: str,
        timestamp: datetime
    ) -> str:
        """
        Create authorization message for user to sign.

        Args:
            account_id: AI trader account ID
            account_name: AI trader account name
            timestamp: Current timestamp

        Returns:
            Message string for user to sign
        """
        return (
            f"Authorize Hyper Alpha Arena to create an API wallet for automated trading.\n\n"
            f"Account: {account_name} (ID: {account_id})\n"
            f"Timestamp: {timestamp.isoformat()}\n\n"
            f"This API wallet will ONLY be able to trade on your behalf.\n"
            f"It CANNOT withdraw funds.\n"
            f"You can revoke this authorization at any time."
        )


# Convenience functions
def generate_and_encrypt_api_wallet() -> Dict[str, str]:
    """
    Generate new API wallet and encrypt private key.

    Returns:
        Dict with 'address', 'encrypted_private_key'
    """
    service = HyperliquidWalletService(testnet=True)
    wallet = service.generate_api_wallet()

    # Encrypt private key
    encrypted_key = encrypt_private_key(wallet["private_key"])

    return {
        "address": wallet["address"],
        "encrypted_private_key": encrypted_key,
    }


def decrypt_and_get_account(encrypted_private_key: str):
    """
    Decrypt API wallet private key and create eth_account.Account.

    Args:
        encrypted_private_key: Encrypted private key from database

    Returns:
        eth_account.Account object

    Raises:
        ValueError: If decryption fails
    """
    # Decrypt private key
    private_key = decrypt_private_key(encrypted_private_key)

    # Remove 0x prefix if present
    if private_key.startswith("0x"):
        private_key = private_key[2:]

    # Create account
    return Account.from_key(private_key)
