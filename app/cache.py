"""Simple in-process caches for context-processor queries.

Module-level dicts with TTL — no external dependencies.
Thread-safe enough for Flask's per-request threading model:
worst case two threads both refresh at the same instant, which is harmless.
"""

import threading
import time
from collections import OrderedDict

# glibc hoards freed arena pages, so each evicted ~40MB _BulkData ratchets RSS; trim returns them to the OS.
try:
    import ctypes
    _malloc_trim = ctypes.CDLL('libc.so.6').malloc_trim
except (OSError, AttributeError):
    _malloc_trim = None  # non-glibc platform (e.g. macOS dev) — trimming not needed/available

# ---------------------------------------------------------------------------
# Part A — Country / Genre filter lists (shared across all users)
# ---------------------------------------------------------------------------

_filter_cache = {'countries': [], 'genres': [], 'genders': [], 'album_types': [], 'ts': -9999.0}
_FILTER_TTL = 60  # seconds

def get_cached_filters():
    """Return (countries, genres, genders) lists, refreshing at most once per TTL."""
    from sqlalchemy import func, desc
    from app.extensions import db
    from app.models.lookups import Country, Genre, GroupGender, AlbumType
    from app.models.music import Artist, album_genres

    now = time.monotonic()
    if now - _filter_cache['ts'] > _FILTER_TTL:
        try:
            _filter_cache['countries'] = [
                c for c, _ in
                db.session.query(Country, func.count(Artist.id).label('cnt'))
                .outerjoin(Artist, Artist.country_id == Country.id)
                .group_by(Country.id)
                .order_by(desc('cnt'), func.lower(Country.country))
                .all()
            ]
            _filter_cache['genres'] = [
                g for g, _ in
                db.session.query(Genre, func.count(album_genres.c.album_id).label('cnt'))
                .outerjoin(album_genres, album_genres.c.genre_id == Genre.id)
                .group_by(Genre.id)
                .order_by(desc('cnt'), func.lower(Genre.genre))
                .all()
            ]
            _filter_cache['genders'] = GroupGender.query.order_by(GroupGender.id).all()
            _filter_cache['album_types'] = AlbumType.query.order_by(AlbumType.id).all()
            _filter_cache['ts'] = now
        except Exception:
            pass  # return stale/empty lists rather than None
    return _filter_cache['countries'], _filter_cache['genres'], _filter_cache['genders'], _filter_cache['album_types']


def clear_filter_cache():
    """Force refresh on next request (e.g. after admin adds a country/genre)."""
    _filter_cache['ts'] = 0.0


# ---------------------------------------------------------------------------
# Part B — Resolved theme dict, keyed by (user_id, theme_id)
# ---------------------------------------------------------------------------

_theme_cache = OrderedDict()
_theme_lock = threading.Lock()
_THEME_MAX = 256  # LRU cap — theme dicts are small but the key space is per-user

def get_cached_theme(user):
    """Return resolved theme dict, caching by (user_id, theme_id)."""
    from app.services.theme import get_resolved_theme

    theme_id = user.settings.theme if user.settings else 0
    key = (user.id, theme_id)
    with _theme_lock:
        cached = _theme_cache.get(key)
        if cached is not None:
            _theme_cache.move_to_end(key)
            return cached
    resolved = get_resolved_theme(user)
    with _theme_lock:
        _theme_cache[key] = resolved
        _theme_cache.move_to_end(key)
        while len(_theme_cache) > _THEME_MAX:
            _theme_cache.popitem(last=False)
    return resolved


def clear_theme_cache_for_user(user_id):
    """Remove all cached entries for a specific user."""
    with _theme_lock:
        keys = [k for k in _theme_cache if k[0] == user_id]
        for k in keys:
            _theme_cache.pop(k, None)


def clear_theme_cache_for_theme(theme_id):
    """Remove all cached entries that reference a specific theme."""
    with _theme_lock:
        keys = [k for k in _theme_cache if k[1] == theme_id]
        for k in keys:
            _theme_cache.pop(k, None)


# ---------------------------------------------------------------------------
# Part C — Stats bulk data cache, keyed by (include_featured, include_remixes)
# ---------------------------------------------------------------------------

_stats_cache = OrderedDict()
_stats_lock = threading.Lock()
_STATS_TTL = 300  # 5 minutes
# Hard LRU cap — each entry retains ~40MB of live heap (per-song/per-user rating
# maps), so an unbounded cache is what drove RSS from ~450MB to ~1GB between
# restarts. Cap keeps worst-case cache memory bounded regardless of key cardinality.
_STATS_MAX = 4

def get_cached_bulk_data(include_featured, include_remixes, include_covers=True, genre_ids=None, hide_osts=False, keep_remix_ids=None):
    """Return cached BulkData, refreshing at most once per TTL (LRU-bounded)."""
    from app.services.stats import load_bulk_data

    genre_key = tuple(sorted(genre_ids)) if genre_ids else ()
    keep_key = tuple(sorted(keep_remix_ids)) if keep_remix_ids else ()
    key = (include_featured, include_remixes, include_covers, genre_key, hide_osts, keep_key)
    now = time.monotonic()
    with _stats_lock:
        entry = _stats_cache.get(key)
        if entry and now - entry['ts'] < _STATS_TTL:
            _stats_cache.move_to_end(key)
            return entry['data']

    data = load_bulk_data(include_featured=include_featured, include_remixes=include_remixes, include_covers=include_covers, genre_ids=genre_ids, hide_osts=hide_osts, keep_remix_ids=keep_remix_ids)
    with _stats_lock:
        _stats_cache[key] = {'data': data, 'ts': time.monotonic()}
        _stats_cache.move_to_end(key)
        while len(_stats_cache) > _STATS_MAX:
            _stats_cache.popitem(last=False)
    if _malloc_trim:
        _malloc_trim(0)
    return data


def clear_stats_cache():
    """Invalidate all stats cache entries (e.g. after a rating change or data edit)."""
    with _stats_lock:
        _stats_cache.clear()


# ---------------------------------------------------------------------------
# Part D — Railway platform stats (slow external API, shared across all users)
# ---------------------------------------------------------------------------

_railway_cache = {'data': None, 'ts': -9999.0}
_RAILWAY_TTL = 90  # seconds — Railway's API is slow and rate-limited

def get_cached_railway_stats():
    """Return Railway platform stats, refreshing at most once per TTL.

    On a failed refresh, returns the last good value rather than blanking the
    section; the underlying service already degrades per-section on its own.
    """
    from app.services.railway import get_railway_stats

    now = time.monotonic()
    if _railway_cache['data'] is None or now - _railway_cache['ts'] > _RAILWAY_TTL:
        try:
            _railway_cache['data'] = get_railway_stats()
            _railway_cache['ts'] = now
        except Exception:
            if _railway_cache['data'] is None:
                _railway_cache['data'] = {'available': False, 'reason': 'Railway stats unavailable'}
    return _railway_cache['data']


def get_cache_status():
    """Snapshot of in-process cache occupancy for the operational-stats page."""
    now = time.monotonic()
    filter_age = now - _filter_cache['ts'] if _filter_cache['ts'] > 0 else None
    return {
        'theme_cache_entries': len(_theme_cache),
        'stats_cache_entries': len(_stats_cache),
        'filter_cache_age_seconds': filter_age,
        'railway_cache_age_seconds': (now - _railway_cache['ts']) if _railway_cache['data'] is not None else None,
    }
