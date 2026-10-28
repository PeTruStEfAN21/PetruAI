"""Shop class for inventory management."""

from pathlib import Path
from inventory.models import Order, OrderLine, Product
from inventory.storage import Storage
from inventory.errors import (
    InventoryError,
    UnknownProduct,
    DuplicateProduct,
    InsufficientStock,
    InvalidOrder,
)
from inventory.pricing import compute_order_total, compute_line_total


class Shop:
    """Shop class for managing inventory and orders."""

    def __init__(self, path: str | Path) -> None:
        """Initialize the shop with a storage instance at the given path."""
        self._storage = Storage(Path(path))

    def add_product(self, sku: str, name: str, *, price_cents: int, quantity: int) -> None:
        """Add a new product to inventory.
        
        Raises:
            InventoryError: if price_cents < 0 or quantity < 0, or if sku already exists.
        """
        if price_cents < 0:
            raise InventoryError("Price cannot be negative")
        if quantity < 0:
            raise InventoryError("Quantity cannot be negative")
        if sku in self._storage.products:
            raise DuplicateProduct(f"Product with SKU {sku} already exists")
        
        self._storage.products[sku] = {
            "sku": sku,
            "name": name,
            "price_cents": price_cents,
            "quantity": quantity,
        }
        self._storage.save()

    def product(self, sku: str) -> Product:
        """Get a product by SKU.
        
        Raises:
            UnknownProduct: if sku not found.
        """
        product_data = self._storage.products.get(sku)
        if product_data is None:
            raise UnknownProduct(f"Product with SKU {sku} not found")
        return Product(
            sku=product_data["sku"],
            name=product_data["name"],
            price_cents=product_data["price_cents"],
            quantity=product_data["quantity"],
        )

    def products(self) -> list[Product]:
        """Get all products sorted by SKU."""
        products = []
        for sku in sorted(self._storage.products.keys()):
            product_data = self._storage.products[sku]
            products.append(Product(
                sku=product_data["sku"],
                name=product_data["name"],
                price_cents=product_data["price_cents"],
                quantity=product_data["quantity"],
            ))
        return products

    def restock(self, sku: str, amount: int) -> None:
        """Restock a product.
        
        Raises:
            UnknownProduct: if sku not found.
            InventoryError: if amount <= 0.
        """
        if amount <= 0:
            raise InventoryError("Restock amount must be positive")
        if sku not in self._storage.products:
            raise UnknownProduct(f"Product with SKU {sku} not found")
        
        self._storage.products[sku]["quantity"] += amount
        self._storage.save()

    def set_price(self, sku: str, price_cents: int) -> None:
        """Set the price of a product.
        
        Raises:
            UnknownProduct: if sku not found.
        """
        if sku not in self._storage.products:
            raise UnknownProduct(f"Product with SKU {sku} not found")
        
        self._storage.products[sku]["price_cents"] = price_cents
        self._storage.save()

    def remove_product(self, sku: str) -> None:
        """Remove a product from inventory.
        
        Raises:
            UnknownProduct: if sku not found.
        """
        if sku not in self._storage.products:
            raise UnknownProduct(f"Product with SKU {sku} not found")
        
        del self._storage.products[sku]
        self._storage.save()

    def low_stock(self, threshold: int) -> list[str]:
        """Get list of SKUs with quantity below threshold, sorted.
        
        Returns:
            List of SKUs where quantity < threshold.
        """
        result = []
        for sku, product_data in self._storage.products.items():
            if product_data["quantity"] < threshold:
                result.append(sku)
        return sorted(result)

    def place_order(self, customer: str, items: dict[str, int]) -> Order:
        """Place an order.
        
        Args:
            customer: Customer name.
            items: Dict mapping SKU to quantity.
            
        Returns:
            Order object.
            
        Raises:
            InvalidOrder: if customer is empty, items is empty, or any quantity <= 0.
            UnknownProduct: if any SKU not found.
            InsufficientStock: if any SKU has insufficient stock.
        """
        # Validation
        if not customer:
            raise InvalidOrder("Customer cannot be empty")
        if not items:
            raise InvalidOrder("Order items cannot be empty")
        for qty in items.values():
            if qty <= 0:
                raise InvalidOrder("Quantity must be positive")
        
        # Check all products exist
        for sku in items.keys():
            if sku not in self._storage.products:
                raise UnknownProduct(f"Product with SKU {sku} not found")
        
        # Check stock and build order lines
        lines: list[OrderLine] = []
        for sku, qty in sorted(items.items()):
            product_data = self._storage.products[sku]
            if product_data["quantity"] < qty:
                raise InsufficientStock(f"Insufficient stock for SKU {sku}")
            lines.append(OrderLine(sku=sku, quantity=qty, unit_price_cents=product_data["price_cents"]))
        
        # Compute total
        total_cents = compute_order_total(lines)
        
        # Create order
        order_id = f"O{self._storage.next_order:04d}"
        order_dict = {
            "id": order_id,
            "customer": customer,
            "lines": [{"sku": line.sku, "quantity": line.quantity, "unit_price_cents": line.unit_price_cents} for line in lines],
            "total_cents": total_cents,
            "status": "placed",
        }
        
        # Create Order object for return
        order = Order(
            id=order_id,
            customer=customer,
            lines=lines,
            total_cents=total_cents,
            status="placed",
        )
        
        # Save order
        self._storage.orders.append(order_dict)
        self._storage.next_order += 1
        self._storage.save()
        
        # Reserve stock (reduce stock)
        for sku, qty in items.items():
            self._storage.products[sku]["quantity"] -= qty
        self._storage.save()
        
        return order

    def order(self, order_id: str) -> Order:
        """Get an order by ID.
        
        Raises:
            InvalidOrder: if order not found.
        """
        for order_dict in self._storage.orders:
            if order_dict["id"] == order_id:
                return Order(
                    id=order_dict["id"],
                    customer=order_dict["customer"],
                    lines=[OrderLine(sku=line["sku"], quantity=line["quantity"], unit_price_cents=line["unit_price_cents"]) for line in order_dict["lines"]],
                    total_cents=order_dict["total_cents"],
                    status=order_dict["status"],
                )
        raise InvalidOrder(f"Order {order_id} not found")

    def orders(self, customer: str | None = None) -> list[Order]:
        """Get orders, optionally filtered by customer.
        
        Returns:
            List of orders sorted by ID.
        """
        orders = self._storage.orders
        if customer is not None:
            orders = [o for o in orders if o["customer"] == customer]
        result = []
        for order_dict in sorted(orders, key=lambda o: o["id"]):
            result.append(Order(
                id=order_dict["id"],
                customer=order_dict["customer"],
                lines=[OrderLine(sku=line["sku"], quantity=line["quantity"], unit_price_cents=line["unit_price_cents"]) for line in order_dict["lines"]],
                total_cents=order_dict["total_cents"],
                status=order_dict["status"],
            ))
        return result

    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order.
        
        Raises:
            InvalidOrder: if order not found or already cancelled.
        """
        for order_dict in self._storage.orders:
            if order_dict["id"] == order_id:
                if order_dict["status"] == "cancelled":
                    raise InvalidOrder(f"Order {order_id} already cancelled")
                order_dict["status"] = "cancelled"
                # Restore stock
                for line in order_dict["lines"]:
                    sku = line["sku"]
                    qty = line["quantity"]
                    if sku in self._storage.products:
                        self._storage.products[sku]["quantity"] += qty
                self._storage.save()
                return Order(
                    id=order_dict["id"],
                    customer=order_dict["customer"],
                    lines=[OrderLine(sku=line["sku"], quantity=line["quantity"], unit_price_cents=line["unit_price_cents"]) for line in order_dict["lines"]],
                    total_cents=order_dict["total_cents"],
                    status=order_dict["status"],
                )
        raise InvalidOrder(f"Order {order_id} not found")
