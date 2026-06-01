from app.extensions import db


class BillingCost(db.Model):
    """Manually-entered real dollar amount paid for one Railway billing cycle.

    Keyed by the cycle's start date (ISO, the billing-anchor day). Entered by an
    admin per month; the API can't report the actually-billed amount.
    """
    __tablename__ = 'billing_cost'
    cycle_start = db.Column(db.Text, primary_key=True)  # ISO date of the cycle start (the 17th)
    amount = db.Column(db.Float, nullable=False)
