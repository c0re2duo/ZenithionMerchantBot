import decimal
import json
import logging
from datetime import datetime
from typing import Any
import html
import re

from aiogram import Dispatcher, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiohttp import web

from callbacks import Cb, is_cb
from config import config
from keyboards.inline import get_inline_kb
from filters import ApiTokenFilter
from states import PaymentCheckState, WithdrawState
from zenithionpay_client import ZenithionPayApiError, get_json, post_json


bot: Bot


_service_unavailable = "Сервис временно недоступен. Попробуйте позже"


def _format_dt_short(value: Any) -> str:
    if not value:
        return "—"
    if not isinstance(value, str):
        return str(value)
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return value


async def get_merchant_info_text(api_key: str, *, refresh: bool) -> str:
    response_data = await get_json(
        "merchant/info",
        {"X-API-Key": api_key},
        timeout=5,
        cache_ttl=100,
        refresh=refresh,
    )

    return (
        f"💵 Баланс: <b>{float(response_data.get('balance', '0')):.4f} USDT</b>\n\n"
        f"📅 Оплаченные платежи за сегодня: <b>{response_data.get('paid_payments_today', 'Будет доступно позже.')}</b>\n"
        f"✅ Оплаченные платежи за все время: <b>{response_data.get('paid_payments_total', '<b>Будет доступно позже.')}</b>"
    )


_TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")

_STATUS_RU: dict[str, str] = {
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "underpaid": "Недооплачен",
    "expired": "Просрочен",
    "closed": "Закрыт",
    "error": "Ошибка",
}


def _status_ru(status: Any) -> str:
    if not status:
        return "Неизвестно"
    s = str(status).lower()
    return _STATUS_RU.get(s, s)


def _format_payment_block(p: dict[str, Any]) -> str:
    payment_id = p.get("id", "—")
    tron_address = p.get("tron_address", "—")
    status = _status_ru(p.get("status"))
    created = _format_dt_short(p.get("created_at"))
    expires = _format_dt_short(p.get("expires_at"))

    amount = p.get("amount", "-")
    amount_to_pay = p.get("amount_to_pay", "-")
    amount_paid = p.get("amount_paid", "-")

    lines = [
        f"<i>ID</i>: <code>{payment_id}</code>",
        f"<i>Статус</i>: <b>{status}</b>",
        f"<i>Адрес</i>: <code>{tron_address}</code>",
        f"<i>Создан</i>: <b>{created}</b>  •  До: <b>{expires}</b>",
        f"Сумма: <b>{amount}</b>  •  <i>К оплате</i>: <b>{amount_to_pay}</b>  •  <i>Оплачено</i>: <b>{amount_paid}</b>",
    ]
    return "\n".join(lines)


def _format_payment_details(p: dict[str, Any]) -> str:
    if p.get("status") == 'closed':
        return 'Платеж <b>закрыт</b>'

    payment_id = p.get("id", "—")
    tron_address = p.get("tron_address", "—")
    status = _status_ru(p.get("status"))

    created = _format_dt_short(p.get("created_at"))
    expires = _format_dt_short(p.get("expires_at"))

    amount = p.get("amount", None)
    amount_to_pay = p.get("amount_to_pay", None)
    amount_paid = p.get("amount_paid", None)

    metadata = p.get("metadata", None)
    if isinstance(metadata, dict) and metadata:
        metadata_text = ", ".join(f"{k}={v}" for k, v in metadata.items())
    elif metadata is None:
        metadata_text = "—"
    else:
        metadata_text = str(metadata)

    deposits = p.get("deposits", None)
    deposits_lines: list[str] = []
    if isinstance(deposits, list) and deposits:
        for d in deposits:
            if not isinstance(d, dict):
                continue
            d_id = d.get("id", "—")
            d_created = _format_dt_short(d.get("created_at"))
            d_amount = d.get("amount", "—")
            d_address = d.get("address", "—")
            d_txid = d.get("txid", "—")
            deposits_lines.append(
                "• "
                f"<i>ID</i>: <code>{html.escape(str(d_id))}</code>  •  "
                f"  ⏱️: <b>{html.escape(str(d_created))}</b>\n"
                f"  💵: <b>{html.escape(str(d_amount))} USDT</b>\n"
                f"  <i>TXID</i>: <code>{html.escape(str(d_txid))}</code>"
            )
    deposits_text = "\n".join(deposits_lines) if deposits_lines else "—"

    sum_for_paying_line = f"<i>Сумма</i>: <b>{amount}</b>\n" if amount is not None else ""
    amount_to_pay_line = f"<i>К оплате</i>: <b>{amount_to_pay}</b>" if amount_to_pay is not None else ""
    paid_line = f"<i>Оплачено</i>: <b>{amount_paid}</b>" if amount_paid is not None else ""

    return (
        "<b>Платёж</b>\n"
        f"<i>ID</i>: <code>{payment_id}</code>\n"
        f"<i>Статус</i>: <b>{status}</b>\n"
        f"<i>Адрес</i>: <code>{tron_address}</code>\n"
        f"⏱️ <i>Создан</i>: <b>{created}</b>\n"
        f"⌛️ <i>Истекает</i>: <b>{expires}</b>\n"
        f"{sum_for_paying_line}"
        f"{amount_to_pay_line}"
        f"{paid_line}\n"
        f"<i>Метаданные</i>: <code>{metadata_text}</code>\n\n"
        f"📥 <b>Депозиты ({len(deposits)})</b>\n"
        f"{deposits_text}"
    )


