from flask import Blueprint, request, render_template, abort, session
from flask_login import login_required, current_user
from markupsafe import Markup, escape
from sqlalchemy import distinct, func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.changelog import Changelog
from app.models.lookups import ChangelogType
from app.models.music import Artist, Song, ArtistSong
from app.models.proxy_change import ProxyChange
from app.models.user import User
from app.cache import clear_stats_cache
from app.decorators import role_required, ADMIN, USER_OR_ABOVE
from app.services.events import publish
from app.services.proxy_change import mark_approved, reject_proxy_change
from app.services.search import like_contains, LIKE_ESCAPE

changelog_bp = Blueprint('changelog', __name__)

PAGE_SIZE = 100


@changelog_bp.route('/changelog')
@login_required
def changelog():
    """Changelog page with HTMX search, user filter, and cursor pagination."""
    search = request.args.get('q', '').strip()
    user_ids = [v for v in request.args.getlist('user_id') if v.strip()]
    include = request.args.getlist('include')
    before = request.args.get('before', type=int)

    _type_order = {'Album': 0, 'Artist': 1, 'Link': 2, 'Rating': 3, 'Song': 4, 'Legacy': 99}
    all_types = sorted(ChangelogType.query.all(), key=lambda t: _type_order.get(t.type, 50))
    all_type_names = [t.type for t in all_types]

    query = Changelog.query.options(
        joinedload(Changelog.user), joinedload(Changelog.change_type),
    ).order_by(Changelog.date.desc(), Changelog.id.desc())

    if search:
        query = query.filter(Changelog.description.ilike(like_contains(search), escape=LIKE_ESCAPE))
    if user_ids:
        query = query.filter(Changelog.user_id.in_([int(v) for v in user_ids]))
    if include:
        include_ids = [ct.id for ct in all_types if ct.type in include]
        if include_ids:
            query = query.filter(Changelog.change_type_id.in_(include_ids))

    if before:
        query = query.filter(Changelog.id < before)

    entries = query.limit(PAGE_SIZE + 1).all()
    has_more = len(entries) > PAGE_SIZE
    entries = entries[:PAGE_SIZE]
    last_id = entries[-1].id if entries else None

    # Use pre-rendered HTML, fall back to escaped plain text for old rows
    for e in entries:
        e._linked_desc = Markup(e.description_html) if e.description_html else escape(e.description)

    # "Load More" HTMX request — return rows + OOB load-more button
    if before and request.headers.get('HX-Request'):
        return render_template('fragments/changelog_entries.html',
                               entries=entries, has_more=has_more, last_id=last_id)

    # Compute shown/hidden types for summary
    if include:
        shown = [t for t in all_type_names if t in include]
    else:
        shown = list(all_type_names)
    hidden = [t for t in all_type_names if t not in shown]

    # Get distinct users who have changelog entries
    all_user_ids = [r[0] for r in Changelog.query.with_entities(distinct(Changelog.user_id)).all() if r[0]]
    users = User.query.filter(User.id.in_(all_user_ids)).order_by(func.lower(User.username)).all()

    # Compute shown/hidden users for summary
    selected_ids = {int(v) for v in user_ids}
    if selected_ids:
        shown_users = [u.username for u in users if u.id in selected_ids]
    else:
        shown_users = [u.username for u in users]
    hidden_users = [u.username for u in users if u.username not in shown_users]

    if request.headers.get('HX-Request'):
        return render_template('fragments/changelog_list.html', entries=entries,
                               shown=shown, hidden=hidden,
                               shown_users=shown_users, hidden_users=hidden_users,
                               has_more=has_more, last_id=last_id)

    return render_template('changelog.html', entries=entries, search=search, user_ids=user_ids,
                           users=users, all_types=all_types, include=include,
                           shown=shown, hidden=hidden,
                           shown_users=shown_users, hidden_users=hidden_users,
                           has_more=has_more, last_id=last_id)


@changelog_bp.route('/changelog/<int:entry_id>', methods=['DELETE'])
@login_required
@role_required(ADMIN)
def delete_entry(entry_id):
    if not session.get('edit_mode'):
        abort(403)
    entry = db.session.get(Changelog, entry_id)
    if entry is None:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    return ''


