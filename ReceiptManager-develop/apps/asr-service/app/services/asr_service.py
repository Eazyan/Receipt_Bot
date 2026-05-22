import base64
from typing import Any

import httpx

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
        self.models = self._model_candidates()

        logger.info(f"ASR Service initialized with models: {', '.join(self.models)}")

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        user_prompt: str = "Transcribe the audio verbatim. Do not translate. Return only the transcribed text.",
    ) -> TranscriptionResponse:
        try:
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info(f"Transcribing audio ({len(audio_bytes)} bytes, format: {audio_format})")

            response_data, used_model = await self._transcribe_with_fallbacks(
                audio_base64=audio_base64,
                audio_format=audio_format,
                user_prompt=user_prompt,
            )

            transcribed_text = str(response_data.get("text") or "").strip()

            if not self._is_usable_transcription(transcribed_text):
                raise ASRProcessingError(f"Model returned unusable transcription: {transcribed_text!r}")

            logger.info(f"Transcription successful: {transcribed_text[:100]}...")

            language = self._detect_language(transcribed_text)

            return TranscriptionResponse(
                text=transcribed_text,
                language=language,
                model=used_model,
                confidence=1.0,
            )

        except Exception as e:
            error_msg = f"ASR transcription failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ASRProcessingError(error_msg) from e

    def _model_candidates(self) -> list[str]:
        models = [settings.asr_model, *settings.asr_fallback_models.split(",")]
        result: list[str] = []
        for model in models:
            clean_model = model.strip()
            if clean_model and clean_model not in result:
                result.append(clean_model)
        return result

    async def _transcribe_with_fallbacks(
        self,
        audio_base64: str,
        audio_format: str,
        user_prompt: str | None,
    ) -> tuple[dict[str, Any], str]:
        errors: list[str] = []
        for model in self.models:
            try:
                response_data = await self._transcribe_via_stt_endpoint(
                    model=model,
                    audio_base64=audio_base64,
                    audio_format=audio_format,
                    user_prompt=user_prompt,
                )
                return response_data, model
            except ASRProcessingError as exc:
                errors.append(f"{model}: {exc}")
                logger.warning(f"ASR model failed, trying fallback if available: {model}: {exc}")

        raise ASRProcessingError("; ".join(errors) or "All ASR models failed")

    async def _transcribe_via_stt_endpoint(
        self,
        model: str,
        audio_base64: str,
        audio_format: str,
        user_prompt: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input_audio": {
                "data": audio_base64,
                "format": audio_format,
            },
            "temperature": settings.asr_temperature,
        }
        if settings.asr_language:
            payload["language"] = settings.asr_language
        prompt = " ".join((user_prompt or settings.asr_prompt or "").split()).strip()
        if prompt:
            payload["prompt"] = prompt[:1800]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.asr_timeout) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url.rstrip('/')}/audio/transcriptions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise ASRProcessingError(f"OpenRouter request timed out after {settings.asr_timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ASRProcessingError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise ASRProcessingError(f"HTTP {response.status_code}: {detail}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ASRProcessingError("OpenRouter returned non-JSON response") from exc

        text = str(data.get("text") or "").strip()
        if not self._is_usable_transcription(text):
            raise ASRProcessingError(f"OpenRouter returned unusable transcription: {text!r}")

        return data

    def _is_usable_transcription(self, text: str) -> bool:
        cleaned = " ".join(text.split()).strip(" .,!?:;\"'«»")
        if len(cleaned) < 2:
            return False
        lowered = cleaned.lower()
        bad_phrases = {
            "you",
            "thanks",
            "thank you",
            "subtitles",
            "music",
            "silence",
        }
        return lowered not in bad_phrases

    def _extract_error_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:400]

        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("detail") or error)[:400]
            if isinstance(error, str):
                return error[:400]
            detail = data.get("detail")
            if detail:
                return str(detail)[:400]
        return str(data)[:400]

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
