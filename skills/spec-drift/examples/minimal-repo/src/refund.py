"""Refund domain: refund requests, fees, and the approval workflow."""
from __future__ import annotations

FEE_RATE = 0.03


class RefundRequest:
    def __init__(self, request_id, order, amount, reason=None):
        self.request_id = request_id
        self.order = order
        self.amount = amount
        self.reason = reason
        self.status = "pending"

    def amount_after_fee(self):
        if self.amount <= 0:
            return 0.0
        return round(self.amount * (1 - FEE_RATE), 2)


def approve_refund(req):
    if req.status != "pending":
        raise ValueError("only a pending request can be approved")
    req.status = "approved"
    return req


def reject_refund(req, reason):
    if not reason:
        raise ValueError("a rejection requires a reason")
    req.status = "rejected"
    req.reason = reason
    return req


def escalate_refund(req):
    if req.status != "pending":
        return req
    req.status = "escalated"
    return req
