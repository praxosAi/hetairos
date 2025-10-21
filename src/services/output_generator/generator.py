import logging
from google import genai
from google.genai import types
from src.config.settings import settings
from src.utils.logging import setup_logger
from src.utils.blob_utils import upload_bytes_to_blob_storage,get_blob_sas_url
from src.utils.audio import wave_file, wav_bytes_to_ogg_bytes, ogg_bytes_to_caf_bytes
logger = setup_logger(__name__)


import datetime
import time
import uuid
from typing import Optional
from enum import Enum
class GeminiVoice(str, Enum):
    ZEPHYR = "Zephyr"
    PUCK = "Puck"
    CHARON = "Charon"
    KORE = "Kore"
    FENRIR = "Fenrir"
    LEDA = "Leda"
    ORUS = "Orus"
    AOEDE = "Aoede"
    CALLIRRHOE = "Callirrhoe"
    AUTONOE = "Autonoe"
    ENCELADUS = "Enceladus"
    IAPETUS = "Iapetus"
    UMBRIEL = "Umbriel"
    ALGIEBA = "Algieba"
    DESPINA = "Despina"
    ERINOME = "Erinome"
    ALGENIB = "Algenib"
    RASALGETHI = "Rasalgethi"
    LAOMEDEIA = "Laomedeia"
    ACHERNAR = "Achernar"
    ALNILAM = "Alnilam"
    SCHEDAR = "Schedar"
    GACRUX = "Gacrux"
    PULCHERRIMA = "Pulcherrima"
    ACHIRD = "Achird"
    ZUBENELGENUBI = "Zubenelgenubi"
    VINDEMIATRIX = "Vindemiatrix"
    SADACHBIA = "Sadachbia"
    SADALTAGER = "Sadaltager"
    SULAFAT = "Sulafat"



class OutputGenerator:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)


    async def generate_image(self, prompt: str, prefix: str, media_ids: list=[], reference_image_bytes: list=[]) -> str:
        """
        Generates an image based on a text prompt using the Gemini API.

        Args:
            prompt: Text description of the image to generate
            prefix: Blob storage prefix for organization
            media_ids: Legacy parameter (deprecated, use reference_image_bytes)
            reference_image_bytes: List of (bytes, mime_type) tuples for reference images

        Returns:
            Tuple of (url, file_name, blob_path)
        """
        # Build contents list with prompt and optional reference images
        contents = [prompt]

        # Add reference images if provided
        if reference_image_bytes:
            for img_bytes, mime_type in reference_image_bytes:
                try:
                    image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                    contents.append(image_part)
                    logger.info(f"Added reference image ({mime_type}) to generation context")
                except Exception as e:
                    logger.warning(f"Could not add reference image: {e}")

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=contents,
        )
        logger.info(f"image generated")
        for part in response.candidates[0].content.parts:
            
            if part.inline_data is not None:
                ### we will want to upload the bytes to blob storage and return the link
                image_data = part.inline_data.data
                file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.png"
                image_blob_name = await upload_bytes_to_blob_storage(image_data, f"{prefix}/{file_name}", content_type="image/png", container_name="cdn-container")
                image_blob_sas_url = await get_blob_sas_url(image_blob_name,container_name="cdn-container")
                return image_blob_sas_url, file_name, image_blob_name  # Return blob_path too

        return None, None, None

    async def generate_speech(self, text: str, prefix: str, imessage_scenario: bool = False, voice: Optional[GeminiVoice] = GeminiVoice.KORE) -> str:
        """
        Generates speech from text using the Gemini API.
        """
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=[text],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice.value,
                        )
                    )
                ),
            ),
        )
        logger.info(f"speech generated")
        data = response.candidates[0].content.parts[0].inline_data
        if data and data.data:
            wave_bytes = wave_file(data.data) 
            ogg_bytes = wav_bytes_to_ogg_bytes(wave_bytes)
            logger.info(f"Generated OGG audio")
            if imessage_scenario:
                logger.info(f"Converting OGG to CAF for iMessage compatibility")
                caf_bytes = ogg_bytes_to_caf_bytes(ogg_bytes)
                file_name = f"{uuid.uuid4().hex}.caf"
                audio_blob_name = await upload_bytes_to_blob_storage(caf_bytes,  f"{prefix}/generated_audio/{file_name}", content_type="audio/x-caf")
                audio_blob_sas_url = await get_blob_sas_url(audio_blob_name)
                return audio_blob_sas_url, file_name, audio_blob_name  # Return blob_path too

            file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.ogg"
            audio_blob_name = await upload_bytes_to_blob_storage(ogg_bytes,  f"{prefix}/generated_audio/{file_name}", content_type="audio/ogg")
            audio_blob_sas_url = await get_blob_sas_url(audio_blob_name)
            return audio_blob_sas_url, file_name, audio_blob_name  # Return blob_path too
        return None, None, None
    async def generate_video(self, prompt: str, prefix: str, reference_image_bytes:list={}) -> str:
        """
        Generates a video based on a text prompt using the Gemini API.
        This is an asynchronous operation.
        """
        im = None
        if reference_image_bytes and len(reference_image_bytes) > 0:
            for img_obj in reference_image_bytes:
                try:
                    im = types.Image(image_bytes=img_obj['img_bytes'], mime_type=img_obj['mime_type'])
                    break
                except Exception as e:
                    logger.error(f"Error creating image for video generation: {e}")
        # Poll the operation status until the video is ready.
        if im:
            operation = self.client.models.generate_videos(
                model="veo-3.1-generate-preview",
                prompt=prompt,
                image=im,
            )
        else:
            operation = self.client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=prompt,
            )
        while not operation.done:
            print("Waiting for video generation to complete...")
            time.sleep(10)
            operation = self.client.operations.get(operation)
        print("Video generation completed.")
        # Download the generated video.
        generated_video = operation.response.generated_videos[0]
        self.client.files.download(file=generated_video.video)
        video_file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.mp4"
        video_blob_name = await upload_bytes_to_blob_storage(generated_video.video.video_bytes, f"{prefix}/generated_video/{video_file_name}", content_type="video/mp4")
        video_blob_sas_url = await get_blob_sas_url(video_blob_name)
        return video_blob_sas_url, video_file_name, video_blob_name  # Return blob_path too