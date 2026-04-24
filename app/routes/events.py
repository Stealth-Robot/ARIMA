from flask import Blueprint, request
from flask_login import login_required

from app.services.events import get_changes_since

events_bp = Blueprint('events', __name__)


@events_bp.route('/events/poll')
@login_required
def poll_events():
    """Return events since the given sequence number."""
    since = request.args.get('since', 0, type=int)
    events, current_seq = get_changes_since(since)
    return {'seq': current_seq, 'events': events}
