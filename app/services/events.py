"""In-memory change log for event polling.

NOTE: This only works with a single gunicorn worker (--workers 1).
If workers are ever increased, replace with Redis pub/sub.
"""

import threading
import time

_changes = []
_seq = int(time.time())
_lock = threading.Lock()
_MAX_AGE = 300  # prune entries older than 5 minutes


def publish(event_type, data):
    """Record an event in the change log."""
    global _seq
    with _lock:
        _seq += 1
        _changes.append({'seq': _seq, 'event': event_type, 'data': data, 'ts': time.time()})
        cutoff = time.time() - _MAX_AGE
        while _changes and _changes[0]['ts'] < cutoff:
            _changes.pop(0)


def get_changes_since(seq):
    """Return (events_list, current_seq) for all events after the given seq."""
    with _lock:
        events = [{'event': c['event'], 'data': c['data']} for c in _changes if c['seq'] > seq]
        return events, _seq


def get_current_seq():
    """Return the current sequence number."""
    with _lock:
        return _seq
