"""In-memory user presence, fed by the event poll.

NOTE: Like events.py, this only works with a single gunicorn worker.
"""

import threading
import time

_VISIBLE_TTL = 8
# Chrome throttles timers in long-hidden tabs to about one per minute.
_HIDDEN_TTL = 75
ON_PAGE = ('artist', 'misc')

_tabs = {}  # (user_id, tab_id) -> {page, artist_id, cell, away, hidden, mobile, ts, changed}
_left = {}  # (user_id, tab_id) -> time it left
_lock = threading.Lock()
_version = 0
_state = {}


def touch(user_id, tab_id, page, artist_id, cell, away, hidden, mobile=False):
    """Record a tab's location and return the current presence version."""
    now = time.time()
    with _lock:
        # A poll racing the unload beacon must not resurrect a closed tab.
        if (user_id, tab_id) in _left:
            return _refresh(now)
        prev = _tabs.get((user_id, tab_id))
        loc = (page, artist_id, cell)
        moved = prev is None or (prev['page'], prev['artist_id'], prev['cell']) != loc
        _tabs[(user_id, tab_id)] = {
            'page': page, 'artist_id': artist_id, 'cell': cell, 'away': away, 'hidden': hidden,
            'mobile': mobile, 'ts': now, 'changed': now if moved else prev['changed'],
        }
        return _refresh(now)


def leave(user_id, tab_id):
    now = time.time()
    with _lock:
        _tabs.pop((user_id, tab_id), None)
        _left[(user_id, tab_id)] = now
        return _refresh(now)


def current_version():
    with _lock:
        return _refresh(time.time())


def snapshot():
    """Return (version, {user_id: (state, page, artist_id, cell, mobile)}) for online users."""
    with _lock:
        _refresh(time.time())
        return _version, dict(_state)


def _refresh(now):
    global _version, _state
    for key, t in list(_tabs.items()):
        if now - t['ts'] > (_HIDDEN_TTL if t['hidden'] else _VISIBLE_TTL):
            del _tabs[key]
    for key, ts in list(_left.items()):
        if now - ts > _HIDDEN_TTL:
            del _left[key]
    state = _aggregate()
    if state != _state:
        _state = state
        _version += 1
    return _version


def _aggregate():
    by_user = {}
    for (user_id, _), t in _tabs.items():
        by_user.setdefault(user_id, []).append(t)
    out = {}
    for user_id, tabs in by_user.items():
        active = [t for t in tabs if not t['away']]
        on_page = [t for t in active if t['page'] in ON_PAGE]
        if on_page:
            # Latest move wins so two open artist tabs don't flip-flop every poll.
            t = max(on_page, key=lambda t: t['changed'])
            out[user_id] = ('page', t['page'], t['artist_id'], t['cell'], t['mobile'])
        elif active:
            out[user_id] = ('online', None, None, None, False)
        else:
            idle_on_page = [t for t in tabs if t['page'] in ON_PAGE]
            if idle_on_page:
                t = max(idle_on_page, key=lambda t: t['changed'])
                out[user_id] = ('away', t['page'], t['artist_id'], None, False)
            else:
                out[user_id] = ('away', None, None, None, False)
    return out
