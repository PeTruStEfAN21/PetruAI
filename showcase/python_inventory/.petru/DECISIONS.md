# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-27: The tests show that `restock("X", 0)` raises InventoryError. Should restock also reject negative amounts? -> Keep the API exactly as the tests use it; put errors.py, models.py, pricing.py, storage.py and shop.py inside inventory/.
- 2026-10-27: For the `Order` model, should `total_cents` be computed at construction time and stored, or computed on the fly? The tests show it's stored (e.g. `order.total_cents == 750 + 1200`). -> Standard library only (dataclasses, json, pathlib); write the JSON file atomically through a temporary file.
- 2026-10-27: For `place_order`, should the method signature accept a dict like `{"sku": quantity}` or should it accept separate `sku` and `quantity` arguments? The tests use `{"A1": 3, "B2": 1}`. -> Work test-first against tests/test_shop.py and run run_checks until everything passes.
- 2026-10-27: Modules: errors, models, pricing, storage, shop inside inventory/
- 2026-10-27: Standard library only (dataclasses, json, pathlib, tempfile)
- 2026-10-27: Order total_cents stored at construction time
- 2026-10-27: place_order accepts dict {sku: quantity}
- 2026-10-27: Atomic JSON writes via temp file + rename
- 2026-10-27: Order IDs formatted as O0001, O0002, ...
- 2026-10-27: plan confirmat: Inventory and Order Service (7 pași)
