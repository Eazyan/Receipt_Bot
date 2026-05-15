from functools import lru_cache
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict
from typing import Callable


from app.agent.llm import get_llm
from app.agent.prompts import RECEIPT_SYSTEM_PROMPT, ROOM_SYSTEM_PROMPT
from app.agent.schemas import AgentRoomState, AgentReceiptState, AgentState
from app.agent.tools.manager import get_all_tools, get_receipt_tools, get_room_tools
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class AgentBuilder:
    """Строитель для создания агента"""

    def __init__(self):
        self.llm = get_llm()
        self.tools = get_all_tools()
        self.system_prompt = RECEIPT_SYSTEM_PROMPT
        self.state_schema = None
        self.checkpointer = None

    def with_llm(self, llm):
        """Установить кастомный LLM"""
        self.llm = llm
        return self

    def with_tools(self, tools: list[Callable]):
        """Установить кастомный набор инструментов"""
        self.tools = tools
        return self

    def with_system_prompt(self, prompt: str):
        """Установить кастомный system prompt"""
        self.system_prompt = prompt
        return self

    def with_state_schema(self, state_schema: TypedDict):
        """Установить кастомный state schema"""
        self.state_schema  = state_schema
        return self

    def with_max_iterations(self, max_iterations: int):
        """Установить максимальное количество итераций"""
        self.max_iterations = max_iterations
        return self

    def with_memory(self, checkpointer: AsyncPostgresSaver):
        """Добавить персистентную память (checkpointer)"""
        self.checkpointer = checkpointer
        return self

    def build(self) -> CompiledStateGraph:
        """Создаёт и возвращает готового агента"""
        logger.info(
            f"Building agent with {len(self.tools)} tools"
            # f"with_max_iterations={self.max_iterations}"
        )

        # Создаём ReAct агента через LangGraph
        agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt,  # system message
            state_schema=self.state_schema,
            checkpointer=self.checkpointer,
        )

        return agent


class AgentExecutor:
    """Обёртка над агентом для удобного выполнения"""

    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    async def ainvoke(
            self,
            message: str,
            session_id: str | None = None,
            config: RunnableConfig | None = None,
    ) -> dict:
        """
        Асинхронное выполнение агента.

        Args:
            message: Входящее сообщение пользователя
            session_id: ID сессии для персистентности
            config: Дополнительная конфигурация

        Returns:
            Результат выполнения агента
        """
        logger.info(f"Agent invoked with message: {message[:50]}...")

        # Формируем входные данные
        input_data = {
            "messages": [HumanMessage(content=message),],
            "user_id": config.get("configurable", {}).get("user_id"),
            "receipt_id": config.get("configurable", {}).get("receipt_id"),
        }
        # Конфигурация с session_id для checkpointer
        run_config = dict(config or {})
        run_config.setdefault("configurable", {})
        if session_id:
            run_config["configurable"]["thread_id"]=session_id
        try:
            result = await self.agent.ainvoke(input_data, config=run_config)

            logger.info(f"Agent completed successfully")
            return self._format_result(result)

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            raise

    async def astream(
            self,
            message: str,
            session_id: str | None = None,
    ):
        """
        Стриминговое выполнение агента (для real-time вывода).

        Yields:
            Чанки результата по мере выполнения
        """
        input_data = {"messages": [HumanMessage(content=message)]}

        config = {}
        if session_id:
            config["configurable"] = {"thread_id": session_id}

        async for event in self.agent.astream(input_data, config=config):
            yield event

    def _format_result(self, result: dict) -> dict:
        """
        Форматирует результат агента в удобную структуру.

        Args:
            result: Сырой результат от LangGraph

        Returns:
            Отформатированный результат
        """
        messages = result.get("messages", [])

        # Последнее AI сообщение — финальный ответ
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        final_answer = ai_messages[-1].content if ai_messages else "No response"

        # Собираем информацию о вызванных tools
        tool_calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_calls.append({
                        "name": tool_call.get("name"),
                        "args": tool_call.get("args"),
                    })

        response = {
            "answer": final_answer,
            "tools_used": [tc["name"] for tc in tool_calls],
            "tool_calls": tool_calls,
            "message_count": len(messages),
        }

        # Добавляем специфичные для каждого агента поля
        if "receipt_updated" in result:
            response["receipt_updated"] = result.get("receipt_updated", False)
        if "assignment_updated" in result:
            response["assignment_updated"] = result.get("assignment_updated", False)
        if "action_required" in result:
            response["action_required"] = result.get("action_required", False)
        if "error" in result:
            errors = result.get("error", [])
            response["error"] = errors[0] if errors else None

        return response



