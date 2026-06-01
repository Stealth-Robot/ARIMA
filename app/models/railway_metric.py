from app.extensions import db


class RailwayMetricSample(db.Model):
    """A single Railway resource-metric reading, stored locally for history.

    Railway only retains ~30 days of metrics; a background poller writes samples
    here so the operational-stats charts can show an arbitrarily long window.
    Composite (measurement, ts) primary key makes re-polling overlapping windows
    idempotent via INSERT OR IGNORE.
    """
    __tablename__ = 'railway_metric_sample'
    measurement = db.Column(db.String(40), primary_key=True)
    ts = db.Column(db.Integer, primary_key=True)  # unix seconds
    value = db.Column(db.Float, nullable=False)
