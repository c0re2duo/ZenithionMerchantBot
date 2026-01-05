from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import config


class ApiTokenFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool | dict[str, Any]:
        from_user = getattr(event, "from_user", None)
        user_id = str(from_user.id) if from_user else None

        api_key = config.get_api_token(user_id) if user_id else None

        if not api_key:
            text = "Для вашего аккаунта не найден API токен."
            if isinstance(event, Message):
                await event.answer(text)
            else:
                # CallbackQuery
                if event.message:
                    await event.message.answer(text)
                else:
                    # in case of inline callbacks without message
                    await event.answer(text, show_alert=True)
            return False

        return {"api_key": api_key}
