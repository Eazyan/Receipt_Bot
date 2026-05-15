from fastapi import UploadFile
import httpx

from app.core.config import settings


class ASRServiceError(RuntimeError):
    pass


class ASRTimeoutError(ASRServiceError):
    pass


class ASRConnectionError(ASRServiceError):
    pass


async def transcribe_audio(audio_file: UploadFile) -> str:
    data = await audio_file.read()
    if not data:
        raise ASRServiceError("Audio file is empty")

    files = {
        "file": (
            audio_file.filename or "voice.webm",
            data,
            audio_file.content_type or "audio/webm",
        )
    }

    try:
        async with httpx.AsyncClient(base_url=settings.asr_service_url, timeout=settings.asr_timeout_seconds) as client:
            response = await client.post("/transcribe", files=files)
            response.raise_for_status()
            payload = response.json()
            text = payload.get("text")
            if not text:
                raise ASRServiceError("ASR service returned empty text")
            return text
    except httpx.TimeoutException as exc:
        raise ASRTimeoutError(str(exc)) from exc
    except httpx.ConnectError as exc:
        raise ASRConnectionError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ASRServiceError(str(exc)) from exc
