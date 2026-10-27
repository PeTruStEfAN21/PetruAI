from __future__ import annotations

from pathlib import Path

from inventory.errors import DuplicateProduct, InsufficientStock, InvalidOrder, InventoryError, UnknownProduct
from inventory.models import Order, OrderLine, Product
from inventory.pricing import order_total
from inventory.storage import JsonStore


class Shop:
    """Products and orders; every change is written to the JSON file at once."""

    def __init__(self, path: Path | str) -> None:
        self._store = JsonStore(path)
        data = self._store.load()
        self._products = {p["sku"]: Product.from_dict(p) for p in data.get("products", [])}
        self._orders = {o["id"]: Order.from_dict(o) for o in data.get("orders", [])}
        self._next_order = int(data.get("next_order", 1))

    # products

    def add_product(self, sku: str, name: str, *, price_cents: int, quantity: int) -> Product:
        if sku in self._products:
            raise DuplicateProduct(sku)
        if price_cents < 0 or quantity < 0:
            raise InventoryError("price and quantity must not be negative")
        product = Product(sku, name, price_cents, quantity)
        self._products[sku] = product
        self._save()
        return product

    def product(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError:
            raise UnknownProduct(sku) from None

    def products(self) -> list[Product]:
        return [self._products[sku] for sku in sorted(self._products)]

    def restock(self, sku: str, amount: int) -> Product:
        product = self.product(sku)
        if amount <= 0:
            raise InventoryError("restock amount must be positive")
        product.quantity += amount
        self._save()
        return product

    def set_price(self, sku: str, price_cents: int) -> Product:
        product = self.product(sku)
        if price_cents < 0:
            raise InventoryError("price must not be negative")
        product.price_cents = price_cents
        self._save()
        return product

    def remove_product(self, sku: str) -> None:
        self.product(sku)
        del self._products[sku]
        self._save()

    def low_stock(self, threshold: int) -> list[str]:
        return [p.sku for p in self.products() if p.quantity < threshold]

    # orders

    def place_order(self, customer: str, items: dict[str, int]) -> Order:
        if not customer:
            raise InvalidOrder("an order needs a customer")
        if not items:
            raise InvalidOrder("an order needs at least one item")
        lines = []
        for sku, quantity in items.items():
            if quantity <= 0:
                raise InvalidOrder(f"quantity of {sku} must be positive")
            product = self.product(sku)
            if product.quantity < quantity:
                raise InsufficientStock(f"{sku}: {product.quantity} left, {quantity} wanted")
            lines.append(OrderLine(sku, quantity, product.price_cents))
        for line in lines:  # every line checked first, so a failed order reserves nothing
            self._products[line.sku].quantity -= line.quantity
        order = Order(f"O{self._next_order:04d}", customer, lines, order_total(lines))
        self._next_order += 1
        self._orders[order.id] = order
        self._save()
        return order

    def order(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise InvalidOrder(f"no order {order_id}") from None

    def orders(self, customer: str | None = None) -> list[Order]:
        found = [self._orders[oid] for oid in sorted(self._orders)]
        return [o for o in found if customer is None or o.customer == customer]

    def cancel_order(self, order_id: str) -> Order:
        order = self.order(order_id)
        if order.status != "placed":
            raise InvalidOrder(f"{order_id} is already {order.status}")
        for line in order.lines:
            if line.sku in self._products:
                self._products[line.sku].quantity += line.quantity
        order.status = "cancelled"
        self._save()
        return order

    def _save(self) -> None:
        self._store.save(
            {
                "products": [p.to_dict() for p in self.products()],
                "orders": [o.to_dict() for o in self.orders()],
                "next_order": self._next_order,
            }
        )
