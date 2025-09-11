import os
import base64
import logging
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)


class TokenEncryption:
    """
    Handles encryption and decryption of OAuth tokens using Fernet
    symmetric encryption, with the key sourced from an environment variable.
    """

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._encryption_key: Optional[bytes] = None

    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key from environment variable"""
        if self._encryption_key:
            logger.debug("Using cached encryption key")
            return self._encryption_key

        env_key = os.getenv('ENCRYPTION_KEY')
        if not env_key:
            raise ValueError("No encryption key available. Set ENCRYPTION_KEY environment variable.")

        logger.info("Using encryption key from environment variable")
        logger.debug(f"Environment key length: {len(env_key)}")

        # Check if it's already a valid Fernet key or needs derivation
        try:
            # Try to use it directly as a Fernet key
            test_key = env_key.encode() if isinstance(env_key, str) else env_key
            Fernet(test_key)  # Test if it's valid
            self._encryption_key = base64.urlsafe_b64decode(test_key)
            logger.info("Environment key is a valid Fernet key")
        except Exception:
            # If not valid, derive from password
            logger.info("Environment key is not a valid Fernet key, deriving from password")
            derived_key = self._derive_key_from_password(env_key.encode())
            self._encryption_key = base64.urlsafe_b64decode(derived_key)

        logger.debug(f"Final encryption key length: {len(self._encryption_key)} bytes")
        return self._encryption_key

    def _derive_key_from_password(self, password: bytes, salt: Optional[bytes] = None) -> bytes:
        """Derive encryption key from password using PBKDF2"""
        if salt is None:
            salt = b'mypraxos-salt'
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def _get_fernet(self) -> Fernet:
        """Get Fernet encryption instance"""
        if not self._fernet:
            logger.debug("Creating new Fernet instance")
            key_bytes = self._get_encryption_key()
            key_b64 = base64.urlsafe_b64encode(key_bytes)
            logger.debug(f"Fernet key length: {len(key_b64)} characters")
            try:
                self._fernet = Fernet(key_b64)
                logger.debug("Successfully created Fernet instance")
            except Exception as e:
                logger.error(f"Failed to create Fernet instance: {e}")
                logger.error(f"Key bytes length: {len(key_bytes)}, Key b64 length: {len(key_b64)}")
                raise
        return self._fernet

    def encrypt_token(self, token: str) -> str:
        """
        Encrypt a token string
        
        Args:
            token: Plain text token to encrypt
            
        Returns:
            Base64 encoded encrypted token
        """
        try:
            logger.debug(f"Encrypting token of length: {len(token)}")
            fernet = self._get_fernet()
            encrypted_bytes = fernet.encrypt(token.encode())
            encrypted_b64 = base64.b64encode(encrypted_bytes).decode()
            logger.debug(f"Encrypted token length: {len(encrypted_b64)}")
            return encrypted_b64
        except Exception as e:
            logger.error(f"Failed to encrypt token: {e}")
            logger.error(f"Token length: {len(token) if token else 'None'}")
            raise

    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt an encrypted token
        
        Args:
            encrypted_token: Base64 encoded encrypted token
            
        Returns:
            Plain text token
        """
        try:
            logger.debug(f"Decrypting token of length: {len(encrypted_token)}")
            fernet = self._get_fernet()
            
            # Decode the base64 encrypted token
            try:
                encrypted_bytes = base64.b64decode(encrypted_token.encode())
                logger.debug(f"Decoded encrypted bytes length: {len(encrypted_bytes)}")
            except Exception as e:
                logger.error(f"Failed to decode base64 encrypted token: {e}")
                logger.error(f"Encrypted token: {encrypted_token[:50]}...")
                raise
            
            # Decrypt using Fernet
            try:
                decrypted_bytes = fernet.decrypt(encrypted_bytes)
                decrypted_token = decrypted_bytes.decode()
                logger.debug(f"Successfully decrypted token of length: {len(decrypted_token)}")
                return decrypted_token
            except Exception as e:
                logger.error(f"Failed to decrypt with Fernet: {e}")
                logger.error(f"Encrypted bytes length: {len(encrypted_bytes)}")
                raise
                
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            logger.error(f"Encrypted token length: {len(encrypted_token) if encrypted_token else 'None'}")
            raise
    
    def encrypt_token_pair(self, access_token: str, refresh_token: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Encrypt both access and refresh tokens
        
        Args:
            access_token: Access token to encrypt
            refresh_token: Optional refresh token to encrypt
            
        Returns:
            Tuple of (encrypted_access_token, encrypted_refresh_token)
        """
        logger.debug("Encrypting token pair")
        encrypted_access = self.encrypt_token(access_token)
        encrypted_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        logger.debug(f"Token pair encrypted: access={len(encrypted_access)}, refresh={len(encrypted_refresh) if encrypted_refresh else 'None'}")
        
        return encrypted_access, encrypted_refresh

    def decrypt_token_pair(self, encrypted_access_token: str, encrypted_refresh_token: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Decrypt both access and refresh tokens
        
        Args:
            encrypted_access_token: Encrypted access token
            encrypted_refresh_token: Optional encrypted refresh token
            
        Returns:
            Tuple of (access_token, refresh_token)
        """
        logger.debug("Decrypting token pair")
        try:
            access_token = self.decrypt_token(encrypted_access_token)
            refresh_token = self.decrypt_token(encrypted_refresh_token) if encrypted_refresh_token else None
            logger.debug(f"Token pair decrypted successfully: access={len(access_token)}, refresh={len(refresh_token) if refresh_token else 'None'}")
            return access_token, refresh_token
        except Exception as e:
            logger.error(f"Failed to decrypt token pair: {e}")
            raise

    def rotate_encryption_key(self) -> None:
        """
        Rotate the encryption key (for security best practices)
        Note: This would require re-encrypting all existing tokens
        """
        raise NotImplementedError("Key rotation is not supported with environment variable-based keys.")
    
    @classmethod
    def generate_new_key(cls) -> str:
        """Generate a new encryption key for initial setup"""
        key = Fernet.generate_key()
        return key.decode()

# Global instance
_token_encryption = TokenEncryption()

def encrypt_token(token: str) -> str:
    """Convenience function to encrypt a token"""
    return _token_encryption.encrypt_token(token)

def decrypt_token(encrypted_token: str) -> str:
    """Convenience function to decrypt a token"""
    return _token_encryption.decrypt_token(encrypted_token)

def encrypt_token_pair(access_token: str, refresh_token: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Convenience function to encrypt token pair"""
    return _token_encryption.encrypt_token_pair(access_token, refresh_token)

def decrypt_token_pair(encrypted_access_token: str, encrypted_refresh_token: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Convenience function to decrypt token pair"""
    return _token_encryption.decrypt_token_pair(encrypted_access_token, encrypted_refresh_token)