async def start_handler(message: Message, api_key: str) -> None:
    try:
        text = await get_merchant_info_text(api_key, refresh=False)
    except ZenithionPayApiError as e:
        if e.status >= 500:
            await message.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        else:
            await message.answer(f"Ошибка запроса", reply_markup=get_inline_kb("user_menu"))
        return
    except Exception:
        await message.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        return

    await message.answer(text, reply_markup=get_inline_kb("user_menu"))


async def delete_message_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.delete()


async def cancel_callback(callback: CallbackQuery, state: FSMContext, api_key) -> None:
    await state.clear()
    # if callback.message:
    #     await callback.message.delete()
    try:
        text = await get_merchant_info_text(api_key, refresh=False)
    except ZenithionPayApiError as e:
        if e.status >= 500:
            await callback.message.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        else:
            await callback.message.answer(f"Ошибка запроса", reply_markup=get_inline_kb("user_menu"))
        return
    except Exception:
        await callback.message.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        return

    await callback.message.answer(text, reply_markup=get_inline_kb("user_menu"))
    await callback.message.delete()


async def info_callback(callback: CallbackQuery, api_key: str) -> None:
    try:
        text = await get_merchant_info_text(api_key, refresh=True)
    except ZenithionPayApiError as e:
        if e.status >= 500:
            await callback.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        else:
            await callback.answer(f"Ошибка запроса", reply_markup=get_inline_kb("user_menu"))
        return
    except Exception:
        await callback.answer(_service_unavailable, reply_markup=get_inline_kb("user_menu"))
        return

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_inline_kb("user_menu")
        )
    except TelegramBadRequest:
        pass
    await callback.answer('Данные обновлены.')


async def payments_history_callback(callback: CallbackQuery, api_key: str) -> None:
    await callback.answer()

    try:
        response_data = await get_json(
            "payments/history",
            {"X-API-Key": api_key},
            params={'limit': 10, 'with_closed': False},
            cache_ttl=10
        )
    except ZenithionPayApiError as e:
        if e.status >= 500:
            await callback.message.answer(_service_unavailable)
            return
        await callback.message.answer(f"Ошибка запроса: {e.status}\nОтвет:\n{e.payload}")
        return
    except Exception:
        await callback.message.answer(_service_unavailable)
        return

    payments = response_data.get("payments") if isinstance(response_data, dict) else None
    if not isinstance(payments, list) or not payments:
        await callback.message.answer("Платежи не найдены.")
        return

    blocks: list[str] = []
    for item in payments:
        if isinstance(item, dict):
            blocks.append(_format_payment_block(item))

    text = f"Последние {response_data.get('count', '?')} платежей (Без закрытых):\n\n"
    block_text = "\n\n".join(blocks) if blocks else "Платежи не найдены."
    text += block_text
    await callback.message.answer(f"{text}", reply_markup=get_inline_kb("cansel"))
    await callback.message.delete()


async def check_payment_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PaymentCheckState.waiting_for_payment_id_or_address)
    await callback.message.answer(
        "Отправь <b>ID платежа</b> или <b>TRON-адрес</b>.\n"
        "Пример: <code>7747b8f0-6970-4f38-bcfd-95e6560e49db</code>",
        reply_markup=get_inline_kb("cansel"),
    )
    await callback.message.delete()


async def check_payment_input(message: Message, state: FSMContext, api_key: str) -> None:
    await message.delete()

    value = (message.text or "").strip()
    if not value:
        await message.answer("Пришли ID или адрес одним сообщением.", reply_markup=get_inline_kb("delete_message"))
        return

    try:
        payload = await get_json(
            f"payments/{value}",
            {"X-API-Key": api_key},
            cache_ttl=10
        )
    except ZenithionPayApiError as e:
        if e.status == 404:
            await message.answer(f"Платеж <b>{value}</b> не найден. Попробуйте еще раз.",
                                 reply_markup=get_inline_kb("cansel"))
        else:
            await message.answer(_service_unavailable, reply_markup=get_inline_kb("cansel"))
            await state.clear()
        return
    except Exception:
        await message.answer(_service_unavailable, reply_markup=get_inline_kb("cansel"))
        await state.clear()
        return

    text = _format_payment_details(payload) if isinstance(payload, dict) else str(payload)
    await message.answer(text, reply_markup=get_inline_kb("delete_message"))
    await state.clear()


