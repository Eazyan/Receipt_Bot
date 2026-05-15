from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import Optional
import os
import httpx
from app.api.dependencies import DB

from app.api.schemas import CommandResult, ReceiptItemOut, ReceiptOut, ReceiptUpdate, Transcription

router = APIRouter(prefix="/agent", tags=["agent commands"])
#
#
# @router.post("/command", response_model=CommandResult, status_code=201)
# def execute_voice_command(
#         request: Request,
#         db: DB,
#         file: Optional[UploadFile] = File(None),
#         url: Optional[str] = Form(None),
#         ):
#     """
#     Transcribe audio from an uploaded file or a URL.
#     Exactly one of file or url must be provided.
#     """
#
#
#     if file is not None:
#         suffix = os.path.splitext(file.filename or "")[-1].lower() or ".wav"
#     """Transcription - response format for ASR"""
#

@router.post("/command", response_model=CommandResult, status_code=201)
def execute_voice_command(
        request: Request,
        file: Optional[UploadFile] = File(None),
        url: Optional[str] = Form(None),
        ):
    """
    Transcribe audio from an uploaded file or a URL.
    Exactly one of file or url must be provided.
    """


    if file is not None:
        suffix = os.path.splitext(file.filename or "")[-1].lower() or ".wav"
    """Transcription - response format for ASR"""
