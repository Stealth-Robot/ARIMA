from collections import OrderedDict

from flask import Blueprint, request, render_template, abort, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.submission import Submission
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong
from app.models.user import User
from app.decorators import role_required, EDITOR_OR_ADMIN, USER_OR_ABOVE
from app.services.submission import (
    approve_submission, _mark_approved, reject_rating_submission,
    reject_artist_submission, reject_album_submission, reject_song_submission,
    get_artist_cascade_preview, get_album_cascade_preview, get_song_cascade_preview,
)
from app.cache import clear_stats_cache
from app.services.events import publish

submissions_bp = Blueprint('submissions', __name__)


def _bulk_resolve(submissions):
    """Batch-load all entities for a list of submissions to avoid N+1 queries."""
    artist_ids = {s.entity_id for s in submissions if s.type == 'artist'}
    album_ids = {s.entity_id for s in submissions if s.type == 'album'}
    song_ids = {s.entity_id for s in submissions if s.type in ('song', 'rating', 'note')}

    artists = {a.id: a for a in Artist.query.filter(Artist.id.in_(artist_ids)).all()} if artist_ids else {}
    albums = {a.id: a for a in Album.query.filter(Album.id.in_(album_ids)).all()} if album_ids else {}
    songs = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids)).all()} if song_ids else {}

    # Batch-load main artist links for songs
    all_song_ids = song_ids | {a.id for a in albums.values() if a.artist_id}
    song_artist_links = {}
    if song_ids:
        links = ArtistSong.query.filter(ArtistSong.song_id.in_(song_ids), ArtistSong.artist_is_main == True).all()
        for link in links:
            song_artist_links[link.song_id] = link.artist_id

    # Load artists referenced by songs/albums
    extra_artist_ids = set(song_artist_links.values()) | {a.artist_id for a in albums.values() if a.artist_id}
    extra_artist_ids -= set(artists.keys())
    if extra_artist_ids:
        for a in Artist.query.filter(Artist.id.in_(extra_artist_ids)).all():
            artists[a.id] = a

    return artists, albums, songs, song_artist_links


def _entity_name(sub, cache=None):
    """Resolve the display name for a submission's entity."""
    artists, albums, songs, song_artist_links = cache or ({}, {}, {}, {})
    fallback = sub.entity_name or f'{sub.type} {sub.entity_id}'
    if sub.type == 'artist':
        entity = artists.get(sub.entity_id)
        return entity.name if entity else fallback
    elif sub.type == 'album':
        entity = albums.get(sub.entity_id)
        return entity.name if entity else fallback
    elif sub.type == 'song':
        entity = songs.get(sub.entity_id)
        return entity.name if entity else fallback
    elif sub.type in ('rating', 'note'):
        entity = songs.get(sub.entity_id)
        song_name = entity.name if entity else fallback
        artist_ctx = ''
        if sub.artist_name:
            artist_ctx = f' ({sub.artist_name})'
        elif entity:
            artist_id = song_artist_links.get(entity.id)
            artist = artists.get(artist_id) if artist_id else None
            if artist:
                artist_ctx = f' ({artist.name})'
        return f'{song_name}{artist_ctx}'
    return fallback


def _entity_url(sub, cache=None):
    """Return a URL to the entity, or None if deleted."""
    artists, albums, songs, song_artist_links = cache or ({}, {}, {}, {})

    def _artist_slug_url(artist):
        if artist and artist.slug:
            return f'/artists/{artist.slug}'
        elif artist:
            return f'/artists/{artist.id}'
        return None

    if sub.type == 'artist':
        return _artist_slug_url(artists.get(sub.entity_id))
    elif sub.type == 'album':
        entity = albums.get(sub.entity_id)
        if entity and entity.artist_id:
            artist = artists.get(entity.artist_id)
            if artist and artist.slug:
                return f'/artists/{artist.slug}#album-{entity.id}'
    elif sub.type in ('song', 'rating', 'note'):
        entity = songs.get(sub.entity_id)
        if entity:
            artist_id = song_artist_links.get(entity.id)
            artist = artists.get(artist_id) if artist_id else None
            if artist and artist.slug:
                return f'/artists/{artist.slug}#song-{entity.id}'
    return None


