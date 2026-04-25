import json

from flask import Blueprint, render_template, session, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist, ArtistSubscription
from app.services.stats import get_display_users, get_artist_stats
from app.services.artist import get_top_level_artists
from app.cache import get_cached_bulk_data
from app.decorators import role_required, ADMIN

subscriptions_bp = Blueprint('subscriptions', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}


def _get_viewer_settings():
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return {
            'include_featured': current_user.settings.include_featured,
            'include_remixes': current_user.settings.include_remixes,
            'country_ids': list(current_user.settings.country_ids or []),
            'genre_ids': list(current_user.settings.genre_ids or []),
            'hide_osts': getattr(current_user.settings, 'hide_osts', False),
        }
    return {
        'include_featured': False,
        'include_remixes': False,
        'country_ids': list(session.get('country_ids') or []),
        'genre_ids': list(session.get('genre_ids') or []),
        'hide_osts': session.get('hide_osts', False),
    }


@subscriptions_bp.route('/subscriptions')
@login_required
def subscriptions_page():
    users = get_display_users()
    if not any(u.id == current_user.id for u in users):
        users = list(users) + [current_user]

    settings = _get_viewer_settings()
    country_ids = settings.pop('country_ids')
    genre_ids = settings.pop('genre_ids')
    bulk = get_cached_bulk_data(**settings, genre_ids=genre_ids)

    artists = get_top_level_artists(bulk)
    if country_ids:
        country_set = set(country_ids)
        artists = [a for a in artists if a.country_id in country_set]

    sub_ids = {s.artist_id for s in
               ArtistSubscription.query.filter_by(user_id=current_user.id).all()}

    hide_osts = settings.get('hide_osts', False)
    rows = []
    for a in artists:
        stats = get_artist_stats(a.id, users, bulk)
        if (genre_ids or hide_osts) and stats['song_count'] == 0:
            continue
        my = stats['per_user'].get(current_user.id,
                                   {'pct_rated': 0.0, 'unrated_count': 0})
        rows.append({
            'artist': a,
            'global_pct': stats['global_avg_pct'],
            'my_pct': my['pct_rated'],
            'my_remaining': my['unrated_count'],
            'song_count': stats['song_count'],
            'is_subscribed': a.id in sub_ids,
        })

    rows.sort(key=lambda r: (not r['is_subscribed'], r['artist'].name.lower()))

    return render_template('subscriptions.html',
                           rows=rows, gender_css=GENDER_CSS)


@subscriptions_bp.route('/subscriptions/toggle-tracked/<int:artist_id>',
                        methods=['POST'])
@login_required
@role_required(ADMIN)
def toggle_tracked(artist_id):
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    artist.is_tracked = not artist.is_tracked
    db.session.commit()
    return json.dumps({'is_tracked': artist.is_tracked}), 200, \
        {'Content-Type': 'application/json'}
