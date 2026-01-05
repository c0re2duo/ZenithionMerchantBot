from __future__ import annotations

from typing import List, Tuple


class Cb:
    BALANCE = "balance"
    PAYMENTS_LAST = "payments_last"
    PAYMENTS_TODAY = "payments_today"
    WITHDRAW = "withdraw"
    CHECK_PAYMENT = "check_payment"
    DELETE_MESSAGE = "delete_message"
    CANCEL = "cancel"


def pack(name: str, *args: str) -> str:
    return ":".join([name, *args])


def unpack(data: str) -> Tuple[str, List[str]]:
    parts = (data or "").split(":")
    return parts[0], parts[1:]


def is_cb(data: str | None, name: str) -> bool:
    return (data or "") == name


def is_cb_prefix(data: str | None, name: str) -> bool:
    # true for "payments_page:last:3"
    return (data or "").startswith(f"{name}:")