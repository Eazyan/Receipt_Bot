from fastapi import APIRouter, Request, UploadFile, File
from app.api.schemas import ChatRequest
from app.api.dependencies import DB, ReceiptAgent, RoomAgent
from langchain_core.runnables import RunnableConfig
from app.core.logger import get_logger
from app.clients.asr_client import transcribe_audio, ASRServiceError, ASRTimeoutError, ASRConnectionError


logger = get_logger(__name__)


router = APIRouter(prefix="/receipt", tags=["receipt agent commands"])


@router.post("/chat")
async def chat_with_agent(
        request: ChatRequest,
        db: DB,
        # llm: LLM,
        receipt_agent: ReceiptAgent,
        room_agent: RoomAgent,
        ) -> dict:
    # TODO: Добавить обработку состояний - отправка на фронт сообщений

    agent = room_agent if request.task_type == "room" else receipt_agent
    task_type = "room" if request.task_type == "room" else "receipt"
    config = RunnableConfig(
        configurable = {
            "user_id": request.user_id,
            "receipt_id": request.receipt_id,
            "room_id": request.room_id,
            "db_client": db,
            "agent": agent,
            "thread_id": f"{task_type}_{request.user_id}:{request.receipt_id}"
        }
    )

    response = await agent.ainvoke(
        request.user_message,
        config=config
    )
    logger.info(response)
    answer = response.get("answer", {})

    result = {
        "answer": answer,
        "tools_used": response.get("tools_used", []),
        "message_count": response.get("message_count", 0),
    }

    if "action_required" in response and response["action_required"]:
        result["action_required"] = response["action_required"]
    if "error" in response and response["error"]:
        result["error"] = response["error"]

    return result


@router.post("/voice")
async def process_voice_message(
        audio_file: UploadFile = File(...),
        user_id: int = None,
        receipt_id: int = None,
        task_type: str = "receipt",
        room_id: int | None = None,
        db: DB = None,
        receipt_agent: ReceiptAgent = None,
        room_agent: RoomAgent = None,
) -> dict:
    """
    Обработка голосовой команды через ASR service.
    
    1. Расшифровать аудио используя ASR service
    2. Добавляет voice recognition marker к сообщению
    3. Отправялет агенту команду
    
    Args:
        audio_file: Аудио файл для расшифровки
        user_id: User ID
        receipt_id: Receipt ID
        task_type: "receipt" или "room"
        room_id: Room ID (нужно если task_type=="room")
        db, receipt_agent, room_agent: Injected dependencies
        
    Returns:
        dict с результатами работы сервиса
    """
    
    logger.info(f"Voice input received from user {user_id}, task_type={task_type}")
    
    try:

        logger.info(f"Transcribing audio: {audio_file.filename}")
        transcribed_text = await transcribe_audio(audio_file)
        
        # Сообщаем агенту, что текст взял из аудио и может содержать в себе ошибки
        marked_message = f"[VOICE_RECOGNIZED]\n{transcribed_text}"
        
        logger.info("Passing transcribed text to agent")
        
        agent = room_agent if task_type == "room" else receipt_agent
        config = RunnableConfig(
            configurable = {
                "user_id": user_id,
                "receipt_id": receipt_id,
                "room_id": room_id,
                "db_client": db,
                "agent": agent,
                "thread_id": f"{task_type}_{user_id}:{receipt_id}"
            }
        )
        
        response = await agent.ainvoke(
            marked_message,
            config=config
        )
        logger.info(f"Voice processing completed for user {user_id}")
        answer = response.get("answer", {})
        
        result = {
            "answer": answer,
            "tools_used": response.get("tools_used", []),
            "message_count": response.get("message_count", 0),
            "recognized_text": transcribed_text,  # Include original text
        }

        if "action_required" in response and response["action_required"]:
            result["action_required"] = response["action_required"]
        if "error" in response and response["error"]:
            result["error"] = response["error"]

        return result
    
    except ASRTimeoutError as e:
        error_msg = (
            "Голосовой сервис не ответил за отведенное время. "
            "Попробуйте еще раз или используйте текстовый ввод."
        )
        logger.error(f"ASR timeout: {str(e)}")
        return {
            "answer": error_msg,
            "tools_used": [],
            "message_count": 0,
            "error": "ASR_TIMEOUT"
        }
    
    except ASRConnectionError as e:
        error_msg = (
            "Не удалось подключиться к голосовому сервису. "
            "Сервис может быть недоступен. Используйте текстовый ввод."
        )
        logger.error(f"ASR connection error: {str(e)}")
        return {
            "answer": error_msg,
            "tools_used": [],
            "message_count": 0,
            "error": "ASR_CONNECTION_ERROR"
        }
    
    except ASRServiceError as e:
        error_msg = (
            "Ошибка при обработке голоса. "
            "Используйте текстовый ввод или попробуйте позже."
        )
        logger.error(f"ASR service error: {str(e)}")
        return {
            "answer": error_msg,
            "tools_used": [],
            "message_count": 0,
            "error": "ASR_SERVICE_ERROR"
        }
    
    except Exception as e:
        error_msg = (
            "Неожиданная ошибка при обработке голоса. "
            "Пожалуйста, используйте текстовый ввод."
        )
        logger.error(f"Unexpected error in voice processing: {str(e)}", exc_info=True)
        return {
            "answer": error_msg,
            "tools_used": [],
            "message_count": 0,
            "error": "UNKNOWN_ERROR"
        }
