"""
Private Key Encryption Utilities

Provides secure encryption/decryption for Hyperliquid private keys using Fernet (symmetric encryption).
Private keys are encrypted before storing in database and decrypted only when needed for API calls.
"""
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """
    Get encryption key from environment variable

    Returns:
        Encryption key as bytes

    Raises:
        ValueError: If HYPERLIQUID_ENCRYPTION_KEY not set
    """
    key = os.getenv('HYPERLIQUID_ENCRYPTION_KEY')
    if not key:
        raise ValueError(
            "HYPERLIQUID_ENCRYPTION_KEY not set in environment. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return key.encode()


def encrypt_private_key(private_key: str) -> str:
    """
    Encrypt private key for database storage

    Args:
        private_key: Hyperliquid private key (plain text, e.g., "0x...")

    Returns:
        Encrypted private key as string

    Raises:
        ValueError: If encryption fails
    """
    try:
        f = Fernet(get_encryption_key())
        encrypted = f.encrypt(private_key.encode())
        logger.debug("Private key encrypted successfully")
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Failed to encrypt private key: {e}")
        raise ValueError(f"Encryption failed: {e}")


def decrypt_private_key(encrypted_key: str) -> str:
    """
    Decrypt private key from database

    Args:
        encrypted_key: Encrypted private key from database

    Returns:
        Decrypted private key as string

    Raises:
        ValueError: If decryption fails
    """
    try:
        f = Fernet(get_encryption_key())
        decrypted = f.decrypt(encrypted_key.encode())
        logger.debug("Private key decrypted successfully")
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Failed to decrypt private key: {e}")
        raise ValueError(f"Decryption failed: {e}")


def generate_encryption_key() -> str:
    """
    Generate a new encryption key

    Use this function to generate a new encryption key for initial setup.
    Store the generated key in HYPERLIQUID_ENCRYPTION_KEY environment variable.

    Returns:
        New encryption key as string

    Example:
        >>> key = generate_encryption_key()
        >>> print(f"Export this: export HYPERLIQUID_ENCRYPTION_KEY={key}")
    """
    key = Fernet.generate_key().decode()
    logger.info("Generated new encryption key")
    return key


def validate_encryption_setup() -> bool:
    """
    Validate that encryption is properly configured

    Returns:
        True if encryption key is set and valid

    Raises:
        ValueError: If encryption setup invalid
    """
    try:
        key = get_encryption_key()
        # Test encryption/decryption
        test_data = "test_private_key_0x123"
        encrypted = encrypt_private_key(test_data)
        decrypted = decrypt_private_key(encrypted)

        if decrypted != test_data:
            raise ValueError("Encryption test failed: decrypted data doesn't match")

        logger.info("Encryption setup validated successfully")
        return True
    except Exception as e:
        logger.error(f"Encryption setup validation failed: {e}")
        raise


if __name__ == "__main__":
    # Script mode: generate encryption key
    print("Generating new encryption key for Hyperliquid private key storage...")
    print("")
    key = generate_encryption_key()
    print(f"Generated Key: {key}")
    print("")
    print("Add this to your .env file or export as environment variable:")
    print(f"export HYPERLIQUID_ENCRYPTION_KEY={key}")
    print("")
    print("Keep this key secure! If lost, you cannot decrypt stored private keys.")
