from typing import Callable
from functools import lru_cache
from app.agent.tools.receipt_config_tools import (add_items,
                                                  get_receipt_items,
                                                  get_item,
                                                  update_item,
                                                  delete_item,
                                                  update_receipt,
                                                  get_receipt_info
                                                  )


from app.agent.tools.room_config_tools import (assign_user_to_dish,
                                               unassign_user_from_dish,
                                               update_payment_status,
                                               get_room_participants_list,
                                               get_user_info,
                                               get_dish_assignments,
                                               get_all_dishes_assignments
                                               )


_all_tools: list[Callable] | None = None
_receipt_tools: list[Callable] | None = None
_room_tools: list[Callable] | None = None


@lru_cache(maxsize=1)
def build_tools_list() -> list:
    """Создаёт список из callable tools (singleton)"""
    return [add_items,]

@lru_cache(maxsize=1)
def build_receipt_tools_list() -> list:
    """Создаёт список из callable receipt tools (singleton)"""
    return [add_items,
            get_receipt_items,
            get_item,
            update_item,
            delete_item,
            update_receipt,
            get_receipt_info
            ]


@lru_cache(maxsize=1)
def build_room_tools_list() -> list:
    """Создаёт список из callable receipt tools (singleton)"""
    return [assign_user_to_dish,
            unassign_user_from_dish,
            update_payment_status,
            get_room_participants_list,
            get_user_info,
            get_dish_assignments,
            get_all_dishes_assignments,
            get_receipt_items # из receipt tools
            ]



def get_all_tools() -> list:
    """
    Возвращает singleton инстанс список tools для агента

    Returns:
        Готовый к использованию список tools
    """
    global _all_tools

    if _all_tools is None:
        _all_tools = build_tools_list()

    return _all_tools



def get_receipt_tools() -> list:
    """
    Возвращает singleton инстанс список receipt tools для агента

    Returns:
        Готовый к использованию список receipt tools
    """
    global _receipt_tools

    if _receipt_tools is None:
        _receipt_tools = build_receipt_tools_list()

    return _receipt_tools



def get_room_tools() -> list:
    """
    Возвращает singleton инстанс список room tools для агента

    Returns:
        Готовый к использованию список room tools
    """
    global _room_tools

    if _room_tools is None:
        _room_tools = build_room_tools_list()

    return _room_tools