def _resolve_artist_for_submission(sub, cache=None):
    """Return (artist_id, artist_name, artist_url) for a submission, or None."""
    artists, albums, songs, song_artist_links = cache or ({}, {}, {}, {})

    def _url(artist):
        return f'/artists/{artist.slug}' if artist.slug else f'/artists/{artist.id}'

    if sub.type == 'artist':
        artist = artists.get(sub.entity_id)
        if artist:
            return artist.id, artist.name, _url(artist)
    elif sub.type == 'album':
        album = albums.get(sub.entity_id)
        if album and album.artist_id:
            artist = artists.get(album.artist_id)
            if artist:
                return artist.id, artist.name, _url(artist)
    elif sub.type in ('song', 'rating', 'note'):
        song = songs.get(sub.entity_id)
        if song:
            artist_id = song_artist_links.get(song.id)
            artist = artists.get(artist_id) if artist_id else None
            if artist:
                return artist.id, artist.name, _url(artist)

    # Fallback to stored fields (entity deleted)
    if sub.artist_id and sub.artist_name:
        return -sub.artist_id, sub.artist_name, None

    return None


@submissions_bp.route('/submissions/for-me')
@login_required
@role_required(USER_OR_ABOVE)
def submissions_for_me():
    """For Me page — rating/note submissions targeting the current user."""
    status = request.args.get('status', 'open')
    type_filter = request.args.get('type', '')

    query = Submission.query.options(
        joinedload(Submission.submitted_by),
        joinedload(Submission.resolved_by),
    ).filter(
        Submission.type.in_(['rating', 'note']),
        Submission.target_user_id == current_user.id,
    )

    if status == 'open':
        query = query.filter_by(status='open')
    else:
        query = query.filter(Submission.status.in_(['approved', 'rejected']))

    if type_filter:
        query = query.filter_by(type=type_filter)

    if status == 'open':
        query = query.order_by(Submission.submitted_at.desc(), Submission.id.desc())
    else:
        query = query.order_by(Submission.resolved_at.desc(), Submission.id.desc())

    submissions = query.all()
    cache = _bulk_resolve(submissions)

    for sub in submissions:
        sub._entity_name = _entity_name(sub, cache)
        sub._entity_url = _entity_url(sub, cache)
        is_target = sub.target_user_id == current_user.id
        sub._can_approve = is_target
        sub._can_reject = is_target

    if request.headers.get('HX-Request'):
        return render_template('fragments/submissions_list.html',
                               groups=[], ungrouped=submissions, status=status)

    return render_template('submissions_for_me.html',
                           groups=[], ungrouped=submissions,
                           status=status, type_filter=type_filter)


