from app.core.logger import get_logger
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from app.agent.schemas import AgentReceiptState
from rapidfuzz import fuzz
from dataclasses import dataclass
from langgraph.types import Command
import httpx

logger = get_logger(__name__)


@dataclass
class UserSearchResult:
    """Результат поиска пользователя в комнате"""
    success: bool
    user_id: int | None = None
    username: str | None = None
    user_public_name: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class ItemSearchResult:
    """Результат поиска блюда в чеке"""
    success: bool
    item_id: int | None = None
    item_name: str | None = None
    error_type: str | None = None
    error_message: str | None = None


async def find_user_in_room(
        search_query: str,
        room_id: int,
        db_client,
) -> UserSearchResult:
    """
    Ищет пользователя в комнате по названию с использованием Fuzz поиска.

    Args:
        search_query: Поисковый запрос (имя пользователя)
        room_id: ID комнаты
        db_client: Клиент базы данных

    Returns:
        UserSearchResult с найденным user_id или описанием ошибки
    """
    try:
        participants = await db_client.get_room_participants(room_id)
    except Exception as e:
        return UserSearchResult(
            success=False,
            error_type="fetch_failed",
            error_message=f"Ошибка получения участников комнаты: {str(e)}"
        )

    if not participants:
        return UserSearchResult(
            success=False,
            error_type="no_participants",
            error_message="В комнате нет участников."
        )

    matches: list[tuple[int, any]] = []

    for participant in participants:
        # Используем public_name если доступно, иначе username
        display_name = participant.user_public_name or participant.username
        score = fuzz.partial_ratio(search_query.lower(), display_name.lower())
        if score > 75:
            matches.append((score, participant))

    matches.sort(key=lambda x: x[0], reverse=True)

    if not matches:
        return UserSearchResult(
            success=False,
            error_type="not_found",
            error_message=f"Пользователь '{search_query}' не найден в комнате."
        )

    if len(matches) > 1 and matches[0][0] - matches[1][0] < 10:
        options = [str(m[1].user_id) for m in matches[:3]]
        return UserSearchResult(
            success=False,
            error_type="ambiguous",
            error_message=f"Найдено несколько похожих пользователей: {options}. Уточни, какого имеешь в виду."
        )

    target = matches[0][1]

    return UserSearchResult(
        success=True,
        user_id=target.user_id,
        username=target.username,
        user_public_name=target.user_public_name
    )


async def find_item_by_name(
        search_query: str,
        receipt_id: int,
        db_client,
) -> ItemSearchResult:
    """
    Ищет блюдо в чеке по названию с использованием Fuzz поиска.

    Args:
        search_query: Поисковый запрос (название блюда)
        receipt_id: ID чека
        db_client: Клиент базы данных

    Returns:
        ItemSearchResult с найденным item_id или описанием ошибки
    """
    try:
        response = await db_client.get_receipt_items(receipt_id)
        items = response.items
    except Exception as e:
        return ItemSearchResult(
            success=False,
            error_type="fetch_failed",
            error_message=f"Ошибка получения позиций чека: {str(e)}"
        )

    if not items:
        return ItemSearchResult(
            success=False,
            error_type="no_items",
            error_message="В чеке нет позиций."
        )

    matches: list[tuple[int, any]] = []

    for item in items:
        score = fuzz.partial_ratio(search_query.lower(), item.name.lower())
        if score > 75:
            matches.append((score, item))

    matches.sort(key=lambda x: x[0], reverse=True)

    if not matches:
        return ItemSearchResult(
            success=False,
            error_type="not_found",
            error_message=f"Блюдо '{search_query}' не найдено в чеке."
        )

    if len(matches) > 1 and matches[0][0] - matches[1][0] < 10:
        options = [m[1].name for m in matches[:3]]
        return ItemSearchResult(
            success=False,
            error_type="ambiguous",
            error_message=f"Найдено несколько похожих блюд: {options}. Уточни, какое имеешь в виду."
        )

    target = matches[0][1]

    return ItemSearchResult(
        success=True,
        item_id=target.id,
        item_name=target.name
    )


