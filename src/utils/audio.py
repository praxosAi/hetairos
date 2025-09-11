import base64
from pydub import AudioSegment
import io
from src.utils.logging.base_logger import setup_logger

logger = setup_logger(__name__)

def convert_ogg_b64_to_wav_b64(ogg_b64_data: str) -> str:
    """
    Converts a base64-encoded OGG audio string to a base64-encoded WAV string.

    Args:
        ogg_b64_data: The base64-encoded string of the OGG audio data.

    Returns:
        A base64-encoded string of the audio data in WAV format.
    """
    try:
        logger.info("Converting base64 OGG to base64 WAV...")
        # Decode the base64 string into raw bytes
        ogg_bytes = base64.b64decode(ogg_b64_data)
        
        # Load the OGG data from the in-memory bytes
        audio = AudioSegment.from_file(io.BytesIO(ogg_bytes), format="ogg")

        # Create an in-memory buffer to hold the WAV data
        wav_buffer = io.BytesIO()

        # Export the audio to the buffer in WAV format
        audio.export(wav_buffer, format="wav")

        # Go to the beginning of the buffer and get the bytes
        wav_buffer.seek(0)
        wav_bytes = wav_buffer.read()

        # Encode the WAV bytes back to a base64 string and return
        return base64.b64encode(wav_bytes).decode('ascii')

    except Exception as e:
        logger.error(f"Error converting base64 OGG to base64 WAV: {e}", exc_info=True)
        raise
