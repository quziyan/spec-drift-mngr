"""Pricing domain: base price, discounts, and final quotes."""
from __future__ import annotations

MAX_DISCOUNT = 0.5


def base_price(order):
    if order.total < 0:
        raise ValueError("order total cannot be negative")
    return order.total


def apply_discount(price, discount):
    if discount > MAX_DISCOUNT:
        discount = MAX_DISCOUNT
    return round(price * (1 - discount), 2)


def quote(order):
    price = base_price(order)
    if price == 0:
        return 0.0
    return apply_discount(price, 0.0)
