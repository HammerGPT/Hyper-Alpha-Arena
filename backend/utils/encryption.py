"""
Encryption utilities for securing API wallet private keys.

This module provides AES-256-GCM encryption/decryption for sensitive data.
The encryption key is auto-generated on first run if not present in .env.

Security Features:
- AES-256-GCM authenticated encryption
- Auto-generated encryption key (32 bytes / 256 bits)
- Base64 encoding for database storage
- Nonce/IV uniquely generated per encryption
"""

import os
import secrets
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
from pathlib import Path


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive data (API wallet keys).

    Uses AES-256-GCM for authenticated encryption with auto-generated keys.
    """

    def __init__(self):
        """
        Initialize encryption service.

        Automatically generates and stores encryption key if not present.
        """
        self.encryption_key = self._get_or_create_encryption_key()
        self.aesgcm = AESGCM(self.encryption_key)

    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get encryption key from environment or generate new one.

        Returns:
            32-byte encryption key
        """
        # Check if encryption key exists in environment
        key_b64 = os.environ.get("ENCRYPTION_KEY")

        if key_b64:
            try:
                key = base64.b64decode(key_b64)
                if len(key) == 32:
                    return key
                else:
                    print(f"Warning: ENCRYPTION_KEY in .env is {len(key)} bytes, expected 32. Generating new key.")
            except Exception as e:
                print(f"Warning: Invalid ENCRYPTION_KEY in .env: {e}. Generating new key.")

        # Generate new encryption key
        key = secrets.token_bytes(32)  # 256 bits
        key_b64_str = base64.b64encode(key).decode('utf-8')

        # Save to .env file
        env_path = Path(__file__).parent.parent / ".env"

        try:
            # Read existing .env content
            if env_path.exists():
                with open(env_path, 'r') as f:
                    env_content = f.read()
            else:
                env_content = ""

            # Check if ENCRYPTION_KEY already exists in file
            if "ENCRYPTION_KEY=" not in env_content:
                # Append new key
                with open(env_path, 'a') as f:
                    if env_content and not env_content.endswith('\n'):
                        f.write('\n')
                    f.write(f"\n# Auto-generated encryption key for API wallet private keys\n")
                    f.write(f"# DO NOT COMMIT THIS FILE TO VERSION CONTROL\n")
                    f.write(f"# Keep this key secure - loss = inability to decrypt API wallets\n")
                    f.write(f"ENCRYPTION_KEY={key_b64_str}\n")

                print(f"✓ Generated new encryption key and saved to {env_path}")
                print("  IMPORTANT: Back up this .env file securely!")
            else:
                print(f"Warning: ENCRYPTION_KEY found in .env file but not in environment. Using generated key for this session.")
        except Exception as e:
            print(f"Warning: Could not write encryption key to .env: {e}")
            print(f"Add this to your .env file manually:")
            print(f"ENCRYPTION_KEY={key_b64_str}")

        return key

    def encrypt_private_key(self, private_key: str) -> str:
        """
        Encrypt a private key for secure storage.

        Args:
            private_key: Hex string (with or without 0x prefix)

        Returns:
            Base64-encoded encrypted data (nonce + ciphertext)

        Raises:
            ValueError: If private key format is invalid
        """
        if not private_key:
            raise ValueError("Private key cannot be empty")

        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        # Validate hex format
        try:
            bytes.fromhex(private_key)
        except ValueError:
            raise ValueError("Private key must be valid hex string")

        # Convert to bytes
        plaintext = private_key.encode('utf-8')

        # Generate random nonce (96 bits / 12 bytes for GCM)
        nonce = secrets.token_bytes(12)

        # Encrypt with authenticated encryption
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, None)

        # Combine nonce + ciphertext and encode as base64
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('utf-8')

    def decrypt_private_key(self, encrypted_data_b64: str) -> str:
        """
        Decrypt a private key from storage.

        Args:
            encrypted_data_b64: Base64-encoded encrypted data (nonce + ciphertext)

        Returns:
            Decrypted private key (hex string without 0x prefix)

        Raises:
            ValueError: If decryption fails (wrong key or corrupted data)
        """
        if not encrypted_data_b64:
            raise ValueError("Encrypted data cannot be empty")

        try:
            # Decode from base64
            encrypted_data = base64.b64decode(encrypted_data_b64)

            # Extract nonce (first 12 bytes) and ciphertext
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]

            # Decrypt
            plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)

            # Return as hex string
            return plaintext.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def test_encryption_decryption(self) -> bool:
        """
        Test encryption and decryption with sample data.

        Returns:
            True if test passed, False otherwise
        """
        test_key = "a" * 64  # 64 hex chars = 32 bytes

        try:
            encrypted = self.encrypt_private_key(test_key)
            decrypted = self.decrypt_private_key(encrypted)
            return decrypted == test_key
        except Exception as e:
            print(f"Encryption test failed: {e}")
            return False


# Global singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get global encryption service singleton.

    Returns:
        EncryptionService instance
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


# Convenience functions
def encrypt_private_key(private_key: str) -> str:
    """Encrypt a private key for storage."""
    return get_encryption_service().encrypt_private_key(private_key)


def decrypt_private_key(encrypted_data: str) -> str:
    """Decrypt a private key from storage."""
    return get_encryption_service().decrypt_private_key(encrypted_data)
