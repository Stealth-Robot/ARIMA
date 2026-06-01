"""Railway billing cycles and the manually-entered real cost per cycle.

The billing cycle is anchored on the 17th: each cycle runs from the 17th of one
month to the 17th of the next and is billed on its end date. The first tracked
cycle is Apr 17 2026 – May 17 2026 (first bill paid May 17 2026).
"""

from datetime import date

from app.models.billing_cost import BillingCost

ANCHOR_DAY = 17
FIRST_CYCLE_START = date(2026, 4, 17)


def _next_cycle_start(d):
    year, month = d.year, d.month + 1
    if month > 12:
        year, month = year + 1, 1
    return date(year, month, ANCHOR_DAY)


def get_billing_cycles(today=None):
    """All cycles from the first tracked one through the current (in-progress) one.

    Each entry: {start, end, key, amount} where amount is the stored real cost
    (or None if not yet entered) and key is the cycle-start ISO date.
    """
    today = today or date.today()
    stored = {b.cycle_start: b.amount for b in BillingCost.query.all()}

    cycles = []
    start = FIRST_CYCLE_START
    while start <= today:
        end = _next_cycle_start(start)
        key = start.isoformat()
        cycles.append({'start': start, 'end': end, 'key': key, 'amount': stored.get(key)})
        start = end
    return cycles