@tool
async def assign_user_to_dish(
        user_search: str,
        dish_search: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Присваивает пользователя к блюду в чеке (например "Роман платит за утку").

    user_search — имя пользователя из участников комнаты
    dish_search — название блюда из чека

    Возвращает:
    Сообщение об успешном присвоении или описание ошибки.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")
    room_id = configurable.get("room_id")

    if not db_client:
        logger.error("Error: db_client not found in config configurable.")
        error = "unable to connect to DB: db_client not found in config configurable"
        error_message = "Системная ошибка: нет подключения к БД. Сообщи пользователю об ошибке."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id
                    ),
                ]
            }
        )

    if not receipt_id:
        logger.error("Error: receipt_id not found in config metadata.")
        error = "unable to assign: receipt_id not found in config metadata"
        error_message = "Ошибка: отсутствует ID чека. Убедись, что чек был создан."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id
                    ),
                ]
            }
        )

    if not room_id:
        logger.error("Error: room_id not found in config metadata.")
        error = "unable to assign: room_id not found in config metadata"
        error_message = "Ошибка: отсутствует ID комнаты."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id
                    ),
                ]
            }
        )

    # ищем блюдо в чеке
    dish_result = await find_item_by_name(dish_search, receipt_id, db_client)

    if not dish_result.success:
        return Command(
            update={
                "error": dish_result.error_type,
                "messages": [
                    ToolMessage(
                        content=dish_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # ищем пользователя в комнате
    user_result = await find_user_in_room(user_search, room_id, db_client)

    if not user_result.success:
        return Command(
            update={
                "error": user_result.error_type,
                "messages": [
                    ToolMessage(
                        content=user_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # проверяем, есть ли уже назначение для этого пользователя на это блюдо
    existing_assignments = await db_client.get_item_assignments(dish_result.item_id)
    user_already_assigned = any(a.user_id == user_result.user_id for a in existing_assignments)
    
    # присваиваем пользователя к блюду
    try:
        await db_client.assign_user_to_item(
            item_id=dish_result.item_id,
            user_id=user_result.user_id,
            paid="not paid"
        )

        logger.info(
            f"User {user_result.user_id} assigned to item {dish_result.item_id} "
            f"({dish_result.item_name}) in receipt {receipt_id}"
        )

        if user_already_assigned:
            success_message = (
                f"✓ Пользователь {user_search} уже был назначен на блюдо '{dish_result.item_name}'."
            )
        else:
            success_message = (
                f"✓ Пользователь {user_search} назначен на блюдо '{dish_result.item_name}'."
            )

        return Command(
            update={
                "error": None,
                "action_required": True,
                "messages": [
                    ToolMessage(
                        content=success_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else "Unknown"
        error_details = e.response.text if e.response else str(e)

        logger.error(
            f"HTTP {status_code}: failed to assign user {user_result.user_id} "
            f"to item {dish_result.item_id}",
            exc_info=True
        )

        error_message = f"Ошибка API при назначении: {status_code}. Детали: {error_details}"

        return Command(
            update={
                "error": f"HTTP {status_code}",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error(
            f"Unexpected error while assigning user {user_result.user_id} "
            f"to item {dish_result.item_id}",
            exc_info=True
        )

        error_message = f"Произошла непредвиденная ошибка при назначении: {str(e)}"

        return Command(
            update={
                "error": "unexpected_error",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


@tool
async def unassign_user_from_dish(
        user_search: str,
        dish_search: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Удаляет назначение пользователя с блюда (например "Роман больше не платит за утку").

    user_search — имя пользователя
    dish_search — название блюда

    Возвращает:
    Сообщение об успешном удалении или описание ошибки.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")
    room_id = configurable.get("room_id")

    if not db_client or not receipt_id or not room_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Ищем блюдо в чеке
    dish_result = await find_item_by_name(dish_search, receipt_id, db_client)

    if not dish_result.success:
        return Command(
            update={
                "error": dish_result.error_type,
                "messages": [
                    ToolMessage(
                        content=dish_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Ищем пользователя в комнате
    user_result = await find_user_in_room(user_search, room_id, db_client)

    if not user_result.success:
        return Command(
            update={
                "error": user_result.error_type,
                "messages": [
                    ToolMessage(
                        content=user_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Удаляем назначение пользователя с блюда
    try:
        await db_client.unassign_user_from_item(
            item_id=dish_result.item_id,
            user_id=user_result.user_id
        )

        logger.info(
            f"User {user_result.user_id} unassigned from item {dish_result.item_id} "
            f"({dish_result.item_name}) in receipt {receipt_id}"
        )

        success_message = (
            f"✓ Пользователь {user_search} удален с блюда '{dish_result.item_name}'."
        )

        return Command(
            update={
                "error": None,
                "action_required": True,
                "messages": [
                    ToolMessage(
                        content=success_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error(
            f"Error while unassigning user {user_result.user_id} "
            f"from item {dish_result.item_id}",
            exc_info=True
        )

        error_message = f"Ошибка при удалении назначения: {str(e)}"

        return Command(
            update={
                "error": "unassign_failed",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


@tool
async def update_payment_status(
        user_search: str,
        dish_search: str,
        status: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Изменяет статус оплаты для назначения пользователя на блюдо.

    user_search — имя пользователя
    dish_search — название блюда
    status — новый статус оплаты: "not paid" (не оплачено), "on review" (на проверке), "paid" (оплачено)

    Возвращает:
    Сообщение об успешном обновлении или описание ошибки.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")
    room_id = configurable.get("room_id")

    if not db_client or not receipt_id or not room_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Валидируем статус
    valid_statuses = ["not paid", "on review", "paid"]
    if status.lower() not in valid_statuses:
        return Command(
            update={
                "error": "invalid_status",
                "messages": [
                    ToolMessage(
                        content=f"Неверный статус оплаты: '{status}'. Допустимые значения: {valid_statuses}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Ищем блюдо в чеке
    dish_result = await find_item_by_name(dish_search, receipt_id, db_client)

    if not dish_result.success:
        return Command(
            update={
                "error": dish_result.error_type,
                "messages": [
                    ToolMessage(
                        content=dish_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Ищем пользователя в комнате
    user_result = await find_user_in_room(user_search, room_id, db_client)

    if not user_result.success:
        return Command(
            update={
                "error": user_result.error_type,
                "messages": [
                    ToolMessage(
                        content=user_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Обновляем статус оплаты
    try:
        await db_client.update_assignment_payment_status(
            item_id=dish_result.item_id,
            user_id=user_result.user_id,
            paid=status.lower()
        )

        logger.info(
            f"Payment status for user {user_result.user_id} on item {dish_result.item_id} "
            f"({dish_result.item_name}) updated to: {status}"
        )

        status_ru = {
            "not paid": "не оплачено",
            "on review": "на проверке",
            "paid": "оплачено"
        }

        success_message = (
            f"✓ Статус оплаты для {user_search} на блюде '{dish_result.item_name}' "
            f"изменен на '{status_ru.get(status.lower(), status)}'."
        )

        return Command(
            update={
                "error": None,
                "action_required": True,
                "messages": [
                    ToolMessage(
                        content=success_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error(
            f"Error while updating payment status for user {user_result.user_id} "
            f"on item {dish_result.item_id}",
            exc_info=True
        )

        error_message = f"Ошибка при обновлении статуса оплаты: {str(e)}"

        return Command(
            update={
                "error": "update_failed",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


@tool
async def get_room_participants_list(
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Получает список всех участников текущей комнаты с их username и user_public_name.

    Используется для просмотра кто есть в комнате и может быть назначен на блюда.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    room_id = configurable.get("room_id")

    if not db_client or not room_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    try:
        participants = await db_client.get_room_participants(room_id)
    except Exception as e:
        logger.error(f"Error fetching room participants for room {room_id}", exc_info=True)

        return Command(
            update={
                "error": "fetch_failed",
                "messages": [
                    ToolMessage(
                        content=f"Ошибка при получении участников комнаты: {str(e)}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    if not participants:
        return Command(
            update={
                "error": None,
                "messages": [
                    ToolMessage(
                        content="В комнате нет участников.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    participants_list = []
    for participant in participants:
        display_name = participant.user_public_name or participant.username
        participants_list.append({
            "user_id": participant.user_id,
            "username": participant.username,
            "user_public_name": participant.user_public_name,
            "display_name": display_name,
            "joined_at": participant.joined_at.isoformat() if participant.joined_at else None
        })

    response_message = f"Участники комнаты ({len(participants_list)}):\n"
    for p in participants_list:
        response_message += f"- {p['display_name']} (username: {p['username']}, ID: {p['user_id']})\n"

    logger.info(f"Retrieved {len(participants)} participants from room {room_id}")

    return Command(
        update={
            "error": None,
            "messages": [
                ToolMessage(
                    content=response_message,
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
async def get_user_info(
        user_search: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Получает информацию о конкретном пользователе из комнаты.

    user_search — имя пользователя для поиска

    Возвращает:
    Информацию о пользователе (username, user_public_name) или описание ошибки.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    room_id = configurable.get("room_id")

    if not db_client or not room_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    user_result = await find_user_in_room(user_search, room_id, db_client)

    if not user_result.success:
        return Command(
            update={
                "error": user_result.error_type,
                "messages": [
                    ToolMessage(
                        content=user_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    user_info = (
        f"Информация о пользователе:\n"
        f"- User ID: {user_result.user_id}\n"
        f"- Username: {user_result.username}\n"
        f"- Public name: {user_result.user_public_name or '(не указано)'}\n"
    )

    logger.info(f"Retrieved user info for user {user_result.user_id} (username: {user_result.username})")

    return Command(
        update={
            "error": None,
            "messages": [
                ToolMessage(
                    content=user_info,
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
async def get_dish_assignments(
        dish_search: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Получает список всех пользователей, которым назначено конкретное блюдо.

    dish_search — название блюда (например "утка")

    Возвращает:
    Список пользователей с их статусом оплаты для этого блюда, или сообщение об ошибке.
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    if not db_client or not receipt_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Ищем блюдо в чеке
    dish_result = await find_item_by_name(dish_search, receipt_id, db_client)

    if not dish_result.success:
        return Command(
            update={
                "error": dish_result.error_type,
                "messages": [
                    ToolMessage(
                        content=dish_result.error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Получаем список назначений для блюда
    try:
        assignments = await db_client.get_item_assignments(dish_result.item_id)

        if not assignments:
            response_message = f"На блюдо '{dish_result.item_name}' никто не назначен."
        else:
            response_message = f"Назначения для блюда '{dish_result.item_name}' ({len(assignments)}):\n"
            for assignment in assignments:
                display_name = assignment.user_public_name or assignment.username
                status_ru = {
                    "not paid": "не оплачено",
                    "on review": "на проверке",
                    "paid": "оплачено"
                }
                paid_status = status_ru.get(assignment.paid, assignment.paid)
                response_message += f"- {display_name} (username: {assignment.username}): {paid_status}\n"

        logger.info(f"Retrieved {len(assignments)} assignments for item {dish_result.item_id}")

        return Command(
            update={
                "error": None,
                "messages": [
                    ToolMessage(
                        content=response_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error(
            f"Error while fetching assignments for item {dish_result.item_id}",
            exc_info=True
        )

        error_message = f"Ошибка при получении назначений: {str(e)}"

        return Command(
            update={
                "error": "fetch_failed",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


@tool
async def get_all_dishes_assignments(
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Получает список всех блюд в чеке с назначенными пользователями для каждого блюда.
    
    Это батч-операция, которая вместо множественных параллельных вызовов get_dish_assignments
    получает информацию ВСЕ блюд ОДНИМ вызовом, избегая race conditions.
    
    Возвращает:
    Таблица всех блюд и кто за какое блюдо платит, или сообщение об ошибке.
    """
    
    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")
    
    if not db_client or not receipt_id:
        return Command(
            update={
                "error": "config_error",
                "messages": [
                    ToolMessage(
                        content="Системная ошибка конфигурации.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
    
    try:
        # Получаем все блюда в чеке
        receipt_items = await db_client.get_receipt_items(receipt_id)
        items = receipt_items.items
        
        if not items:
            return Command(
                update={
                    "error": None,
                    "messages": [
                        ToolMessage(
                            content="В чеке нет позиций.",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        
        # Собираем информацию о назначениях для всех блюд
        response_message = "**Кто за что платит:**\n\n"
        
        has_any_assignments = False
        
        for item in items:
            try:
                assignments = await db_client.get_item_assignments(item.id)
                
                if assignments:
                    has_any_assignments = True
                    response_message += f"**{item.name}** ({len(assignments)} назначений):\n"
                    
                    for assignment in assignments:
                        display_name = assignment.user_public_name or assignment.username
                        status_ru = {
                            "not paid": "не оплачено",
                            "on review": "на проверке",
                            "paid": "оплачено"
                        }
                        paid_status = status_ru.get(assignment.paid, assignment.paid)
                        response_message += f"  - {display_name}: {paid_status}\n"
                else:
                    response_message += f"**{item.name}**: не назначено никому\n"
                
                response_message += "\n"
                
            except Exception as e:
                logger.error(
                    f"Error fetching assignments for item {item.id} ({item.name})",
                    exc_info=True
                )
                response_message += f"**{item.name}**: ошибка при получении назначений ({str(e)})\n\n"
        
        if not has_any_assignments:
            response_message = "В чеке нет назначений. Все блюда требуют разбора расчётов."
        
        logger.info(f"Retrieved all assignments for receipt {receipt_id}")
        
        return Command(
            update={
                "error": None,
                "messages": [
                    ToolMessage(
                        content=response_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
        
    except Exception as e:
        logger.error(
            f"Error while fetching all assignments for receipt {receipt_id}",
            exc_info=True
        )
        
        error_message = f"Ошибка при получении назначений: {str(e)}"
        
        return Command(
            update={
                "error": "fetch_failed",
                "messages": [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

