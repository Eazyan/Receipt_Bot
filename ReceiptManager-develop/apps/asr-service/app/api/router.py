from fastapi import APIRouter, UploadFile, File, HTTPException
from app.core.logger import get_logger
from app.api.schemas import TranscriptionResponse, HealthResponse
from app.services.asr_service import get_asr_service, ASRError
from app.core.config import get_settings


logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["transcription"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint
    
    Returns:
        Health status and service information
    """
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        model=", ".join([settings.asr_model, *settings.asr_fallback_models.split(",")]),
    )


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    prompt: str | None = None,
) -> TranscriptionResponse:
    """
    Transcribe audio file to text using OpenRouter ASR model
    
    Supported formats: wav, mp3, ogg, flac, m4a, webm
    
    Args:
        file: Audio file to transcribe
        prompt: Custom prompt for the ASR model (optional)
        
    Returns:
        TranscriptionResponse with transcribed text
        
    Raises:
        HTTPException: If transcription fails
    """
    
    supported_formats = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm"}
    
    # Validate file format
    filename_lower = (file.filename or "").lower()
    file_ext = None
    for fmt in supported_formats:
        if filename_lower.endswith(fmt):
            file_ext = fmt[1:]  # Remove leading dot
            break
    
    if not file_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Supported: {', '.join(supported_formats)}",
        )
    
    try:
        logger.info(f"Transcribing file: {file.filename} ({file_ext})")
        
        # Read file content
        audio_bytes = await file.read()
        
        if not audio_bytes:
            raise HTTPException(
                status_code=400,
                detail="Audio file is empty",
            )
        
        if len(audio_bytes) > 25 * 1024 * 1024:  # 25 MB limit
            raise HTTPException(
                status_code=413,
                detail="Audio file too large (max 25 MB)",
            )
        
        # Get ASR service and transcribe
        asr_service = get_asr_service()
        result = await asr_service.transcribe(
            audio_bytes=audio_bytes,
            audio_format=file_ext,
            user_prompt=prompt,
        )
        
        logger.info(f"Transcription completed for {file.filename}")
        return result
    
    except ASRError as e:
        logger.error(f"ASR service error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}",
        ) from e
    
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Unexpected error during transcription",
        ) from e
    
    finally:
        await file.close()