@submissions_bp.route('/submissions')
@login_required
@role_required(EDITOR_OR_ADMIN)
def submissions_page():
    """Data Approvals page — entity submissions for editors/admins."""
    status = request.args.get('status', 'open')
    type_filter = request.args.get('type', '')
    search = request.args.get('q', '').strip()
    submitted_by = request.args.get('submitted_by', '')
    resolved_by = request.args.get('resolved_by', '')
    submitted_by = submitted_by if submitted_by.isdigit() else ''
    resolved_by = resolved_by if resolved_by.isdigit() else ''

    query = Submission.query.filter(
        Submission.type.in_(['artist', 'album', 'song']),
    ).options(
        joinedload(Submission.submitted_by),
        joinedload(Submission.resolved_by),
    )

    if status == 'open':
        query = query.filter_by(status='open')
    else:
        query = query.filter(Submission.status.in_(['approved', 'rejected']))

    if submitted_by:
        query = query.filter_by(submitted_by_id=int(submitted_by))
    if resolved_by:
        query = query.filter_by(resolved_by_id=int(resolved_by))

    if type_filter:
        query = query.filter_by(type=type_filter)

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Submission.entity_name.ilike(like),
                Submission.artist_name.ilike(like),
            )
        )

    if status == 'open':
        query = query.order_by(Submission.submitted_at.desc(), Submission.id.desc())
    else:
        query = query.order_by(Submission.resolved_at.desc(), Submission.id.desc())

    submissions = query.all()
    cache = _bulk_resolve(submissions)

    # Attach display info
    is_editor = current_user.is_editor_or_admin
    edit_mode = session.get('edit_mode', False)
    for sub in submissions:
        sub._entity_name = _entity_name(sub, cache)
        sub._entity_url = _entity_url(sub, cache)
        # Data Approvals: requires edit mode + editor/admin except submitter
        can_act = is_editor and edit_mode and (current_user.is_admin or sub.submitted_by_id != current_user.id)
        sub._can_approve = can_act
        sub._can_reject = can_act

    # Group by artist — only when showing all types or artist filter
    # When filtering by album or song, show a flat list instead
    groups = OrderedDict()
    ungrouped = []

    if type_filter in ('artist', 'album', 'song'):
        # Flat list when filtering by album or song
        ungrouped = list(submissions)
    else:
        # Group by artist
        song_subs = []
        for sub in submissions:
            if sub.type in ('rating', 'note'):
                ungrouped.append(sub)
                continue

            artist_info = _resolve_artist_for_submission(sub, cache)
            if not artist_info:
                ungrouped.append(sub)
                continue

            artist_id, artist_name, artist_url = artist_info
            if artist_id not in groups:
                groups[artist_id] = {
                    'artist_id': artist_id,
                    'artist_name': artist_name,
                    'artist_url': artist_url,
                    'artist_sub': None,
                    'children': [],
                }

            if sub.type == 'artist':
                groups[artist_id]['artist_sub'] = sub
            elif sub.type == 'album':
                groups[artist_id]['children'].append({
                    'album_sub': sub,
                    'songs': [],
                })
            elif sub.type == 'song':
                song_subs.append((sub, artist_id))

        # Second pass: attach songs to their album groups
        for sub, artist_id in song_subs:
            placed = False
            if artist_id in groups:
                song_obj = db.session.get(Song, sub.entity_id)
                if song_obj:
                    song_album_ids = {r.album_id for r in AlbumSong.query.filter_by(song_id=song_obj.id).all()}
                elif sub.album_id:
                    song_album_ids = {sub.album_id}
                else:
                    song_album_ids = set()

                for child in groups[artist_id]['children']:
                    if isinstance(child, dict) and child.get('album_sub') and child['album_sub'].entity_id in song_album_ids:
                        child['songs'].append(sub)
                        placed = True
                        break
            if not placed:
                if artist_id in groups:
                    groups[artist_id]['children'].append(sub)
                else:
                    ungrouped.append(sub)

        # Pre-compute row_sub and child_count for each group
        for group in groups.values():
            row_sub = group['artist_sub']
            if not row_sub:
                for child in group['children']:
                    if isinstance(child, dict):
                        row_sub = child['album_sub']
                    else:
                        row_sub = child
                    if row_sub:
                        break
            group['row_sub'] = row_sub

            child_count = 0
            for child in group['children']:
                if isinstance(child, dict):
                    child_count += 1 + len(child['songs'])
                else:
                    child_count += 1
            group['child_count'] = child_count

    if request.headers.get('HX-Request'):
        return render_template('fragments/submissions_list.html',
                               groups=list(groups.values()), ungrouped=ungrouped,
                               status=status)

    # Get users for filter dropdowns
    from sqlalchemy import distinct
    user_ids = set()
    for r in db.session.query(distinct(Submission.submitted_by_id)).all():
        if r[0]:
            user_ids.add(r[0])
    for r in db.session.query(distinct(Submission.resolved_by_id)).all():
        if r[0]:
            user_ids.add(r[0])
    filter_users = User.query.filter(User.id.in_(user_ids)).order_by(User.username).all() if user_ids else []

    return render_template('submissions.html',
                           groups=list(groups.values()), ungrouped=ungrouped,
                           status=status, type_filter=type_filter, search=search,
                           submitted_by=submitted_by, resolved_by=resolved_by,
                           filter_users=filter_users)


@submissions_bp.route('/submissions/<int:sub_id>/approve-preview')
@login_required
@role_required(EDITOR_OR_ADMIN)
def approve_preview(sub_id):
    """Return related open submissions that can be bulk-approved."""
    sub = db.session.get(Submission, sub_id)
    if not sub or sub.status != 'open':
        abort(404)

    related = _get_related_open_submissions(sub)
    if not related:
        return jsonify(related=[])

    result = []
    for r in related:
        entity = None
        item = {'id': r.id, 'type': r.type}
        if r.type == 'album':
            entity = db.session.get(Album, r.entity_id)
            item['name'] = entity.name if entity else f'album {r.entity_id}'
            item['entity_id'] = r.entity_id
        elif r.type == 'song':
            entity = db.session.get(Song, r.entity_id)
            item['name'] = entity.name if entity else f'song {r.entity_id}'
            item['album_id'] = r.album_id
        else:
            item['name'] = f'{r.type} {r.entity_id}'
        result.append(item)
    return jsonify(related=result)


