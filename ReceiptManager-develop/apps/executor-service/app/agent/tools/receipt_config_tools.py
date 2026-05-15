from app.core.config import get_settings
from app.core.logger import get_logger
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from app.agent.schemas import ReceiptItemBatchCreateSchema, ReceiptItemUpdateSchema, ReceiptItemOutSchema, AgentReceiptState, ReceiptUpdateSchema
from app.schemas.receipt_item import ReceiptItemUpdate
from rapidfuzz import fuzz
from dataclasses import dataclass


from langgraph.types import Command

import httpx

logger = get_logger(__name__)


@tool
async def add_items(
        receipt_items_object: ReceiptItemBatchCreateSchema,
        runtime: ToolRuntime[None, AgentReceiptState]
) -> Command:
    """
    Добавляет новые позиции в чек.

    receipt_items_object: список позиций для добавления в чек

    Возвращает:
    Словарь с полем items - список добавленных позиций в виде словарей,
    либо строка с сообщением об ошибке/отсутствии данных
    и командой для последующего выполнения.
    """

    config = runtime.config

    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")

    receipt_id = configurable.get("receipt_id")

    if not db_client:
        logger.error("Error: unable to connect to DB: db_client not found in config configurable.")

        error = "unable to connect to DB: db_client not found in config configurable"
        error_message = "Системная ошибка: нет подключения к БД. Сообщи пользователю об ошибке."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                    content=error_message,
                    tool_call_id=runtime.tool_call_id),
                ]
            }
        )

    if not receipt_id:
        logger.error("Error: unable add items: receipt_id not found in config metadata.")

        error = "unable add items: receipt_id not found in config metadata"
        error_message = "Ошибка: отсутствует ID чека. Убедись, что чек был создан до добавления позиций."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                    content=error_message,
                    tool_call_id=runtime.tool_call_id),
                ]
            }
        )

    try:

        payload_for_db = [item.to_db_model() for item in receipt_items_object.items] # float to Decimal

        response = await db_client.add_items(receipt_id=receipt_id, payload=payload_for_db)

    except httpx.HTTPStatusError as e:

        status_code = e.response.status_code if e.response else "Unknown"
        error_details = e.response.text if e.response else str(e)
        logger.error(f"HTTP {status_code}: failed to add items to receipt {receipt_id}", exc_info=True)

        error = f"HTTP {status_code}"
        error_message = f"""
            Ошибка API при добавлении позиций в чек.
            Код ответа: {status_code}.
            Детали: {error_details}.
            Исправь данные и попробуй снова."""

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                    content=error_message,
                    tool_call_id=runtime.tool_call_id),
                ]
            }
        )

    except Exception as e:

        logger.error(f"Unexpected error while adding items to receipt {receipt_id}", exc_info=True)

        error = "unexpected error"
        error_message = f"Произошла непредвиденная ошибка при добавлении позиций: {str(e)}."

        return Command(
            update={
                "error": error,
                "messages": [
                    ToolMessage(
                    content=error_message,
                    tool_call_id=runtime.tool_call_id),
                ]
            }
        )

    if item_count := len(response.items):

        logger.info(f"Operation successful: {item_count} items were added to receipt with id {receipt_id}")

        response_message = response.model_dump()

        return Command(
            update={
                "error": None,
                "action_required": True,
                "messages": [
                    ToolMessage(
                    content=response_message,
                    tool_call_id=runtime.tool_call_id),
                ]
            }
        )

    logger.warning(f"Error: empty payload for receipt {receipt_id}")

    return Command(
        update={
            "error": "no items were added",
            "messages": [ToolMessage(
                content="Ошибка. Не было добавлено ни одной позиции. Проверь переданные данные",
                tool_call_id=runtime.tool_call_id),
            ]
        }
    )


