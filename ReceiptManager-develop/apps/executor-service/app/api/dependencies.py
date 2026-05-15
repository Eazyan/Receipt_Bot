from fastapi import Request, Depends
from typing import Annotated
from app.clients.db_client import DBClient
from app.agent.agent import AgentExecutor
from langchain_core.language_models.chat_models import BaseChatModel


def get_db_client(request: Request) -> DBClient:
    """получение DBClient из app.state."""
    return request.app.state.db_client

DB = Annotated[DBClient, Depends(get_db_client)]


def get_current_agent(request: Request):
    return request.app.state.agent

Agent = Annotated[AgentExecutor, Depends(get_current_agent)]

def get_receipt_agent(request: Request):
    return request.app.state.receipt_agent

ReceiptAgent = Annotated[AgentExecutor, Depends(get_receipt_agent)]

def get_room_agent(request: Request):
    return request.app.state.room_agent

RoomAgent = Annotated[AgentExecutor, Depends(get_room_agent)]

def get_current_llm(request: Request):
    return request.app.state.llm

LLM = Annotated[BaseChatModel, Depends(get_current_llm)]