# Singleton pattern для агента
_agent_executor: AgentExecutor | None = None


@lru_cache(maxsize=1)
def build_default_agent() -> AgentExecutor:
    """Создаёт агента по умолчанию (singleton)"""
    agent = AgentBuilder().build()
    return AgentExecutor(agent)


@lru_cache(maxsize=1)
def build_receipt_agent(
        checkpointer: AsyncPostgresSaver | None = None
) -> AgentExecutor:
    """Создаёт агента по управлению чеком (singleton)"""
    tools = get_receipt_tools()
    prompt = RECEIPT_SYSTEM_PROMPT

    agent = (AgentBuilder().
             with_tools(tools).
             with_system_prompt(prompt).
             with_state_schema(AgentState).
             with_memory(checkpointer).
             build())
    return AgentExecutor(agent)


@lru_cache(maxsize=1)
def build_room_agent(
        checkpointer: AsyncPostgresSaver | None = None
) -> AgentExecutor:
    """Создаёт агента по управлению комнатой (singleton)"""
    tools = get_room_tools()
    prompt = ROOM_SYSTEM_PROMPT

    agent = (AgentBuilder().
             with_tools(tools).
             with_system_prompt(prompt).
             with_state_schema(AgentState).
             with_memory(checkpointer).
             build())
    return AgentExecutor(agent)


def get_agent() -> AgentExecutor:
    """
    Возвращает singleton инстанс агента.

    Returns:
        Готовый к использованию AgentExecutor
    """
    global _agent_executor

    if _agent_executor is None:
        _agent_executor = build_default_agent()

    return _agent_executor


_receipt_agent_executor: AgentExecutor | None = None


def get_receipt_agent(checkpointer: AsyncPostgresSaver | None = None) -> AgentExecutor:
    """
    Возвращает singleton инстанс агента по управлению чеком.

    Returns:
        Готовый к использованию AgentExecutor
    """
    global _receipt_agent_executor

    if _receipt_agent_executor is None:
        _receipt_agent_executor = build_receipt_agent(checkpointer)

    return _receipt_agent_executor

_room_agent_executor: AgentExecutor | None = None


def get_room_agent(checkpointer: AsyncPostgresSaver | None = None) -> AgentExecutor:
    """
    Возвращает singleton инстанс агента по управлению комнатой.

    Returns:
        Готовый к использованию AgentExecutor
    """
    global _room_agent_executor

    if _room_agent_executor is None:
        _room_agent_executor = build_room_agent(checkpointer)

    return _room_agent_executor


async def quick_ask(question: str) -> str:
    """
    Быстрый вопрос к агенту без создания сессии.
    Args:
        question: Вопрос пользователя
    Returns:
        Ответ агента (только текст)
    """
    agent = get_agent()
    result = await agent.ainvoke(question)
    return result["answer"]


async def debug_agent_run(message: str):
    """
    Выполняет агента с подробным логированием для отладки.
    """
    agent = get_agent()

    print(f"\n{'=' * 60}")
    print(f"DEBUG: Running agent with message: {message}")
    print(f"{'=' * 60}\n")

    async for event in agent.astream(message):
        print(f"Event: {event}")
        print("-" * 60)

    print(f"\n{'=' * 60}")
    print("DEBUG: Agent execution completed")
    print(f"{'=' * 60}\n")