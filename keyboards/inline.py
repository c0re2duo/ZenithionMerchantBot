# keyboards/inline.py
from __future__ import annotations

from typing import Any, Callable, Dict, Union

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks import Cb


def start_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить баланс", callback_data=Cb.BALANCE)],
            [InlineKeyboardButton(text="Последние платежи", callback_data=Cb.PAYMENTS_LAST)],
            # [InlineKeyboardButton(text="Платежи за сегодня", callback_data=Cb.PAYMENTS_TODAY)],
            [InlineKeyboardButton(text="Поиск платежа", callback_data=Cb.CHECK_PAYMENT)],
            [InlineKeyboardButton(text="Вывести", callback_data=Cb.WITHDRAW)],
        ]
    )


def delete_message_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Скрыть", callback_data=Cb.DELETE_MESSAGE)],
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data=Cb.CANCEL)],
        ]
    )


InlineKbFactory = Callable[..., InlineKeyboardMarkup]
InlineKbEntry = Union[InlineKeyboardMarkup, InlineKbFactory]

INLINE_KEYBOARDS: Dict[str, InlineKbEntry] = {
    "start_menu": start_menu_kb,
    "delete_message": delete_message_kb,
    "cansel": cancel_kb,
}


def get_inline_kb(name: str, **kwargs: Any) -> InlineKeyboardMarkup:
    entry = INLINE_KEYBOARDS[name]
    if callable(entry):
        return entry(**kwargs)
    return entry