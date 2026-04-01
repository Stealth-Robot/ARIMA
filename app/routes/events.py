import json
import queue

from flask import Blueprint, Response
from flask_login import login_required

from app.services.events import subscribe, unsubscribe

events_bp = Blueprint('events', __name__)


@events_bp.route('/events/ratings')
@login_required
def rating_stream():
    """SSE stream for real-time rating updates."""
    def generate():
        q = subscribe()
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
