"""Simple in-process caches for context-processor queries.

Module-level dicts with TTL — no external dependencies.
Thread-safe enough for Flask's per-request threading model:
worst case two threads both refresh at the same instant, which is harmless.
"""

import time

# ---------------------------------------------------------------------------
# Part A — Country / Genre filter lists (shared across all users)
# ---------------------------------------------------------------------------

_filter_cache = {'countries': [], 'genres': [], 'ts': -9999.0}
_FILTER_TTL = 60  # seconds

def get_cached_filters():
    """Return (countries, genres) lists, refreshing at most once per TTL."""
    from app.models.lookups import Country, Genre

    now = time.monotonic()
    if now - _filter_cache['ts'] > _FILTER_TTL:
        try:
            _filter_cache['countries'] = Country.query.order_by(Country.id).all()
            _filter_cache['genres'] = Genre.query.order_by(Genre.id).all()
            _filter_cache['ts'] = now
        except Exception:
            pass  # return stale/empty lists rather than None
    return _filter_cache['countries'], _filter_cache['genres']


def clear_filter_cache():
    """Force refresh on next request (e.g. after admin adds a country/genre)."""
    _filter_cache['ts'] = 0.0


# ---------------------------------------------------------------------------
# Part B — Resolved theme dict, keyed by (user_id, theme_id)
# ---------------------------------------------------------------------------

_theme_cache = {}

def get_cached_theme(user):
    """Return resolved theme dict, caching by (user_id, theme_id)."""
    from app.services.theme import get_resolved_theme

    theme_id = user.settings.theme if user.settings else 0
    key = (user.id, theme_id)
    if key not in _theme_cache:
        _theme_cache[key] = get_resolved_theme(user)
    return _theme_cache[key]


def clear_theme_cache_for_user(user_id):
    """Remove all cached entries for a specific user."""
    keys = [k for k in _theme_cache if k[0] == user_id]
    for k in keys:
        _theme_cache.pop(k, None)


def clear_theme_cache_for_theme(theme_id):
    """Remove all cached entries that reference a specific theme."""
    keys = [k for k in _theme_cache if k[1] == theme_id]
    for k in keys:
        _theme_cache.pop(k, None)


# ---------------------------------------------------------------------------
# Part C — Stats bulk data cache, keyed by (include_featured, include_remixes)
# ---------------------------------------------------------------------------

_stats_cache = {}
_STATS_TTL = 300  # 5 minutes

def get_cached_bulk_data(include_featured, include_remixes):
    """Return cached BulkData, refreshing at most once per TTL."""
    from app.services.stats import load_bulk_data

    key = (include_featured, include_remixes)
    now = time.monotonic()
    entry = _stats_cache.get(key)
    if entry and now - entry['ts'] < _STATS_TTL:
        return entry['data']

    data = load_bulk_data(include_featured=include_featured, include_remixes=include_remixes)
    _stats_cache[key] = {'data': data, 'ts': now}
    return data


def clear_stats_cache():
    """Invalidate all stats cache entries (e.g. after a rating change or data edit)."""
    _stats_cache.clear()
