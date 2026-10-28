# python_inventory

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build an inventory and order service in Python 3 (standard library only), as the package `inventory/` at the project root. The acceptance tests are in tests/test_shop.py; do not change them or pyproject.toml.

Public API, importable from `inventory`:
- Errors: `InventoryError` (base), `UnknownProduct`, `DuplicateProduct`, `InsufficientStock`, `InvalidOrder`, all subclasses of InventoryError.
- `Product` (sku, name, price_cents, quantity); `OrderLine` (sku, quantity, unit_price_cents); `Order` (id, customer, lines, total_cents, status: "placed" or "cancelled").
- `Shop(path)`: loads its state from the JSON file at `path` (a missing file is an empty shop) and writes it back after every change, as one JSON object with the keys "products", "orders" and "next_order"; parent folders are created.
  - add_product(sku, name, *, price_cents, quantity) (negative values raise InventoryError, an existing sku DuplicateProduct); product(sku); products() sorted by sku; restock(sku, amount) (amount > 0); set_price(sku, price_cents); remove_product(sku); low_stock(threshold) -> the skus with quantity below threshold, sorted.
  - place_order(customer, {sku: quantity}) -> Order with ids O0001, O0002, ...; the stock is reserved. An order that fails (unknown product, not enough stock, no items, quantity <= 0, empty customer) changes nothing.
  - order(id) (unknown id: InvalidOrder); orders(customer=None) in id order; cancel_order(id) puts the stock back, and cancelling twice or an unknown id raises InvalidOrder.
- Pricing: a line of 10 or more units gets 5% off (integer cents, rounded down); then a subtotal of 10000 cents or more gets 10% off (rounded down). An order keeps the unit prices it was placed with.

Split the code into modules: errors, models, pricing, storage, shop.

## Result

- Acceptance tests: passed
- Time: 17 min as a team, 7 min for the 35B alone
- Pieces handed to the assistant: 3

## Who wrote what

| File | Written by |
|---|---|
| `.gitignore` | lead |
| `.petru/DECISIONS.md` | lead |
| `inventory/__init__.py` | lead |
| `inventory/errors.py` | lead |
| `inventory/models.py` | lead |
| `inventory/pricing.py` | assistant |
| `inventory/shop.py` | assistant |
| `inventory/storage.py` | lead, extended by the assistant |
| `pyproject.toml` | given with the task |
| `tests/test_shop.py` | given with the task |
