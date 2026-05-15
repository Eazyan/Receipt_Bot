from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers import items, receipts, rooms, users
# from contextlib import asynccontextmanager
import uvicorn

app = FastAPI(title="DB Service", version="1.0.0")

# @asynccontextmanager
# async def lifespan(app: FastAPI):

#     yield

def create_app() -> FastAPI:
    app = FastAPI(title="DB API", version="1.0.0")

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

    app.include_router(users.router)
    app.include_router(receipts.router)
    app.include_router(rooms.router)
    app.include_router(items.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
