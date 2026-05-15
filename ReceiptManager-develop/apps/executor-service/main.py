from fastapi import FastAPI
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from fastapi.middleware.cors import CORSMiddleware
from app.api import router
from app.core.config import settings
from app.clients.db_client import DBClient
from app.agent.llm import get_llm
from app.agent.agent import get_agent
from app.agent.agent import get_receipt_agent, get_room_agent
from app.core.logger import get_logger
import uvicorn
import asyncio
import sys


logger = get_logger(__name__)


async def _connect_to_checkpointer_with_retry(conn_string: str, db_name: str, max_retries: int = 5):

    last_exception = None
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Attempt {attempt}/{max_retries}: Connecting to {db_name} checkpointer...")
            checkpointer = AsyncPostgresSaver.from_conn_string(conn_string)
            logger.info(f"Successfully connected to {db_name} checkpointer")
            return checkpointer
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = min(2 ** (attempt - 1), 30)
                logger.warning(
                    f"Failed to connect to {db_name} checkpointer (attempt {attempt}/{max_retries}): {str(e)}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to connect to {db_name} checkpointer after {max_retries} attempts")
    
    raise Exception(f"Could not connect to {db_name} checkpointer after {max_retries} retries") from last_exception


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to checkpointers with retry logic
    receipt_checkpointer = await _connect_to_checkpointer_with_retry(
        settings.langgraph_receipt_db_url,
        "receipt"
    )
    room_checkpointer = await _connect_to_checkpointer_with_retry(
        settings.langgraph_room_db_url,
        "room"
    )
    
    async with receipt_checkpointer as receipt_cp, room_checkpointer as room_cp:
        logger.info("Initialized postgres checkpointer instances")
        await receipt_cp.setup()
        await room_cp.setup()
        logger.info("Postgres checkpointers were set up")
        app.state.llm = get_llm()
        app.state.db_client = DBClient()
        app.state.agent = get_agent()
        app.state.receipt_agent = get_receipt_agent(receipt_cp)
        app.state.room_agent = get_room_agent(room_cp)

        yield
        await app.state.db_client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Executor service", version="1.0.0", lifespan=lifespan)

    #TODO change name, not router.router
    app.include_router(router.router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

app = create_app()

if __name__ == "__main__":

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="0.0.0.0", port=8002)
