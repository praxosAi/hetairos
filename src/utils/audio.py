import base64
from pydub import AudioSegment
import io
from src.utils.logging.base_logger import setup_logger
import wave
from io import BytesIO

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



from io import BytesIO
from pydub import AudioSegment

def wav_bytes_to_ogg_bytes(wav_bytes: bytes) -> bytes:
    """
    Convert WAV audio bytes to OGG/Opus bytes (mono, 16 kHz).

    Args:
        wav_bytes: Raw audio in WAV format.

    Returns:
        OGG/Opus encoded audio as bytes.
    """
    # Load from bytes
    wav_io = BytesIO(wav_bytes)
    sound = AudioSegment.from_file(wav_io, format="wav")

    # Export to OGG/Opus in memory
    ogg_io = BytesIO()
    sound.export(
        ogg_io,
        format="ogg",
        codec="libopus",
        parameters=["-ac", "1", "-ar", "16000"]  # mono, 16 kHz
    )

    # Rewind and return raw bytes
    ogg_io.seek(0)
    return ogg_io.read()


def caf_bytes_to_ogg_bytes(caf_bytes: bytes) -> bytes:
    """
    Convert CAF audio bytes to OGG/Opus bytes (mono, 16 kHz).

    Args:
        caf_bytes: Raw audio in CAF format.

    Returns:
        OGG/Opus encoded audio as bytes.
    """
    # Load CAF from bytes
    caf_io = BytesIO(caf_bytes)
    sound = AudioSegment.from_file(caf_io, format="caf")

    # Export to OGG/Opus in memory
    ogg_io = BytesIO()
    sound.export(
        ogg_io,
        format="ogg",
        codec="libopus",
        parameters=["-ac", "1", "-ar", "16000"]  # mono, 16 kHz
    )

    # Rewind and return raw bytes
    ogg_io.seek(0)
    return ogg_io.read()



def caf_path_to_ogg_bytes(caf_path: str) -> bytes:
    """
    Convert a CAF audio file on disk to OGG/Opus bytes (mono, 16 kHz).

    Args:
        caf_path: Path to a .caf file.

    Returns:
        OGG/Opus encoded audio as bytes.
    """
    # Load CAF from path
    sound = AudioSegment.from_file(caf_path, format="caf")

    # Export to OGG/Opus in memory
    from io import BytesIO
    ogg_io = BytesIO()
    sound.export(
        ogg_io,
        format="ogg",
        codec="libopus",
        parameters=["-ac", "1", "-ar", "16000"]  # mono, 16 kHz
    )

    # Rewind and return raw bytes
    ogg_io.seek(0)
    return ogg_io.read()


def wave_file(pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2, filename: str | None = None):
    """
    Write PCM bytes as a WAV file.
    
    Args:
        pcm: Raw PCM audio bytes.
        channels: Number of channels (1=mono, 2=stereo).
        rate: Sampling rate in Hz.
        sample_width: Sample width in bytes (2=16-bit).
        filename: If given, write to this file. If None, return bytes in memory.
    
    Returns:
        None if filename is provided. If filename is None, returns WAV bytes.
    """
    buffer = BytesIO() if filename is None else open(filename, "wb")

    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

    if filename is None:
        buffer.seek(0)
        return buffer.read()
    else:
        buffer.close()
        return None