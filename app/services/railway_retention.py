"""Local retention of Railway resource metrics.

Railway keeps only ~30 days of metrics. When RAILWAY_RETENTION_ENABLED=true a
background poller fetches recent samples on an interval and stores them in
railway_metric_sample, so the operational-stats charts can render windows
longer than Railway's own retention. Reads are bucket-averaged so even a
multi-month window returns a chart-friendly number of points.
"""

import os
import time
import logging
import threading

from app.extensions import db
from app.services.railway import get_metrics_series, _SERIES_MEASUREMENTS

logger = logging.getLogger(__name__)

POLL_INTERVAL = 900          # 15 minutes
BACKFILL_SECONDS = 30 * 86400  # first run pulls Railway's full ~30-day retention
OVERLAP_SECONDS = 3600       # re-fetch the last hour each poll to fill any gaps
TARGET_POINTS = 1000         # bucket count for reads


def is_enabled():
    return os.environ.get('RAILWAY_RETENTION_ENABLED', '').lower() == 'true'


def _store(series):
    """INSERT OR IGNORE every (measurement, ts, value) point. Returns rows written."""
    rows = []
    for measurement, pts in (series or {}).items():
        ts_list = pts.get('ts') or []
        val_list = pts.get('value') or []
        for ts, value in zip(ts_list, val_list):
            if ts is not None and value is not None:
                rows.append({'m': measurement, 't': int(ts), 'v': float(value)})
    if not rows:
        return 0
    db.session.execute(db.text(
        'INSERT OR IGNORE INTO railway_metric_sample (measurement, ts, value) '
        'VALUES (:m, :t, :v)'
    ), rows)
    db.session.commit()
    return len(rows)


def poll_once():
    """Fetch recent metrics and persist them. Returns rows written (0 on failure)."""
    now = int(time.time())
    last_ts = db.session.execute(db.text(
        'SELECT MAX(ts) FROM railway_metric_sample'
    )).scalar()
    start = (last_ts - OVERLAP_SECONDS) if last_ts else (now - BACKFILL_SECONDS)

    result = get_metrics_series(start, now)
    if not result.get('available'):
        logger.warning('Railway retention poll skipped: %s', result.get('reason'))
        return 0
    written = _store(result.get('series'))
    logger.info('Railway retention poll: stored up to %d sample rows (since ts=%s)', written, start)
    return written


def _poll_loop(app):
    try:
        with app.app_context():
            poll_once()
    except Exception:
        logger.exception('Railway retention poll failed')
    finally:
        t = threading.Timer(POLL_INTERVAL, _poll_loop, args=[app])
        t.daemon = True
        t.start()


def start_retention_scheduler(app):
    """Start the metrics poller if enabled and Railway is configured."""
    if not is_enabled():
        return
    if not os.environ.get('RAILWAY_API_TOKEN'):
        logger.warning('Railway retention disabled: RAILWAY_API_TOKEN not set')
        return
    logger.info('Starting Railway retention poller (every %ds)', POLL_INTERVAL)
    t = threading.Timer(5, _poll_loop, args=[app])
    t.daemon = True
    t.start()


def get_stored_metrics_series(start_epoch, end_epoch):
    """Bucket-averaged time-series from the local store, shaped like get_metrics_series."""
    start, end = int(start_epoch), int(end_epoch)
    span = max(end - start, 60)
    bucket = max(60, (span // TARGET_POINTS // 60) * 60)

    rows = db.session.execute(db.text(
        'SELECT measurement, (ts / :b) * :b AS bts, AVG(value) AS v '
        'FROM railway_metric_sample '
        'WHERE measurement IN :ms AND ts BETWEEN :s AND :e '
        'GROUP BY measurement, bts ORDER BY bts'
    ).bindparams(db.bindparam('ms', expanding=True)),
        {'b': bucket, 'ms': _SERIES_MEASUREMENTS, 's': start, 'e': end}).fetchall()

    series = {m: {'ts': [], 'value': []} for m in _SERIES_MEASUREMENTS}
    for measurement, bts, v in rows:
        series[measurement]['ts'].append(int(bts))
        series[measurement]['value'].append(v)
    return {'available': True, 'source': 'local', 'bucket': bucket, 'series': series}