async def withdraw_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(WithdrawState.waiting_for_to_address)
    await callback.message.answer(
        "Введите <b>адрес на который совершится вывод</b> USDT TRC-20 (TRON-адрес).",
        reply_markup=get_inline_kb("cansel"),
    )
    await callback.message.delete()


async def withdraw_input(message: Message, state: FSMContext, api_key: str) -> None:
    to_address = (message.text or "").strip()

    if not _TRON_ADDRESS_RE.fullmatch(to_address):
        await message.answer(
            "Неправильный адрес TRON.\n"
            "Пример формата: <b>TKTgEtjonYPdCWDs7bUb9dUUwYikceDabx</b>\n"
            "Отправь адрес ещё раз.",
            reply_markup=get_inline_kb("cansel"),
        )
        return

    try:
        payload = await post_json(
            "merchant/balance/withdraw",
            {"X-API-Key": api_key},
            json_body={"to_address": to_address},
        )
    except ZenithionPayApiError as e:
        if e.status >= 500:
            await message.answer(_service_unavailable, reply_markup=get_inline_kb("cansel"))
        else:
            await message.answer(f"Ошибка запроса: {e.status}\nОтвет:\n{e.payload}",
                                 reply_markup=get_inline_kb("cansel"))
        await state.clear()
        return
    except Exception:
        await message.answer(_service_unavailable, reply_markup=get_inline_kb("cansel"))
        await state.clear()
        return

    withdraw_fail_text = f"❌ Не удалось выполнить вывод. Обратитесь в техподдержку."

    if isinstance(payload, dict):
        success = payload.get("success") is True
        if success:
            await message.answer(f"✅ Вывод успешно создан. Ожидайте пополнение на {to_address} <b>(не дольше часа)</b>.", reply_markup=get_inline_kb("delete_message"))
        else:
            status = payload.get("status")
            if status == 'under_minimum_withdrawal_amount':
                await message.answer('❕ Сумма к выводу меньше допустимого минимума. Совершайте вывод когда сумма будет превышать порог.', reply_markup=get_inline_kb("delete_message"))
            else:
                await message.answer(withdraw_fail_text, reply_markup=get_inline_kb("delete_message"))
    else:
        await message.answer(withdraw_fail_text, reply_markup=get_inline_kb("delete_message"))

    await state.clear()
    await message.delete()


async def new_deposit_notify(address: str, amount: decimal.Decimal, new_status: str, merchant_api_token: str) -> None:
    admins_ids = config.api_tokens.get(merchant_api_token, [])

    if not admins_ids:
        logging.warning(f"Merchant API token not found: {merchant_api_token}")
        return

    text = f'''
💸 Новый депозит.

Адрес: <code><b>{address}</b></code>
Сумма: <b><i>{amount}</i></b>

Статус платежа: {_status_ru(new_status)}
'''

    for admin_id in admins_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramBadRequest as e:
            logging.warning(f"Failed to send message to admin: {e}",)
    logging.info(f"New deposit notifications sent.")


def register_handlers(dp: Dispatcher, actual_bot: Bot) -> None:
    global bot
    bot = actual_bot

    dp.message.register(
        start_handler,
        CommandStart(),
        ApiTokenFilter(),
    )
    dp.callback_query.register(
        delete_message_callback,
        lambda c: is_cb(c.data, Cb.DELETE_MESSAGE),
    )
    dp.callback_query.register(
        cancel_callback,
        lambda c: is_cb(c.data, Cb.BACK_TO_USER_MENU),
        ApiTokenFilter(),
    )
    dp.callback_query.register(
        info_callback,
        lambda c: is_cb(c.data, Cb.BALANCE),
        ApiTokenFilter(),
    )
    dp.callback_query.register(
        payments_history_callback,
        lambda c: is_cb(c.data, Cb.PAYMENTS_LAST),
        ApiTokenFilter(),
    )
    dp.callback_query.register(
        withdraw_callback,
        lambda c: is_cb(c.data, Cb.WITHDRAW),
        ApiTokenFilter(),
    )
    dp.callback_query.register(
        check_payment_callback,
        lambda c: is_cb(c.data, Cb.CHECK_PAYMENT),
        ApiTokenFilter(),
    )
    dp.message.register(
        withdraw_input,
        WithdrawState.waiting_for_to_address,
        ApiTokenFilter(),
    )
    dp.message.register(
        check_payment_input,
        PaymentCheckState.waiting_for_payment_id_or_address,
        ApiTokenFilter(),
    )
