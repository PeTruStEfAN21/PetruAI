from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Product:
    sku: str
    name: str
    price_cents: int
    quantity: int


@dataclass
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass
class Order:
    id: str
    customer: str
    lines: list[OrderLine] = field(default_factory=list)
    total_cents: int = 0
    status: str = "placed"
