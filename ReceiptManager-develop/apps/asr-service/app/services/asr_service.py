import base64
from openrouter import OpenRouter
from app.core.config import get_settings
from app.core.logger import get_logger
from app.api.schemas import TranscriptionResponse


logger = get_logger(__name__)
settings = get_settings()


class ASRError(Exception):
    pass


class ASRConfigError(ASRError):
    pass


class ASRProcessingError(ASRError):
    pass


class ASRService:
    def __init__(self):
        if not settings.openrouter_api_key:
            raise ASRConfigError("OPENROUTER_API_KEY not configured")

        self.api_key = settings.openrouter_api_key
        self.model = settings.asr_model

        logger.info(f"ASR Service initialized with model: {self.model}")

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        user_prompt: str = "Transcribe the audio verbatim. Do not translate. Return only the transcribed text.",
    ) -> TranscriptionResponse:
        try:
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info(f"Transcribing audio ({len(audio_bytes)} bytes, format: {audio_format})")

            with OpenRouter(api_key=self.api_key) as client:
                response = client.chat.send(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an automatic speech recognition system. "
                                       "Transcribe audio exactly as spoken. "
                                       "Do not translate. Do not explain.",
                        },
                        {
                            "role": "user",
                            "content": user_prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": audio_base64,
                                        "format": audio_format,
                                    },
                                }
                            ],
                        },
                    ],
                    temperature=0,
                )

            if not response.choices or not response.choices[0].message:
                raise ASRProcessingError("Empty response from ASR model")

            transcribed_text = response.choices[0].message.content.strip()

            if not transcribed_text:
                raise ASRProcessingError("Model returned empty text")

            logger.info(f"Transcription successful: {transcribed_text[:100]}...")

            language = self._detect_language(transcribed_text)

            return TranscriptionResponse(
                text=transcribed_text,
                language=language,
                model=self.model,
                confidence=1.0,
            )

        except Exception as e:
            error_msg = f"ASR transcription failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ASRProcessingError(error_msg) from e

    def _detect_language(self, text: str) -> str:
        cyrillic_count = sum(1 for c in text if "\u0400" <= c <= "\u04FF")
        if cyrillic_count > len(text) * 0.3:
            return "ru"
        return "en"


_asr_service: ASRService | None = None


def get_asr_service() -> ASRService:
    global _asr_service
    if _asr_service is None:
        _asr_service = ASRService()
    return _asr_service