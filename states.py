from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PaymentCheckState(StatesGroup):
    waiting_for_payment_id_or_address = State()


class WithdrawState(StatesGroup):
    waiting_for_to_address = State()