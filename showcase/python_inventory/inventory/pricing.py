from inventory.models import OrderLine


def compute_line_total(unit_price_cents: int, quantity: int) -> int:
    """Compute the total for a line item.
    
    If quantity >= 10: apply 5% discount (multiply by 95 // 100), rounded down.
    Otherwise: return unit_price_cents * quantity.
    """
    if quantity >= 10:
        return unit_price_cents * quantity * 95 // 100
    return unit_price_cents * quantity


def compute_order_total(lines: list[OrderLine]) -> int:
    """Compute the total for an order.
    
    Sum up all line totals. If the subtotal >= 10000: apply 10% discount.
    Otherwise: return the subtotal as-is.
    """
    subtotal = sum(compute_line_total(line.unit_price_cents, line.quantity) for line in lines)
    if subtotal >= 10000:
        return subtotal * 90 // 100
    return subtotal
