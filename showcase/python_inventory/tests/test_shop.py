import json

import pytest

from inventory import (
    DuplicateProduct,
    InsufficientStock,
    InvalidOrder,
    InventoryError,
    Shop,
    UnknownProduct,
)


@pytest.fixture
def shop(tmp_path):
    s = Shop(tmp_path / "shop.json")
    s.add_product("A1", "Widget", price_cents=250, quantity=10)
    s.add_product("B2", "Gadget", price_cents=1200, quantity=3)
    return s


def test_products_are_listed_by_sku(shop):
    shop.add_product("0Z", "Zero", price_cents=1, quantity=0)
    assert [p.sku for p in shop.products()] == ["0Z", "A1", "B2"]
    widget = shop.product("A1")
    assert (widget.name, widget.price_cents, widget.quantity) == ("Widget", 250, 10)


def test_duplicate_and_unknown_products(shop):
    with pytest.raises(DuplicateProduct):
        shop.add_product("A1", "Again", price_cents=1, quantity=1)
    with pytest.raises(UnknownProduct):
        shop.product("nope")
    with pytest.raises(UnknownProduct):
        shop.restock("nope", 1)
    for error in (UnknownProduct, DuplicateProduct, InsufficientStock, InvalidOrder):
        assert issubclass(error, InventoryError)


def test_invalid_product_values(tmp_path):
    s = Shop(tmp_path / "s.json")
    with pytest.raises(InventoryError):
        s.add_product("X", "Bad", price_cents=-1, quantity=1)
    with pytest.raises(InventoryError):
        s.add_product("X", "Bad", price_cents=1, quantity=-1)
    s.add_product("X", "Ok", price_cents=1, quantity=1)
    with pytest.raises(InventoryError):
        s.restock("X", 0)


def test_restock_and_low_stock(shop):
    shop.restock("B2", 4)
    assert shop.product("B2").quantity == 7
    shop.add_product("C3", "Thing", price_cents=5, quantity=2)
    assert shop.low_stock(5) == ["C3"]
    assert shop.low_stock(11) == ["A1", "B2", "C3"]


def test_place_order_reserves_stock(shop):
    order = shop.place_order("alice", {"A1": 3, "B2": 1})
    assert order.id == "O0001"
    assert order.customer == "alice"
    assert order.status == "placed"
    assert [(line.sku, line.quantity, line.unit_price_cents) for line in order.lines] == [
        ("A1", 3, 250),
        ("B2", 1, 1200),
    ]
    assert order.total_cents == 750 + 1200
    assert shop.product("A1").quantity == 7
    assert shop.product("B2").quantity == 2
    assert shop.place_order("bob", {"A1": 1}).id == "O0002"


def test_failed_order_changes_nothing(shop):
    with pytest.raises(InsufficientStock):
        shop.place_order("alice", {"A1": 2, "B2": 4})
    with pytest.raises(UnknownProduct):
        shop.place_order("alice", {"A1": 2, "ZZ": 1})
    assert shop.product("A1").quantity == 10
    assert shop.orders() == []
    with pytest.raises(InvalidOrder):
        shop.place_order("alice", {})
    with pytest.raises(InvalidOrder):
        shop.place_order("alice", {"A1": 0})
    with pytest.raises(InvalidOrder):
        shop.place_order("", {"A1": 1})
    assert shop.place_order("alice", {"A1": 1}).id == "O0001"


def test_bulk_line_discount(shop):
    shop.restock("A1", 10)
    order = shop.place_order("alice", {"A1": 10})
    assert order.total_cents == 2500 * 95 // 100


def test_large_order_discount(tmp_path):
    s = Shop(tmp_path / "s.json")
    s.add_product("TV", "Television", price_cents=4999, quantity=5)
    order = s.place_order("carol", {"TV": 3})
    assert order.total_cents == 14997 * 90 // 100
    s.add_product("P", "Pen", price_cents=1000, quantity=50)
    both = s.place_order("dan", {"P": 10, "TV": 1})
    subtotal = 10000 * 95 // 100 + 4999
    assert both.total_cents == subtotal * 90 // 100


def test_cancel_restores_stock(shop):
    order = shop.place_order("alice", {"A1": 4})
    cancelled = shop.cancel_order(order.id)
    assert cancelled.status == "cancelled"
    assert shop.order(order.id).status == "cancelled"
    assert shop.product("A1").quantity == 10
    with pytest.raises(InvalidOrder):
        shop.cancel_order(order.id)
    with pytest.raises(InvalidOrder):
        shop.cancel_order("O9999")


def test_order_keeps_its_price(shop):
    order = shop.place_order("alice", {"B2": 1})
    shop.set_price("B2", 9999)
    assert shop.order(order.id).total_cents == 1200
    assert shop.product("B2").price_cents == 9999


def test_orders_filter_by_customer(shop):
    shop.place_order("alice", {"A1": 1})
    shop.place_order("bob", {"A1": 1})
    shop.place_order("alice", {"B2": 1})
    assert [o.id for o in shop.orders()] == ["O0001", "O0002", "O0003"]
    assert [o.id for o in shop.orders(customer="alice")] == ["O0001", "O0003"]


def test_state_survives_reopen(tmp_path):
    path = tmp_path / "data" / "shop.json"
    s = Shop(path)
    s.add_product("A1", "Widget", price_cents=250, quantity=10)
    s.place_order("alice", {"A1": 2})
    s.cancel_order(s.place_order("bob", {"A1": 1}).id)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {"products", "orders", "next_order"} <= set(data)
    again = Shop(path)
    assert again.product("A1").quantity == 8
    assert [(o.id, o.status) for o in again.orders()] == [("O0001", "placed"), ("O0002", "cancelled")]
    assert again.place_order("carol", {"A1": 1}).id == "O0003"


def test_remove_product(shop):
    shop.remove_product("B2")
    assert [p.sku for p in shop.products()] == ["A1"]
    with pytest.raises(UnknownProduct):
        shop.remove_product("B2")
