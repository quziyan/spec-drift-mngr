# Order and refund rules

### R-REF-001 Refund window

**Current rule**
A paid, delivered order can be refunded within 14 days of delivery; on day 15
the request is refused.

**Boundary**
Nothing about partial refunds or the refund fee.

**Anchors**
- `order.py::is_refundable`
- `order.py::REFUND_WINDOW_DAYS`

**Last confirmed**
2026-09-09

### R-REF-002 Refund fee

**Current rule**
The amount returned to the customer is the requested amount minus a flat 3%
fee, rounded to two decimal places.

**Boundary**
Nothing about whether the request is eligible for a refund in the first
place.

**Anchors**
- `refund.py::RefundRequest::amount_after_fee`
- `refund.py::FEE_RATE`

**Last confirmed**
2026-09-09

### R-REF-003 Approve refund

**Current rule**
A refund request can be approved only while it is still pending; approving
moves it straight to the approved state.

**Boundary**
Nothing about who is authorized to approve, or about the payout itself.

**Anchors**
- `refund.py::approve_refund`

**Last confirmed**
2026-09-09

### R-REF-004 Escalate refund

**Current rule**
A pending refund request can be escalated for manual review; a request that
is no longer pending is returned unchanged instead of being escalated again.

**Boundary**
Nothing about who reviews an escalated request or how long review takes.

**Anchors**
- `refund.py::escalate_refund`

**Last confirmed**
2026-09-09

### R-ORD-001 Cancel order

**Current rule**
An order can be cancelled only while it is unpaid; a paid order must go
through the refund flow instead.

**Boundary**
Nothing about notifying the customer or releasing reserved inventory.

**Anchors**
- `order.py::cancel_order`

**Last confirmed**
2026-09-09

### R-PRC-001 Maximum discount

**Current rule**
A quoted discount is capped at 50%; a larger discount is silently clamped
down to the cap rather than rejected.

**Boundary**
Nothing about which discount rate is chosen for a given order.

**Anchors**
- `pricing.py::apply_discount`
- `pricing.py::MAX_DISCOUNT`

**Last confirmed**
2026-09-09
