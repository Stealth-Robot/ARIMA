"""In-memory pub/sub event bus for SSE broadcasting.

NOTE: This only works with a single gunicorn worker (--workers 1).
If workers are ever increased, replace with Redis pub/sub.
"""

import queue
import threading

_subscribers = []
_lock = threading.Lock()


def subscribe():
    """Create a new subscriber queue and register it."""
    q = queue.Queue(maxsize=50)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q):
    """Remove a subscriber queue."""
    with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def publish(event_type, data):
    """Send an event to all subscribers (non-blocking)."""
    with _lock:
        for q in _subscribers:
            try:
                q.put_nowait({'event': event_type, 'data': data})
            except queue.Full:
                pass