def _resolve_songs(changes):
    """Batch-load songs and their main artists for display names and links."""
    song_ids = {c.song_id for c in changes}
    songs = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids)).all()} if song_ids else {}

    song_artist_links = {}
    if song_ids:
        links = ArtistSong.query.filter(ArtistSong.song_id.in_(song_ids), ArtistSong.artist_is_main == True).all()
        for link in links:
            song_artist_links[link.song_id] = link.artist_id

    artist_ids = set(song_artist_links.values())
    artists = {a.id: a for a in Artist.query.filter(Artist.id.in_(artist_ids)).all()} if artist_ids else {}

    return songs, artists, song_artist_links


def _song_display_name(change, songs, artists, song_artist_links):
    """Resolve 'Song Name (Artist)' for a proxy change, falling back to stored names."""
    song = songs.get(change.song_id)
    song_name = song.name if song else (change.song_name or f'song {change.song_id}')
    if song:
        artist = artists.get(song_artist_links.get(song.id))
        artist_name = artist.name if artist else change.artist_name
    else:
        artist_name = change.artist_name
    return f'{song_name} ({artist_name})' if artist_name else song_name


def _song_url(change, songs, artists, song_artist_links):
    """Return a URL to the song's artist page, or None if deleted."""
    song = songs.get(change.song_id)
    if song:
        artist = artists.get(song_artist_links.get(song.id))
        if artist:
            return f'/artists/{artist.id}#song-{song.id}'
    return None


@changelog_bp.route('/changelog/for-me')
@login_required
@role_required(USER_OR_ABOVE)
def for_me():
    """For Me page — proxy rating/note changes targeting the current user."""
    status = request.args.get('status', 'open')
    type_filter = request.args.get('type', '')
    view_filter = request.args.get('view', 'for-me')

    query = ProxyChange.query.options(
        joinedload(ProxyChange.proposed_by),
        joinedload(ProxyChange.resolved_by),
    )

    # View filter: for-me (target), by-me (proposer), all (both)
    if view_filter == 'by-me':
        query = query.filter(ProxyChange.proposed_by_id == current_user.id)
    elif view_filter == 'all':
        query = query.filter(
            db.or_(
                ProxyChange.target_user_id == current_user.id,
                ProxyChange.proposed_by_id == current_user.id,
            )
        )
    else:
        query = query.filter(ProxyChange.target_user_id == current_user.id)

    if status == 'open':
        query = query.filter_by(status='open')
        query = query.order_by(ProxyChange.proposed_at.desc(), ProxyChange.id.desc())
    else:
        query = query.filter(ProxyChange.status.in_(['approved', 'rejected']))
        query = query.order_by(ProxyChange.resolved_at.desc(), ProxyChange.id.desc())

    if type_filter:
        query = query.filter_by(type=type_filter)

    changes = query.all()
    songs, artists, song_artist_links = _resolve_songs(changes)

    for change in changes:
        change._song_display = _song_display_name(change, songs, artists, song_artist_links)
        change._song_url = _song_url(change, songs, artists, song_artist_links)
        is_target = change.target_user_id == current_user.id
        is_proposer = change.proposed_by_id == current_user.id
        change._can_approve = is_target and not is_proposer
        change._can_reject = is_target

    if request.headers.get('HX-Request'):
        return render_template('fragments/for_me_list.html', changes=changes, status=status)

    return render_template('changelog_for_me.html',
                           changes=changes, status=status,
                           type_filter=type_filter, view_filter=view_filter)


@changelog_bp.route('/changelog/for-me/<int:change_id>/approve', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def approve_proxy_change(change_id):
    change = db.session.get(ProxyChange, change_id)
    if not change or change.status != 'open':
        abort(404)
    # Only the target user can approve, and not changes they proposed themselves
    if change.target_user_id != current_user.id or change.proposed_by_id == current_user.id:
        abort(403)
    mark_approved(change, current_user)
    db.session.commit()
    publish('proxy-change-update', {'action': 'approved', 'id': change_id})
    return ''


@changelog_bp.route('/changelog/for-me/<int:change_id>/reject', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def reject_proxy_change_route(change_id):
    change = db.session.get(ProxyChange, change_id)
    if not change or change.status != 'open':
        abort(404)
    # The target user can reject, and the proposer can withdraw their own change
    if current_user.id not in (change.target_user_id, change.proposed_by_id):
        abort(403)

    reason = request.form.get('reason', '').strip()
    if not reason:
        return 'Rejection reason is required', 400

    reject_proxy_change(change, current_user, reason)
    clear_stats_cache()
    publish('proxy-change-update', {'action': 'rejected', 'id': change_id})
    return ''
