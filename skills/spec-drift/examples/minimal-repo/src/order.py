"""Order domain: creation, payment state, and cancellation."""
from __future__ import annotations

REFUND_WINDOW_DAYS = 14


class Order:
    def __init__(self, order_id, total, delivered_on=None, paid=False):
        self.order_id = order_id
        self.total = total
        self.delivered_on = delivered_on
        self.paid = paid

    def is_paid(self):
        return self.paid

    def days_since_delivery(self, today):
        if self.delivered_on is None:
            return None
        return (today - self.delivered_on).days


def is_refundable(order, gate):
    if not order.is_paid():
        return False
    days = order.days_since_delivery(gate)
    if days is None:
        return False
    return days <= REFUND_WINDOW_DAYS


def cancel_order(order):
    if order.is_paid():
        raise ValueError("a paid order must be refunded, not cancelled")
    order.paid = False
    return order
