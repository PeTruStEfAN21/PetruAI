from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Product:
    sku: str
    name: str
    price_cents: int
    quantity: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Product:
        return cls(data["sku"], data["name"], int(data["price_cents"]), int(data["quantity"]))


@dataclass(frozen=True)
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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Order:
        lines = [OrderLine(**line) for line in data["lines"]]
        return cls(data["id"], data["customer"], lines, int(data["total_cents"]), data["status"])
