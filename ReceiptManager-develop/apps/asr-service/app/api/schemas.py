from pydantic import BaseModel, Field


class TranscriptionRequest(BaseModel):
    """Request for transcribing audio"""
    text: str = Field(description="Description or question about the audio")


class TranscriptionResponse(BaseModel):
    """Response with transcribed text"""
    text: str = Field(description="Transcribed text from audio")
    language: str = Field(default="unknown", description="Detected language")
    model: str = Field(description="Model used for transcription")
    confidence: float = Field(default=1.0, description="Confidence score (0-1)")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(description="Service status")
    version: str = Field(description="Service version")
    model: str = Field(description="ASR model being used")