@tool
async def get_receipt_items(
    runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
        Получает информацию о всех позициях в текущем чеке.

        Используется для получения актуальной информации
        о всех позициях в текущем чеке, включая актуальные номера позиций.
    """
    config = runtime.config

    configurable = config.get("configurable", {})

    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    print("STATE:", runtime.state)
    print("CONFIG:", runtime.config)

    if not db_client:
        return Command(update={
            "error": "no_db_connection",
            "messages": [
                ToolMessage(
                    content="Системная ошибка: нет подключения к БД.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    if not receipt_id:
        return Command(update={
            "error": "no_receipt_id",
            "messages": [
                ToolMessage(
                    content="Ошибка: отсутствует ID чека.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    try:
        response = await db_client.get_receipt_items(receipt_id)

    except httpx.HTTPStatusError as e:
        return Command(update={
            "error": f"http_{e.response.status_code if e.response else 'unknown'}",
            "messages": [
                ToolMessage(
                    content="Ошибка API при получении позиций чека.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    except Exception as e:
        return Command(update={
            "error": "unexpected_error",
            "messages": [
                ToolMessage(
                    content=f"Непредвиденная ошибка: {str(e)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    if not response.items:
        return Command(update={
            "error": None,
            "messages": [
                ToolMessage(
                    content="В чеке отсутствуют позиции.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    id_map = {}
    items_data = []

    for i, item in enumerate(response.items, start=1):
        id_map[i] = item.id
        item_dict = item.model_dump()
        item_dict["id"] = i
        items_data.append(item_dict)

    return Command(update={
        "error": None,
        "messages": [
            ToolMessage(
                content=str({"items": items_data}),
                tool_call_id=runtime.tool_call_id,
            )
        ],
    })

@tool
async def get_item(
    item_display_id: int,
    runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
        Получает информацию о позиции в текущем чеке по ее номеру.

        Используется для проверки соответствия позиции и ее отображаемого id.
        Если необходимо удалить или изменить объект, то необходимо проверить
        соответствует ли id объекта самому объекту.
        При несоответствии необходимо вызывать get_receipt_items и после повторить попытку.

        Используй только если ранее вызывал get_receipt_items.

        item_display_id — это отображаемый ID (номер в списке),
        а не реальный ID из базы данных.
    """

    config = runtime.config

    configurable = config.get("configurable", {})

    db_client = configurable.get("db_client")

    id_map = runtime.state.get("id_map", {})

    if not db_client:
        return Command(update={
            "error": "no_db_connection",
            "messages": [
                ToolMessage(
                    content="Системная ошибка: нет подключения к БД.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    item_real_id = id_map.get(item_display_id)
    if not item_real_id:
        return Command(update={
            "error": "invalid_display_id",
            "messages": [
                ToolMessage(
                    content="Сначала получи список позиций через get_receipt_items.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    try:
        response = await db_client.get_item(item_real_id)

    except Exception as e:
        return Command(update={
            "error": "get_item_failed",
            "messages": [
                ToolMessage(
                    content=f"Ошибка при получении позиции: {str(e)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    result = response.model_dump()
    result["id"] = item_display_id

    return Command(update={
        "error": None,
        "messages": [
            ToolMessage(
                content=str(result),
                tool_call_id=runtime.tool_call_id,
            )
        ],
    })


@dataclass
class ItemSearchResult:
    """Результат поиска элемента"""
    success: bool
    item_id: int | None = None
    item_name: str | None = None
    error_type: str | None = None
    error_message: str | None = None


async def find_item_by_name(
        search_query: str,
        receipt_id: int,
        db_client,
) -> ItemSearchResult:
    """
    Ищет элемент чека по названию с использованием Fuzz поиска.

    Args:
        search_query: Поисковый запрос (название позиции)
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
            error_message=f"Ошибка получения позиций: {str(e)}"
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
            error_message=f"Позиция '{search_query}' не найдена. Уточни название."
        )

    if len(matches) > 1 and matches[0][0] - matches[1][0] < 10:
        options = [m[1].name for m in matches[:3]]
        return ItemSearchResult(
            success=False,
            error_type="ambiguous",
            error_message=f"Найдено несколько похожих позиций: {options}. Уточни, какую изменить."
        )

    target = matches[0][1]

    return ItemSearchResult(
        success=True,
        item_id=target.id,
        item_name=target.name
    )


@tool
async def update_item(
        search_query: str,
        item_info: ReceiptItemUpdateSchema,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Обновляет позицию в текущем чеке по названию.

    search_query — как пользователь называет позицию

    item_info — объект с полями для обновления:
    - name: новое название
    - price: новая цена
    - quantity: новое количество
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    if not db_client or not receipt_id:
        return Command(update={
            "error": "config_error",
            "messages": [
                ToolMessage(
                    content="Системная ошибка конфигурации.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    search_result = await find_item_by_name(search_query, receipt_id, db_client)

    if not search_result.success:
        return Command(update={
            "error": search_result.error_type,
            "messages": [
                ToolMessage(
                    content=search_result.error_message,
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    try:
        updated = await db_client.update_item(
            search_result.item_id,
            item_info.to_db_update()
        )
    except Exception as e:
        return Command(update={
            "error": "update_failed",
            "messages": [
                ToolMessage(
                    content=f"Ошибка при обновлении: {str(e)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    return Command(update={
        "error": None,
        "action_required": True,
        "messages": [
            ToolMessage(
                content=f"Позиция '{updated.name}' успешно обновлена.",
                tool_call_id=runtime.tool_call_id,
            )
        ],
    })


@tool
async def delete_item(
        search_query: str,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """Удаляет позицию из чека по названию."""

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    if not db_client or not receipt_id:
        return Command(update={
            "error": "config_error",
            "messages": [ToolMessage(
                content="Системная ошибка конфигурации.",
                tool_call_id=runtime.tool_call_id,
            )],
        })

    search_result = await find_item_by_name(search_query, receipt_id, db_client)

    if not search_result.success:
        return Command(update={
            "error": search_result.error_type,
            "messages": [ToolMessage(
                content=search_result.error_message,
                tool_call_id=runtime.tool_call_id,
            )],
        })

    try:
        await db_client.delete_item(search_result.item_id)
    except Exception as e:
        return Command(update={
            "error": "delete_failed",
            "messages": [ToolMessage(
                content=f"Ошибка при удалении: {str(e)}",
                tool_call_id=runtime.tool_call_id,
            )],
        })

    return Command(update={
        "error": None,
        "action_required": True,
        "messages": [ToolMessage(
            content=f"Позиция '{search_result.item_name}' успешно удалена.",
            tool_call_id=runtime.tool_call_id,
        )],
    })


@tool
async def update_receipt(
        receipt_info: ReceiptUpdateSchema,
        runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Обновляет информацию о текущем чеке.

    receipt_info — объект с полями для обновления:
    - paid_at: дата оплаты (формат YYYY-MM-DD или YYYY-MM-DD HH:MM:SS)
    - place_name: название заведения
    """

    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    if not db_client or not receipt_id:
        return Command(update={
            "error": "config_error",
            "messages": [ToolMessage(
                content="Системная ошибка конфигурации.",
                tool_call_id=runtime.tool_call_id,
            )],
        })

    try:
        db_update = receipt_info.to_db_update()
        await db_client.update_receipt(receipt_id, db_update)
    except ValueError as e:
        return Command(update={
            "error": "validation_error",
            "messages": [ToolMessage(
                content=str(e),
                tool_call_id=runtime.tool_call_id,
            )],
        })
    except Exception as e:
        return Command(update={
            "error": "update_failed",
            "messages": [ToolMessage(
                content=f"Ошибка при обновлении информации о чеке: {str(e)}",
                tool_call_id=runtime.tool_call_id,
            )],
        })

    return Command(update={
        "error": None,
        "action_required": True,
        "messages": [ToolMessage(
            content="Информация о чеке успешно обновлена.",
            tool_call_id=runtime.tool_call_id,
        )],
    })


@tool
async def get_receipt_info(
    runtime: ToolRuntime[None, AgentReceiptState],
) -> Command:
    """
    Получает информацию о текущем чеке: дата оплаты и название места.
    
    Используется для получения актуальной информации о дате оплаты (paid_at)
    и названии заведения (place_name).
    """
    
    config = runtime.config
    configurable = config.get("configurable", {})
    db_client = configurable.get("db_client")
    receipt_id = configurable.get("receipt_id")

    if not db_client:
        return Command(update={
            "error": "no_db_connection",
            "messages": [
                ToolMessage(
                    content="Системная ошибка: нет подключения к БД.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    if not receipt_id:
        return Command(update={
            "error": "no_receipt_id",
            "messages": [
                ToolMessage(
                    content="Ошибка: отсутствует ID чека.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    try:
        response = await db_client.get_receipt(receipt_id)

    except httpx.HTTPStatusError as e:
        return Command(update={
            "error": f"http_{e.response.status_code if e.response else 'unknown'}",
            "messages": [
                ToolMessage(
                    content="Ошибка API при получении информации о чеке.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    except Exception as e:
        return Command(update={
            "error": "unexpected_error",
            "messages": [
                ToolMessage(
                    content=f"Непредвиденная ошибка: {str(e)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    if not response:
        return Command(update={
            "error": "receipt_not_found",
            "messages": [
                ToolMessage(
                    content="Чек не найден в базе данных.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        })

    receipt_info = {
        "paid_at": response.paid_at.isoformat() if response.paid_at else None,
        "place_name": response.place_name,
    }

    return Command(update={
        "error": None,
        "messages": [
            ToolMessage(
                content=str(receipt_info),
                tool_call_id=runtime.tool_call_id,
            )
        ],
    })


# @tool
# async def delete_item(???, config: RunnableConfig) -> str:
#     ...



# @tool
# async def update_receipt_info(config: RunnableConfig):

# print(addItems.args_schema.schema())
