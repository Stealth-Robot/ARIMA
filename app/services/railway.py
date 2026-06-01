"""Railway platform statistics via the public GraphQL API.

Surfaces resource metrics, recent deployments, and an estimated cost for the
service this app runs on. All calls go through the shared api_queue (retry +
429 handling) and require a RAILWAY_API_TOKEN. The project/service/environment
IDs are read from the RAILWAY_* variables Railway injects at runtime.

The GraphQL query strings below target Railway's public schema at
https://backboard.railway.com/graphql/v2. Railway does not publish exact field
and enum names, so confirm them against railway.com/graphiql (introspection)
before relying on live data. Parsing is defensive: a schema mismatch or API
failure degrades a section to None rather than raising to the request.
"""

import os
import json
import logging

from app.services.api_queue import railway_queue, ApiQueueError

logger = logging.getLogger(__name__)

_ENDPOINT = 'https://backboard.railway.com/graphql/v2'

# Measurements requested for the metrics and usage queries. Enum values follow
# Railway's MetricMeasurement type — confirm via GraphiQL introspection.
_MEASUREMENTS = ['CPU_USAGE', 'MEMORY_USAGE_GB', 'NETWORK_TX_GB', 'DISK_USAGE_GB']

_METRICS_QUERY = """
query Metrics($projectId: String!, $environmentId: String!, $serviceId: String!, $startDate: DateTime!, $measurements: [MetricMeasurement!]!) {
  metrics(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId, startDate: $startDate, measurements: $measurements, sampleRateSeconds: 3600) {
    measurement
    values { ts value }
  }
}
"""

_DEPLOYMENTS_QUERY = """
query Deployments($projectId: String!, $environmentId: String!, $serviceId: String!) {
  deployments(first: 5, input: {projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId}) {
    edges { node { id status createdAt } }
  }
}
"""

_USAGE_QUERY = """
query Usage($projectId: String!, $measurements: [MetricMeasurement!]!) {
  estimatedUsage(projectId: $projectId, measurements: $measurements) {
    measurement
    estimatedValue
  }
}
"""

_CURRENT_USAGE_QUERY = """
query CurrentUsage($projectId: String!, $measurements: [MetricMeasurement!]!) {
  usage(projectId: $projectId, measurements: $measurements) {
    measurement
    value
  }
}
"""

# Railway list prices. CPU/memory/disk usage is billed per vCPU- or GB-minute
# (these measurements are returned in minute-integrated units); network egress
# is a flat per-GB charge. 43200 = minutes in a 30-day month.
_RATE_PER_MIN = {
    'CPU_USAGE': 20.0 / 43200,        # $20 / vCPU-month
    'MEMORY_USAGE_GB': 10.0 / 43200,  # $10 / GB-month
    'DISK_USAGE_GB': 0.15 / 43200,    # $0.15 / GB-month
    'EPHEMERAL_DISK_USAGE_GB': 0.15 / 43200,
}
_RATE_PER_GB = {'NETWORK_TX_GB': 0.05}  # $0.05 / GB egress
_COST_MEASUREMENTS = ['CPU_USAGE', 'MEMORY_USAGE_GB', 'NETWORK_TX_GB', 'DISK_USAGE_GB']


def _cost(measurement, value):
    """Dollar cost of a usage value, per Railway list prices."""
    if value is None:
        return 0.0
    if measurement in _RATE_PER_MIN:
        return value * _RATE_PER_MIN[measurement]
    return value * _RATE_PER_GB.get(measurement, 0.0)


_SERIES_QUERY = """
query MetricsSeries($projectId: String!, $environmentId: String!, $serviceId: String!, $startDate: DateTime!, $endDate: DateTime!, $sampleRateSeconds: Int!, $measurements: [MetricMeasurement!]!) {
  metrics(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId, startDate: $startDate, endDate: $endDate, sampleRateSeconds: $sampleRateSeconds, measurements: $measurements) {
    measurement
    values { ts value }
  }
}
"""

# Measurements plotted as time-series on the operational-stats charts.
_SERIES_MEASUREMENTS = ['CPU_USAGE', 'MEMORY_USAGE_GB', 'NETWORK_TX_GB', 'DISK_USAGE_GB']


class RailwayError(Exception):
    pass


def _ids():
    """Project/service/environment IDs Railway injects at runtime."""
    return (
        os.environ.get('RAILWAY_PROJECT_ID'),
        os.environ.get('RAILWAY_SERVICE_ID'),
        os.environ.get('RAILWAY_ENVIRONMENT_ID'),
    )


def _post(query, variables):
    token = os.environ.get('RAILWAY_API_TOKEN')
    if not token:
        raise RailwayError('RAILWAY_API_TOKEN not configured')
    body = json.dumps({'query': query, 'variables': variables})
    try:
        resp = railway_queue.request(
            'POST', _ENDPOINT,
            headers={'Authorization': f'Bearer {token}',
                     'Content-Type': 'application/json'},
            data=body, timeout=15,
        )
    except ApiQueueError as exc:
        raise RailwayError(str(exc))
    if resp.status_code != 200:
        raise RailwayError(f'Railway API returned HTTP {resp.status_code}')
    payload = resp.json()
    if payload.get('errors'):
        first = payload['errors'][0]
        raise RailwayError(first.get('message', 'GraphQL error'))
    return payload.get('data') or {}


def _latest(values):
    """Last data point from a metrics value series, or None."""
    if not values:
        return None
    last = values[-1]
    return last.get('value')


def _fetch_metrics(project_id, environment_id, service_id):
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    data = _post(_METRICS_QUERY, {
        'projectId': project_id,
        'environmentId': environment_id,
        'serviceId': service_id,
        'startDate': start,
        'measurements': _MEASUREMENTS,
    })
    out = {}
    for series in data.get('metrics') or []:
        out[series.get('measurement')] = _latest(series.get('values'))
    return out


