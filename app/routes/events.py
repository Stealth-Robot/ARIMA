import re

from flask import Blueprint, g, request, url_for
from flask_login import current_user, login_required

from app.models.music import Artist
from app.models.user import User
from app.services import presence
from app.services.events import get_changes_since, get_current_seq

events_bp = Blueprint('events', __name__)


# Taken before the page's data is queried, so the first poll gets only edits the page hasn't seen.
@events_bp.before_app_request
def _record_event_seq():
    g.event_seq = get_current_seq()


@events_bp.app_context_processor
def _inject_event_seq():
    return {'event_seq': g.get('event_seq', 0)}

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}
PRESENCE_COLORS = ['#E11D48', '#7C3AED', '#0891B2', '#059669', '#D97706', '#2563EB',
                   '#DB2777', '#65A30D', '#0D9488', '#9333EA', '#EA580C', '#4F46E5']
_CELL_RE = re.compile(r'^\d+-\d+$')
_payload_cache = {'version': None, 'payload': None}


def _tracks_presence():
    return current_user.can_rate and not current_user.is_system_or_guest


def _presence_payload():
    version, state = presence.snapshot()
    if _payload_cache['version'] == version:
        return _payload_cache['payload']
    raters = (User.query.filter(User.role_id.in_((0, 1, 2)), User.email.isnot(None))
              .order_by(User.sort_order).all())
    artist_ids = {s[2] for s in state.values() if s[1] == 'artist' and s[2]}
    artists ={a.id: a for a in Artist.query.filter(Artist.id.in_(artist_ids)).all()} if artist_ids else {}
    default_img = url_for('static', filename='img/default_image.png')
    users = []
    for i, u in enumerate(raters):
        st, page, artist_id, cell, mobile = state.get(u.id, ('offline', None, None, None, False))
        loc = None
        if page:
            a = artists.get(artist_id)
            if page == 'artist' and a:
                loc = {'key': f'a{a.id}', 'artist_id': a.id, 'name': a.name, 'css': GENDER_CSS.get(a.gender_id)}
            elif page == 'misc':
                loc = {'key': 'misc', 'artist_id': None, 'name': 'Misc', 'css': '--gender-mixed'}
            elif st == 'page':
                st, cell = 'online', None
        users.append({'id': u.id, 'name': u.username, 'img': u.profile_image or default_img,
                      'default_img': default_img, 'color': PRESENCE_COLORS[i % len(PRESENCE_COLORS)],
                      'state': st, 'loc': loc, 'cell': cell, 'mobile': mobile})
    payload = {'v': version, 'users': users}
    _payload_cache.update(version=version, payload=payload)
    return payload


@events_bp.route('/events/poll')
@login_required
def poll_events():
    """Return events since the given sequence number, recording the caller's presence."""
    since = request.args.get('since', 0, type=int)
    events, current_seq = get_changes_since(since)
    tab = request.args.get('tab', '')[:32]
    if tab and _tracks_presence():
        page = request.args.get('page', 'other')
        if page not in presence.ON_PAGE:
            page = 'other'
        artist_id = request.args.get('artist', type=int) if page == 'artist' else None
        cell = request.args.get('cell', '')
        cell = cell if page in presence.ON_PAGE and _CELL_RE.match(cell) else None
        version = presence.touch(current_user.id, tab, page, artist_id, cell,
                                 away=request.args.get('away') == '1',
                                 hidden=request.args.get('hidden') == '1',
                                 mobile=request.args.get('m') == '1')
    else:
        version = presence.current_version()
    resp = {'seq': current_seq, 'events': events}
    if request.args.get('pv', -1, type=int) != version:
        resp['presence'] = _presence_payload()
    return resp


@events_bp.route('/presence/leave', methods=['POST'])
@login_required
def presence_leave():
    tab = request.form.get('tab', '')[:32]
    if tab and _tracks_presence():
        presence.leave(current_user.id, tab)
    return '', 204
