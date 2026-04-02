"""Simple in-process caches for context-processor queries.

Module-level dicts with TTL — no external dependencies.
Thread-safe enough for Flask's per-request threading model:
worst case two threads both refresh at the same instant, which is harmless.
"""

import time

# ---------------------------------------------------------------------------
# Part A — Country / Genre filter lists (shared across all users)
# ---------------------------------------------------------------------------

_filter_cache = {'countries': None, 'genres': None, 'ts': 0.0}
_FILTER_TTL = 60  # seconds

def get_cached_filters():
    """Return (countries, genres) lists, refreshing at most once per TTL."""
    from app.models.lookups import Country, Genre

    now = time.monotonic()
    if now - _filter_cache['ts'] > _FILTER_TTL:
        _filter_cache['countries'] = Country.query.order_by(Country.id).all()
        _filter_cache['genres'] = Genre.query.order_by(Genre.id).all()
        _filter_cache['ts'] = now
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