def _get_related_open_submissions(sub):
    """Find open album/song submissions related to an artist or album submission."""
    from app.models.music import AlbumSong, ArtistSong

    if sub.type == 'artist':
        # Find open album submissions for albums owned by this artist
        album_ids = [a.id for a in Album.query.filter_by(artist_id=sub.entity_id).all()]
        # Find open song submissions for songs linked to this artist
        song_ids = [link.song_id for link in ArtistSong.query.filter_by(artist_id=sub.entity_id).all()]

        related = Submission.query.filter(
            Submission.status == 'open',
            Submission.id != sub.id,
            db.or_(
                db.and_(Submission.type == 'album', Submission.entity_id.in_(album_ids)) if album_ids else db.literal(False),
                db.and_(Submission.type == 'song', Submission.entity_id.in_(song_ids)) if song_ids else db.literal(False),
            )
        ).order_by(Submission.type, Submission.id).all()
        return related

    elif sub.type == 'album':
        # Find open song submissions for songs in this album
        song_ids = [als.song_id for als in AlbumSong.query.filter_by(album_id=sub.entity_id).all()]
        if not song_ids:
            return []

        related = Submission.query.filter(
            Submission.status == 'open',
            Submission.id != sub.id,
            Submission.type == 'song',
            Submission.entity_id.in_(song_ids),
        ).order_by(Submission.id).all()
        return related

    return []


@submissions_bp.route('/submissions/<int:sub_id>/approve', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def approve(sub_id):
    sub = db.session.get(Submission, sub_id)
    if not sub or sub.status != 'open':
        abort(404)
    # Target user can always act on their own rating/note submissions
    # Editors need edit mode to act on Data Approvals
    is_target = sub.type in ('rating', 'note') and sub.target_user_id == current_user.id
    is_editor_allowed = current_user.is_editor_or_admin and session.get('edit_mode') and (current_user.is_admin or sub.submitted_by_id != current_user.id)
    if not is_target and not is_editor_allowed:
        abort(403)
    _mark_approved(sub, current_user)

    # Bulk-approve additional related submissions (validated against actual related set)
    # Only editors in edit mode can bulk-approve related items
    also_approve = request.form.getlist('also_approve')
    if also_approve and is_editor_allowed:
        allowed = {s.id for s in _get_related_open_submissions(sub)}
        for extra_id in also_approve:
            extra_id = int(extra_id)
            if extra_id in allowed:
                extra = db.session.get(Submission, extra_id)
                if extra and extra.status == 'open':
                    _mark_approved(extra, current_user)

    db.session.commit()
    publish('submission-update', {'action': 'approved', 'id': sub_id})
    return ''


@submissions_bp.route('/submissions/<int:sub_id>/reject', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def reject(sub_id):
    sub = db.session.get(Submission, sub_id)
    if not sub or sub.status != 'open':
        abort(404)
    # Target user can always act on their own rating/note submissions
    # Editors need edit mode to act on Data Approvals
    is_target = sub.type in ('rating', 'note') and sub.target_user_id == current_user.id
    is_editor_allowed = current_user.is_editor_or_admin and session.get('edit_mode') and (current_user.is_admin or sub.submitted_by_id != current_user.id)
    if not is_target and not is_editor_allowed:
            abort(403)

    reason = request.form.get('reason', '').strip()
    if not reason:
        return 'Rejection reason is required', 400

    if sub.type in ('rating', 'note'):
        reject_rating_submission(sub, current_user, reason)
    else:
        # Entity rejections require password
        password = request.form.get('password', '')
        if not password:
            return 'Password is required', 400
        from app.routes.auth import _check_password
        if not current_user.password or not _check_password(current_user.password, password):
            return 'Incorrect password', 403

        if sub.type == 'artist':
            reject_artist_submission(sub, current_user, reason)
        elif sub.type == 'album':
            reject_album_submission(sub, current_user, reason)
        elif sub.type == 'song':
            reject_song_submission(sub, current_user, reason)

    clear_stats_cache()
    publish('submission-update', {'action': 'rejected', 'id': sub_id})
    return ''


@submissions_bp.route('/submissions/<int:sub_id>/cascade-preview')
@login_required
@role_required(EDITOR_OR_ADMIN)
def cascade_preview(sub_id):
    """Return cascade preview data for entity rejection modal."""
    sub = db.session.get(Submission, sub_id)
    if not sub or sub.status != 'open':
        abort(404)

    if sub.type == 'artist':
        preview = get_artist_cascade_preview(sub.entity_id)
    elif sub.type == 'album':
        preview = get_album_cascade_preview(sub.entity_id)
    elif sub.type == 'song':
        preview = get_song_cascade_preview(sub.entity_id)
    else:
        abort(400)

    if not preview:
        return jsonify(error='Entity not found'), 404

    return render_template('fragments/submission_cascade.html',
                           submission=sub, preview=preview)