def _fetch_deployments(project_id, environment_id, service_id):
    data = _post(_DEPLOYMENTS_QUERY, {
        'projectId': project_id,
        'environmentId': environment_id,
        'serviceId': service_id,
    })
    edges = (data.get('deployments') or {}).get('edges') or []
    return [
        {
            'id': e['node'].get('id'),
            'status': e['node'].get('status'),
            'created_at': e['node'].get('createdAt'),
        }
        for e in edges if e.get('node')
    ]


def _fetch_usage(project_id):
    data = _post(_USAGE_QUERY, {
        'projectId': project_id,
        'measurements': _MEASUREMENTS,
    })
    return {
        u.get('measurement'): u.get('estimatedValue')
        for u in (data.get('estimatedUsage') or [])
    }


def _fetch_costs(project_id):
    """Current per-resource cost + current/estimated totals, in dollars.

    Reproduces Railway's "Project usage" dollar cards: current usage comes from
    the date-less `usage` query (current billing period), the estimated total
    from `estimatedUsage`, both priced with the list rates above.
    """
    cur = _post(_CURRENT_USAGE_QUERY, {'projectId': project_id, 'measurements': _COST_MEASUREMENTS})
    est = _post(_USAGE_QUERY, {'projectId': project_id, 'measurements': _COST_MEASUREMENTS})

    current = {u.get('measurement'): _cost(u.get('measurement'), u.get('value'))
               for u in (cur.get('usage') or [])}
    estimated_total = sum(_cost(u.get('measurement'), u.get('estimatedValue'))
                          for u in (est.get('estimatedUsage') or []))
    return {
        'cpu': current.get('CPU_USAGE', 0.0),
        'memory': current.get('MEMORY_USAGE_GB', 0.0),
        'network': current.get('NETWORK_TX_GB', 0.0),
        'volume': current.get('DISK_USAGE_GB', 0.0),
        'current_total': sum(current.values()),
        'estimated_total': estimated_total,
    }


def get_railway_stats():
    """Resource metrics, recent deployments, and estimated usage.

    Returns a dict with 'available' False (plus 'reason') when Railway can't be
    queried, or 'available' True with metrics/deployments/usage sections. Each
    section is fetched independently so one failure doesn't blank the others;
    per-section failures land in 'errors'.
    """
    if not os.environ.get('RAILWAY_API_TOKEN'):
        return {'available': False, 'reason': 'RAILWAY_API_TOKEN not configured'}

    project_id, service_id, environment_id = _ids()
    if not all((project_id, service_id, environment_id)):
        return {'available': False,
                'reason': 'Railway project/service/environment IDs not present in environment'}

    result = {'available': True, 'metrics': None, 'deployments': None,
              'usage': None, 'costs': None, 'errors': []}

    try:
        result['costs'] = _fetch_costs(project_id)
    except RailwayError as exc:
        logger.warning('Railway costs fetch failed: %s', exc)
        result['errors'].append(f'costs: {exc}')

    try:
        result['metrics'] = _fetch_metrics(project_id, environment_id, service_id)
    except RailwayError as exc:
        logger.warning('Railway metrics fetch failed: %s', exc)
        result['errors'].append(f'metrics: {exc}')

    try:
        result['deployments'] = _fetch_deployments(project_id, environment_id, service_id)
    except RailwayError as exc:
        logger.warning('Railway deployments fetch failed: %s', exc)
        result['errors'].append(f'deployments: {exc}')

    try:
        result['usage'] = _fetch_usage(project_id)
    except RailwayError as exc:
        logger.warning('Railway usage fetch failed: %s', exc)
        result['errors'].append(f'usage: {exc}')

    return result


def _sample_rate(span_seconds):
    """Seconds-per-sample targeting ~600 points, rounded to a 60s multiple, min 60."""
    target = (span_seconds // 600 // 60) * 60
    return max(60, target)


def get_metrics_series(start_epoch, end_epoch):
    """Resource-metric time-series for the charts, between two unix timestamps.

    Returns {'available': True, 'sample_rate': N, 'series': {measurement:
    {'ts': [...], 'value': [...]}}} or {'available': False, 'reason': ...}.
    """
    from datetime import datetime, timezone

    if not os.environ.get('RAILWAY_API_TOKEN'):
        return {'available': False, 'reason': 'RAILWAY_API_TOKEN not configured'}
    project_id, service_id, environment_id = _ids()
    if not all((project_id, service_id, environment_id)):
        return {'available': False,
                'reason': 'Railway project/service/environment IDs not present in environment'}

    span = max(int(end_epoch) - int(start_epoch), 60)
    sample_rate = _sample_rate(span)
    try:
        data = _post(_SERIES_QUERY, {
            'projectId': project_id,
            'environmentId': environment_id,
            'serviceId': service_id,
            'startDate': datetime.fromtimestamp(int(start_epoch), tz=timezone.utc).isoformat(),
            'endDate': datetime.fromtimestamp(int(end_epoch), tz=timezone.utc).isoformat(),
            'sampleRateSeconds': sample_rate,
            'measurements': _SERIES_MEASUREMENTS,
        })
    except RailwayError as exc:
        logger.warning('Railway metrics series fetch failed: %s', exc)
        return {'available': False, 'reason': str(exc)}

    series = {}
    for s in data.get('metrics') or []:
        pts = s.get('values') or []
        series[s.get('measurement')] = {
            'ts': [p.get('ts') for p in pts],
            'value': [p.get('value') for p in pts],
        }
    return {'available': True, 'sample_rate': sample_rate, 'series': series}
