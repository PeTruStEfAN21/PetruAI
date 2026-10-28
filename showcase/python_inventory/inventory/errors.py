class InventoryError(Exception):
    """Base exception for inventory operations."""


class UnknownProduct(InventoryError):
    """The requested SKU does not exist."""


class DuplicateProduct(InventoryError):
    """A product with this SKU already exists."""


class InsufficientStock(InventoryError):
    """Not enough units in stock."""


class InvalidOrder(InventoryError):
    """The order is invalid (empty, zero qty, empty customer, etc.)."""
