import json
import re
import time
import logging
from datetime import datetime, timezone

from flask import request, session, abort, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user

from sqlalchemy import func

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong, ArtistArtist, Rating, album_genres
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.services.artist import generate_unique_slug
from app.services.audit import log_change
from app.services.submission import create_submission, _close_orphaned_submissions
from app.decorators import role_required, ADMIN, EDITOR_OR_ADMIN

from app.routes.edit import edit_bp, _require_edit_mode, _get_filters, _verify_password

logger = logging.getLogger(__name__)


@edit_bp.route('/artist/<int:artist_id>/name', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_name(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    name = request.form.get('value', '').strip()
    if not name:
        abort(400)
    old_name = artist.name
    if name == old_name:
        return jsonify(name=name, slug=artist.slug)
    artist.name = name
    existing_slugs = {r[0] for r in db.session.query(Artist.slug).filter(Artist.id != artist_id).all()}
    artist.slug = generate_unique_slug(name, existing_slugs)
    log_change(current_user, f'Renamed "{old_name}" artist to "{name}"', artist=artist)
    db.session.commit()
    return jsonify(name=name, slug=artist.slug)


@edit_bp.route('/artist/<int:artist_id>/country', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_country(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    country_id = request.form.get('country_id', '').strip()
    if not country_id:
        abort(400)
    country = db.session.get(Country, int(country_id))
    if country is None:
        abort(400)
    if artist.country_id == country.id:
        return json.dumps({'id': country.id, 'country': country.country}), 200, {'Content-Type': 'application/json'}
    artist.country_id = country.id
    log_change(current_user, f'Changed country of "{artist.name}" artist to {country.country}', artist=artist)
    db.session.commit()
    return json.dumps({'id': country.id, 'country': country.country}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/gender', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_gender(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    gender_id = request.form.get('gender_id', '').strip()
    if not gender_id:
        abort(400)
    gender = db.session.get(GroupGender, int(gender_id))
    if gender is None:
        abort(400)
    if artist.gender_id == gender.id:
        return json.dumps({'id': gender.id, 'gender': gender.gender}), 200, {'Content-Type': 'application/json'}
    artist.gender_id = gender.id
    log_change(current_user, f'Changed gender of "{artist.name}" artist to {gender.gender}', artist=artist)
    db.session.commit()
    return json.dumps({'id': gender.id, 'gender': gender.gender}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/is-complete', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_is_complete(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    value = request.form.get('value')
    artist.is_complete = value == '1' if value is not None else not artist.is_complete
    if artist.is_complete:
        artist.owner_id = None
    db.session.commit()
    return json.dumps({
        'is_complete': artist.is_complete,
        'owner_id': artist.owner_id,
    }), 200, {'Content-Type': 'application/json'}


def _assignable_user_ids():
    """User IDs that can be assigned as Owner/Maintainer (raters+ only)."""
    from app.models.user import User
    return {u.id for u in User.query.filter(User.sort_order.isnot(None)).all()}


@edit_bp.route('/artist/<int:artist_id>/owner', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_owner(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    raw = request.form.get('user_id', '').strip()
    if raw == '':
        artist.owner_id = None
    else:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            abort(400)
        if user_id not in _assignable_user_ids():
            abort(400)
        if artist.is_complete:
            return json.dumps({'error': 'Artist is complete; owner cannot be set'}), 409, {'Content-Type': 'application/json'}
        artist.owner_id = user_id
    db.session.commit()
    return json.dumps({'owner_id': artist.owner_id}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/maintainer', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_maintainer(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    raw = request.form.get('user_id', '').strip()
    if raw == '':
        artist.maintainer_id = None
    else:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            abort(400)
        if user_id not in _assignable_user_ids():
            abort(400)
        artist.maintainer_id = user_id
    db.session.commit()
    return json.dumps({'maintainer_id': artist.maintainer_id}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/is-disbanded', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_is_disbanded(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    value = request.form.get('value')
    artist.is_disbanded = value == '1' if value is not None else not artist.is_disbanded
    db.session.commit()
    return json.dumps({'is_disbanded': artist.is_disbanded}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/is-tracked', methods=['POST'])
@login_required
@role_required(ADMIN)
def artist_is_tracked(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    value = request.form.get('value')
    artist.is_tracked = value == '1' if value is not None else not artist.is_tracked
    db.session.commit()
    return json.dumps({'is_tracked': artist.is_tracked}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/convert', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def convert_artist(artist_id):
    """Convert a standalone artist to a subunit or soloist of another artist."""
    _require_edit_mode()
    if not _verify_password():
        return 'Incorrect password', 403
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    parent_id = request.form.get('parent_id', type=int)
    rel_type = request.form.get('type', '').strip()
    if parent_id is None or rel_type not in ('subunit', 'soloist'):
        abort(400)
    parent = db.session.get(Artist, parent_id)
    if parent is None:
        abort(400)
    # Don't allow if artist already has children
    existing_children = ArtistArtist.query.filter_by(artist_1=artist_id).count()
    if existing_children > 0:
        return 'Artist has subunits or soloists', 400
    # Check existing relationships
    existing_links = ArtistArtist.query.filter_by(artist_2=artist_id).all()
    if rel_type == 'subunit':
        # Subunit: only one parent allowed, and can't be a soloist already
        if existing_links:
            return 'Artist is already a subunit or soloist', 400
    else:
        # Soloist: can have multiple parents, but can't be a subunit
        if any(link.relationship == 0 for link in existing_links):
            return 'Artist is already a subunit', 400
        if any(link.artist_1 == parent_id for link in existing_links):
            return 'Artist is already a soloist of this group', 400
    rel_id = 0 if rel_type == 'subunit' else 1
    db.session.add(ArtistArtist(artist_1=parent_id, artist_2=artist_id, relationship=rel_id))
    artist.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Converted "{artist.name}" to {rel_type} of "{parent.name}" artist', artist=artist)
    db.session.commit()
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/unlink', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def unlink_artist(artist_id):
    """Remove a subunit/soloist relationship, converting the child to a standalone artist."""
    _require_edit_mode()
    if not _verify_password():
        return 'Incorrect password', 403
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    parent_id = request.args.get('parent_id', type=int)
    if parent_id:
        link = ArtistArtist.query.filter_by(artist_2=artist_id, artist_1=parent_id).first()
    else:
        link = ArtistArtist.query.filter_by(artist_2=artist_id).first()
    if link is None:
        return redirect(url_for('artists.artist_detail', artist_id=artist_id))
    parent = db.session.get(Artist, link.artist_1)
    parent_name = parent.name if parent else 'Unknown'
    rel_type = 'soloist' if link.relationship == 1 else 'subunit'
    db.session.delete(link)
    artist.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Unlinked "{artist.name}" as {rel_type} from "{parent_name}" artist', artist=artist)
    db.session.commit()
    return redirect(url_for('artists.artist_detail', artist_id=artist_id))


@edit_bp.route('/artist/<int:artist_id>/delete', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def delete_artist(artist_id):
    """Delete an artist and all related data. Requires edit mode + password confirmation."""
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)

    # Verify password
    password = request.form.get('password', '')
    if not password:
        abort(400)
    from app.routes.auth import _check_password
    if not current_user.password or not _check_password(current_user.password, password):
        return '<script>alert("Incorrect password");history.back();</script>', 403

    # Collect counts before deleting
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist_id).all()}
    album_ids = {row.album_id for row in AlbumSong.query.filter(AlbumSong.song_id.in_(song_ids)).all()} if song_ids else set()
    rating_count = Rating.query.filter(Rating.song_id.in_(song_ids)).count() if song_ids else 0
    song_count = len(song_ids)
    album_count = len(album_ids)

    # Remove this artist's links; only delete songs that have no other artists
    for song_id in song_ids:
        ArtistSong.query.filter_by(artist_id=artist_id, song_id=song_id).delete()
        other_artists = ArtistSong.query.filter_by(song_id=song_id).count()
        if other_artists > 0:
            continue  # shared song — leave it for the other artist(s)

        Rating.query.filter_by(song_id=song_id).delete()
        album_song_rows = AlbumSong.query.filter_by(song_id=song_id).all()
        AlbumSong.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()
        _close_orphaned_submissions('song', song_id, current_user)
        _close_orphaned_submissions(['rating', 'note'], song_id, current_user)

        # Clean up albums that are now empty (skip albums with direct artist_id link)
        for row in album_song_rows:
            remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
            if remaining == 0:
                album_obj = db.session.get(Album, row.album_id)
                if album_obj and album_obj.artist_id is None:
                    db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                    db.session.query(Album).filter_by(id=row.album_id).delete()
                    _close_orphaned_submissions('album', row.album_id, current_user)

    # Close orphaned submissions for the artist itself
    _close_orphaned_submissions('artist', artist_id, current_user)

    # Delete artist relationships (subunits/soloists)
    ArtistArtist.query.filter(
        db.or_(ArtistArtist.artist_1 == artist_id, ArtistArtist.artist_2 == artist_id)
    ).delete(synchronize_session=False)

    # Log before deleting (artist FK will be gone after delete)
    artist_name_val = artist.name
    db.session.delete(artist)
    log_change(current_user, f'Deleted "{artist_name_val}" artist with {album_count} albums, {song_count} songs, {rating_count} ratings', change_type='artist')
    db.session.commit()

    return redirect(url_for('artists.artists_list'))


@edit_bp.route('/artist/<int:artist_id>/bulk-genres', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_bulk_genres(artist_id):
    """Bulk apply/remove/clear genres across all albums of a single artist.

    Scope is albums whose primary artist is artist_id. Child artists
    (subunits/soloists) are NOT included — a child has its own bulk button
    that calls this endpoint with the child's id.
    """
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)

    action = request.form.get('action', '').strip()
    if action not in ('apply', 'remove', 'clear'):
        abort(400, description='invalid action')

    raw = request.form.get('genre_ids', '').strip()
    requested_ids = sorted({int(x) for x in raw.split(',') if x.strip()}) if raw else []
    if action in ('apply', 'remove') and not requested_ids:
        abort(400, description='genre_ids required for apply/remove')

    song_ids = {r.song_id for r in ArtistSong.query.filter_by(artist_id=artist_id).all()}
    albums = []
    if song_ids:
        albums = Album.query.join(AlbumSong, Album.id == AlbumSong.album_id).filter(
            AlbumSong.song_id.in_(song_ids)
        ).distinct().all()
    seen = {a.id for a in albums}
    direct = Album.query.filter(
        Album.artist_id == artist_id,
        ~Album.id.in_(seen) if seen else db.true()
    ).all()
    albums.extend(direct)
    if not albums:
        return jsonify(affected=[])

    album_ids = [a.id for a in albums]
    rows = db.session.execute(
        album_genres.select().where(album_genres.c.album_id.in_(album_ids))
    ).fetchall()
    current = {aid: set() for aid in album_ids}
    for row in rows:
        current[row.album_id].add(row.genre_id)

    requested_set = set(requested_ids)
    affected = []
    for a in albums:
        before = current[a.id]
        if action == 'apply':
            to_add = requested_set - before
            if not to_add:
                continue
            for gid in to_add:
                db.session.execute(album_genres.insert().values(album_id=a.id, genre_id=gid))
            after = before | to_add
        elif action == 'remove':
            to_del = requested_set & before
            if not to_del:
                continue
            db.session.execute(
                album_genres.delete().where(
                    (album_genres.c.album_id == a.id)
                    & (album_genres.c.genre_id.in_(to_del))
                )
            )
            after = before - to_del
        else:  # clear
            if not before:
                continue
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == a.id))
            after = set()
        a.last_updated = datetime.now(timezone.utc).isoformat()
        affected.append((a, sorted(after)))

    if not affected:
        return jsonify(affected=[])

    all_gids = {gid for _, gids in affected for gid in gids} | requested_set
    name_by_id = {g.id: g.genre for g in Genre.query.filter(Genre.id.in_(all_gids)).all()}
    requested_names = [name_by_id[g] for g in requested_ids if g in name_by_id]

    n = len(affected)
    album_word = 'album' if n == 1 else 'albums'
    if action == 'apply':
        desc = f'Bulk-applied genres {", ".join(requested_names) or "(none)"} to {n} {album_word} of "{artist.name}"'
    elif action == 'remove':
        desc = f'Bulk-removed genres {", ".join(requested_names) or "(none)"} from {n} {album_word} of "{artist.name}"'
    else:
        desc = f'Bulk-cleared genres from {n} {album_word} of "{artist.name}"'
    log_change(current_user, desc, artist=artist)

    db.session.commit()

    return jsonify(affected=[
        {
            'album_id': a.id,
            'genre_ids': gids,
            'genre_names': [name_by_id[g] for g in gids if g in name_by_id],
        }
        for a, gids in affected
    ])


@edit_bp.route('/search-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def global_search_songs():
    """Search all songs in the database. Used by the Add Artist page."""
    _require_edit_mode()
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    country_ids, genre_ids = _get_filters()
    like = f'%{q}%'
    query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        Song.name.ilike(like),
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        query = query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id.in_(genre_ids))
    rows = query.distinct().all()

    seen = set()
    results = []
    for s, al, a in rows:
        if s.id in seen:
            continue
        seen.add(s.id)
        results.append({
            'id': s.id,
            'name': s.name,
            'artist': a.name,
            'album': al.name,
        })

    results.sort(key=lambda r: r['name'].lower())
    return json.dumps(results[:30]), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/search-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def global_search_albums():
    """Search all albums in the database. Used by the Add Artist page."""
    _require_edit_mode()
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    country_ids, genre_ids = _get_filters()
    like = f'%{q}%'
    query = db.session.query(Album, Artist).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        Album.name.ilike(like),
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        query = query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id.in_(genre_ids))
    rows = query.distinct().all()

    seen = set()
    results = []
    for al, a in rows:
        if al.id in seen:
            continue
        seen.add(al.id)
        song_count = AlbumSong.query.filter_by(album_id=al.id).count()
        results.append({
            'id': al.id,
            'name': al.name,
            'artist': a.name,
            'release_date': al.release_date or '',
            'song_count': song_count,
        })

    results.sort(key=lambda r: r['name'].lower())
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/search-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_search_songs(artist_id):
    """Search songs for adding to a new album. Current artist's songs first."""
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    country_ids, genre_ids = _get_filters()
    like = f'%{q}%'
    query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        Song.name.ilike(like),
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        query = query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id.in_(genre_ids))
    rows = query.distinct().all()

    # Deduplicate by song id, keeping first occurrence
    seen = set()
    results = []
    for s, al, a in rows:
        if s.id in seen:
            continue
        seen.add(s.id)
        results.append({
            'id': s.id,
            'name': s.name,
            'artist': a.name,
            'album': al.name,
            'is_current_artist': a.id == artist_id,
        })

    # Sort: current artist's songs first, then alphabetically
    results.sort(key=lambda r: (0 if r['is_current_artist'] else 1, r['name'].lower()))
    return json.dumps(results[:30]), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/add-artist', methods=['GET'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def add_artist_form():
    """Show the Add Artist form (edit mode only)."""
    if not session.get('edit_mode'):
        return redirect(url_for('artists.artists_list'))
    countries = Country.query.order_by(Country.id).all()
    genres = Genre.query.order_by(Genre.id).all()
    album_types = AlbumType.query.order_by(AlbumType.id).all()
    genders = GroupGender.query.order_by(GroupGender.id).all()
    artists = Artist.query.order_by(func.lower(Artist.name)).all()
    album_types_js = [{'id': t.id, 'type': t.type} for t in album_types]
    genres_js = [{'id': g.id, 'genre': g.genre} for g in genres]
    artists_js = [{'id': a.id, 'name': a.name} for a in artists]
    return render_template('add_artist.html',
                           countries=countries, genres=genres,
                           album_types=album_types, genders=genders,
                           artists=artists, errors={}, form_data={},
                           album_types_js=album_types_js, genres_js=genres_js,
                           artists_js=artists_js)


@edit_bp.route('/add-artist', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def add_artist_submit():
    """Process the Add Artist form (edit mode only)."""
    _require_edit_mode()

    errors = {}

    name = request.form.get('artist_name', '').strip()
    gender_id = request.form.get('gender_id', '').strip()
    country_id = request.form.get('country_id', '').strip()
    albums_json = request.form.get('albums_data', '[]')

    if not name:
        errors['artist_name'] = 'Name is required.'
    if not gender_id:
        errors['gender_id'] = 'Gender is required.'
    if not country_id:
        errors['country_id'] = 'Country is required.'

    try:
        albums_data = json.loads(albums_json)
    except json.JSONDecodeError:
        albums_data = []
        errors['albums'] = 'Invalid album data.'

    if not errors and not albums_data:
        errors['albums'] = 'At least one album is required.'

    if not errors:
        for album_data in albums_data:
            if album_data.get('existing_album_id'):
                continue
            if not album_data.get('name', '').strip():
                errors['albums'] = 'Album name is required.'
                break
            if not album_data.get('songs'):
                errors['albums'] = 'Each album must have at least one song.'
                break
            if not album_data.get('genre_ids'):
                errors['albums'] = 'Each album needs at least one genre.'
                break
            release_date = album_data.get('release_date', '')
            if release_date == '':
                errors['albums'] = 'Album release date is required.'
                break
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', release_date):
                errors['albums'] = 'Release date must be in YYYY-MM-DD format.'
                break
            for song_data in album_data.get('songs', []):
                if song_data.get('existing_song_id'):
                    continue
                artists_list = song_data.get('artists', [])
                if artists_list and not any(a.get('is_main') for a in artists_list):
                    errors['albums'] = 'Each song must have at least one main artist.'
                    break
            if errors:
                break

    if errors:
        countries = Country.query.order_by(Country.id).all()
        genres = Genre.query.order_by(Genre.id).all()
        album_types = AlbumType.query.order_by(AlbumType.id).all()
        genders = GroupGender.query.order_by(GroupGender.id).all()
        artists = Artist.query.order_by(func.lower(Artist.name)).all()
        album_types_js = [{'id': t.id, 'type': t.type} for t in album_types]
        genres_js = [{'id': g.id, 'genre': g.genre} for g in genres]
        artists_js = [{'id': a.id, 'name': a.name} for a in artists]
        form_data = {
            'artist_name': name,
            'gender_id': gender_id,
            'country_id': country_id,
            'is_disbanded': request.form.get('is_disbanded'),
            'is_complete': request.form.get('is_complete'),
            'is_tracked': request.form.get('is_tracked'),
            'albums_json': albums_json,
        }
        return render_template('add_artist.html',
                               countries=countries, genres=genres,
                               album_types=album_types, genders=genders,
                               artists=artists, errors=errors,
                               form_data=form_data,
                               album_types_js=album_types_js, genres_js=genres_js,
                               artists_js=artists_js), 422

    logger.info('add_artist_submit: creating "%s" with %d albums by user %s',
                name, len(albums_data), current_user.username)

    # Generate unique slug
    existing_slugs = {a.slug for a in Artist.query.filter(Artist.slug.isnot(None)).all()}
    slug = generate_unique_slug(name, existing_slugs)

    try:
        artist = Artist(
            name=name,
            gender_id=int(gender_id),
            country_id=int(country_id),
            slug=slug,
            submitted_by_id=current_user.id,
            is_disbanded=bool(request.form.get('is_disbanded')),
            is_complete=bool(request.form.get('is_complete')),
            is_tracked=bool(request.form.get('is_tracked')),
        )
        db.session.add(artist)
        db.session.flush()

        total_songs = 0
        for album_data in albums_data:
            existing_album_id = album_data.get('existing_album_id')
            if existing_album_id:
                existing_album = db.session.get(Album, existing_album_id)
                if existing_album is None:
                    continue
                album_songs = AlbumSong.query.filter_by(album_id=existing_album_id).all()
                for als in album_songs:
                    artist_link = ArtistSong.query.filter_by(artist_id=artist.id, song_id=als.song_id).first()
                    if not artist_link:
                        db.session.add(ArtistSong(artist_id=artist.id, song_id=als.song_id, artist_is_main=True))
                    total_songs += 1
                continue

            new_album = Album(
                name=album_data['name'],
                release_date=album_data.get('release_date') or None,
                album_type_id=album_data['album_type_id'],
                submitted_by_id=current_user.id,
                artist_id=artist.id,
            )
            db.session.add(new_album)
            db.session.flush()

            for gid in album_data.get('genre_ids', []):
                db.session.execute(album_genres.insert().values(album_id=new_album.id, genre_id=gid))

            for track_num, song_data in enumerate(album_data.get('songs', []), 1):
                existing_song_id = song_data.get('existing_song_id')
                if existing_song_id:
                    existing_song = db.session.get(Song, existing_song_id)
                    if existing_song is None:
                        continue
                    already = AlbumSong.query.filter_by(song_id=existing_song_id, album_id=new_album.id).first()
                    if not already:
                        db.session.add(AlbumSong(album_id=new_album.id, song_id=existing_song_id, track_number=track_num))
                    artist_link = ArtistSong.query.filter_by(artist_id=artist.id, song_id=existing_song_id).first()
                    if not artist_link:
                        db.session.add(ArtistSong(artist_id=artist.id, song_id=existing_song_id, artist_is_main=False))
                    total_songs += 1
                    continue

                song_obj = Song(
                    name=song_data['name'],
                    submitted_by_id=current_user.id,
                    is_promoted=song_data.get('is_promoted', False),
                    is_remix=song_data.get('is_remix', False),
                    spotify_url=song_data.get('spotify_url') or None,
                    youtube_url=song_data.get('youtube_url') or None,
                )
                db.session.add(song_obj)
                db.session.flush()
                total_songs += 1

                db.session.add(AlbumSong(album_id=new_album.id, song_id=song_obj.id, track_number=track_num))

                song_artists = song_data.get('artists')
                if song_artists:
                    seen = set()
                    for sa in song_artists:
                        sa_id = sa.get('artist_id') or artist.id
                        if sa_id in seen:
                            continue
                        seen.add(sa_id)
                        db.session.add(ArtistSong(artist_id=sa_id, song_id=song_obj.id, artist_is_main=sa.get('is_main', True)))
                else:
                    db.session.add(ArtistSong(artist_id=artist.id, song_id=song_obj.id, artist_is_main=song_data.get('artist_is_main', True)))

        log_change(current_user, f'Added "{name}" artist with {len(albums_data)} albums, {total_songs} songs', artist=artist)

        # Create submissions for the new artist, its albums, and new songs
        create_submission('artist', artist.id, current_user.id)
        for album_obj in Album.query.filter_by(artist_id=artist.id).all():
            create_submission('album', album_obj.id, current_user.id)
        seen_song_ids = set()
        for link in ArtistSong.query.filter_by(artist_id=artist.id).all():
            if link.song_id in seen_song_ids:
                continue
            seen_song_ids.add(link.song_id)
            song_obj = db.session.get(Song, link.song_id)
            if song_obj and song_obj.submitted_by_id == current_user.id:
                create_submission('song', song_obj.id, current_user.id)

        db.session.commit()
        logger.info('add_artist_submit: success — artist id=%d, %d albums, %d songs', artist.id, len(albums_data), total_songs)

        return redirect(url_for('artists.artist_detail', artist_id=artist.id))

    except Exception as e:
        db.session.rollback()
        logger.error('add_artist_submit: failed to create "%s" — %s', name, e, exc_info=True)
        errors['general'] = 'An unexpected error occurred. Please try again.'
        return render_template('add_artist.html',
                               errors=errors,
                               form_data={'artist_name': name, 'gender_id': gender_id,
                                          'country_id': country_id, 'albums_json': request.form.get('albums_data', '[]')},
                               genders=GroupGender.query.all(),
                               countries=Country.query.all(),
                               genres=Genre.query.all(),
                               artists=Artist.query.order_by(func.lower(Artist.name)).all()), 422


_import_jobs = {}
_import_cancels = {}
_JOB_TTL = 300  # 5 minutes


def _sweep_old_jobs():
    """Evict import jobs older than _JOB_TTL seconds."""
    now = time.time()
    stale = [k for k, v in _import_jobs.items() if now - v.get('_ts', 0) > _JOB_TTL]
    for k in stale:
        _import_jobs.pop(k, None)


@edit_bp.route('/spotify-artist', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def spotify_artist_start():
    """Start a Spotify artist import in the background."""
    if not session.get('edit_mode'):
        abort(403)
    url = request.form.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    from app.services.spotify import fetch_artist
    import uuid
    import threading

    _sweep_old_jobs()

    # Cancel any existing import for this user
    user_id = current_user.id
    old_cancel = _import_cancels.pop(user_id, None)
    if old_cancel:
        old_cancel.set()

    job_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    _import_cancels[user_id] = cancel
    _import_jobs[job_id] = {'progress': 'Connecting to Spotify...', 'percent': 0, '_ts': time.time()}

    def on_progress(msg, pct):
        _import_jobs[job_id] = {'progress': msg, 'percent': pct, '_ts': time.time()}

    def run():
        try:
            data = fetch_artist(url, on_progress=on_progress, cancel=cancel)
            if not data.get('albums'):
                _import_jobs[job_id] = {'error': f'No albums found for "{data.get("name", "artist")}". Spotify may have changed their API — try again or add albums manually.', '_ts': time.time()}
            else:
                _import_jobs[job_id] = {'done': True, 'data': data, '_ts': time.time()}
        except Exception as e:
            if not cancel.is_set():
                _import_jobs[job_id] = {'error': str(e) or 'Import failed unexpectedly', '_ts': time.time()}
        finally:
            _import_cancels.pop(user_id, None)
            if cancel.is_set():
                _import_jobs.pop(job_id, None)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'job_id': job_id})


@edit_bp.route('/spotify-artist/progress')
@login_required
@role_required(EDITOR_OR_ADMIN)
def spotify_artist_progress():
    """Poll progress of a Spotify artist import."""
    job_id = request.args.get('job_id', '')
    job = _import_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Unknown import job'}), 404
    return jsonify({k: v for k, v in job.items() if k != '_ts'})
