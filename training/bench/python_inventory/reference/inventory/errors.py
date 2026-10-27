class InventoryError(Exception):
    """Base class of every error the shop raises."""


class UnknownProduct(InventoryError):
    pass


class DuplicateProduct(InventoryError):
    pass


class InsufficientStock(InventoryError):
    pass


class InvalidOrder(InventoryError):
    pass
