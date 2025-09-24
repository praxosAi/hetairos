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
class OutputGenerator:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)


    async def generate_image(self, prompt: str, prefix: str) -> str:
        """
        Generates an image based on a text prompt using the Gemini API.
        """
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=[prompt],
        )
        logger.info(f"image generated")
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                ### we will want to upload the bytes to blob storage and return the link
                image_data = part.inline_data.data
                file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.png"
                image_blob_name = await upload_bytes_to_blob_storage(image_data, f"{prefix}/{file_name}", content_type="image/png")
                image_blob_sas_url = await get_blob_sas_url(image_blob_name)
                return image_blob_sas_url, file_name

        return None

    async def generate_speech(self, text: str, prefix: str, imessage_scenario: bool = False) -> str:
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
                    voice_name='Kore',
                    )
                )
            ),
        )
        )
        logger.info(f"speech generated")
        data = response.candidates[0].content.parts[0].inline_data
        if data and data.data:
            wave_bytes = wave_file(data.data) 
            ogg_bytes = wav_bytes_to_ogg_bytes(wave_bytes)
            if imessage_scenario:
                caf_bytes = ogg_bytes_to_caf_bytes(ogg_bytes)
                file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.caf"
                audio_blob_name = await upload_bytes_to_blob_storage(caf_bytes,  f"{prefix}/generated_audio/{file_name}", content_type="audio/x-caf")
                audio_blob_sas_url = await get_blob_sas_url(audio_blob_name)
                return audio_blob_sas_url, file_name
                
            file_name = f"{datetime.datetime.utcnow().isoformat()}_{uuid.uuid4()}.ogg"
            audio_blob_name = await upload_bytes_to_blob_storage(ogg_bytes,  f"{prefix}/generated_audio/{file_name}", content_type="audio/ogg")
            audio_blob_sas_url = await get_blob_sas_url(audio_blob_name)
            return audio_blob_sas_url, file_name
        return None,None
    async def generate_video(self, prompt: str, prefix: str) -> str:
        """
        Generates a video based on a text prompt using the Gemini API.
        This is an asynchronous operation.
        """
        operation = self.client.models.generate_videos(
            model="veo-3.0-generate-001",
            prompt=prompt,
        )

        # Poll the operation status until the video is ready.
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
        return video_blob_sas_url, video_file_name