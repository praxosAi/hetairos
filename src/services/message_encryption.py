import json
import base64
import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from src.services.token_encryption import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

class MessageEncryption:
    """
    Handles envelope encryption for large payloads (like email bodies).
    
    Mechanism:
    1. Generate a unique Data Encryption Key (DEK) for the item.
    2. Encrypt the item payload with the DEK.
    3. Encrypt the DEK with the Master Key (KEK) via token_encryption service.
    4. Store { "encrypted_data": ..., "encrypted_key": ... }
    """

    @staticmethod
    def encrypt_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypts a dictionary payload using envelope encryption.
        
        Args:
            payload: The dictionary to encrypt (e.g. email body)
            
        Returns:
            Dict containing encrypted data and key info.
        """
        try:
            # 1. Generate ephemeral DEK
            dek = Fernet.generate_key()
            f = Fernet(dek)

            # 2. Serialize and encrypt data
            json_data = json.dumps(payload).encode('utf-8')
            encrypted_data = f.encrypt(json_data)

            # 3. Encrypt the DEK using the system KEK
            # dek is bytes, token_encryption expects str usually, but let's check. 
            # token_encryption.encrypt_token takes str and returns b64 str.
            encrypted_dek = encrypt_token(dek.decode('utf-8'))

            return {
                "encrypted_data": base64.b64encode(encrypted_data).decode('utf-8'),
                "encrypted_key": encrypted_dek,
                "encryption_version": "v1",
                "is_encrypted": True
            }
        except Exception as e:
            logger.error(f"Failed to encrypt payload: {e}")
            raise

    @staticmethod
    def decrypt_payload(encrypted_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypts a payload if it is encrypted.
        
        Args:
            encrypted_payload: The dictionary from DB which might be encrypted.
            
        Returns:
            The original decrypted dictionary.
        """
        # Check if this is actually an encrypted packet
        if not isinstance(encrypted_payload, dict) or not encrypted_payload.get("is_encrypted"):
            # Not encrypted, return as-is
            return encrypted_payload

        try:
            # 1. Decrypt the DEK
            encrypted_key = encrypted_payload.get("encrypted_key")
            if not encrypted_key:
                raise ValueError("Missing encrypted_key in payload")
            
            dek_str = decrypt_token(encrypted_key)
            dek = dek_str.encode('utf-8')

            # 2. Decrypt the data
            encrypted_data_b64 = encrypted_payload.get("encrypted_data")
            if not encrypted_data_b64:
                raise ValueError("Missing encrypted_data in payload")
                
            encrypted_data = base64.b64decode(encrypted_data_b64)
            
            f = Fernet(dek)
            decrypted_json = f.decrypt(encrypted_data)
            
            return json.loads(decrypted_json.decode('utf-8'))

        except Exception as e:
            logger.error(f"Failed to decrypt payload: {e}")
            # In a partial failure, we might want to re-raise or return raw. 
            # Re-raising is safer to prevent data corruption assumptions.
            raise

message_encryption = MessageEncryption()
