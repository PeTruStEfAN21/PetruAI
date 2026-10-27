"""Order totals: 5% off a line of 10 or more units, then 10% off a subtotal of 100.00 or more."""

from __future__ import annotations

from collections.abc import Iterable

from inventory.models import OrderLine

BULK_QUANTITY = 10
BULK_PERCENT_OFF = 5
LARGE_SUBTOTAL_CENTS = 10_000
LARGE_PERCENT_OFF = 10


def line_total(line: OrderLine) -> int:
    total = line.quantity * line.unit_price_cents
    if line.quantity >= BULK_QUANTITY:
        total = total * (100 - BULK_PERCENT_OFF) // 100
    return total


def order_total(lines: Iterable[OrderLine]) -> int:
    subtotal = sum(line_total(line) for line in lines)
    if subtotal >= LARGE_SUBTOTAL_CENTS:
        subtotal = subtotal * (100 - LARGE_PERCENT_OFF) // 100
    return subtotal
