import json
import re
from datetime import datetime, timezone

from flask import Blueprint, request, session, abort, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Album, Song, Artist, ArtistSong, AlbumSong, ArtistArtist, Rating, album_genres
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.services.artist import generate_unique_slug
from app.services.audit import log_change
from app.cache import clear_stats_cache
from app.decorators import role_required, ADMIN, EDITOR_OR_ADMIN


def _get_filters():
    """Return (country_id, genre_id) from user settings or session."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return current_user.settings.country, current_user.settings.genre
    return session.get('country'), session.get('genre')

edit_bp = Blueprint('edit', __name__, url_prefix='/edit')


@edit_bp.after_request
def _clear_stats_after_edit(response):
    """Clear stats cache after any successful edit operation."""
    if response.status_code < 400:
        clear_stats_cache()
    return response


@edit_bp.route('/artist/<int:artist_id>')
@login_required
def artist_redirect(artist_id):
    """Redirect /edit/artist/<id> to the artist detail page."""
    return redirect(url_for('artists.artist_detail', artist_id=artist_id))


def _require_edit_mode():
    if not session.get('edit_mode'):
        abort(403)


@edit_bp.route('/album/<int:album_id>/name', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_name(album_id):
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    name = request.form.get('value', '').strip()
    if not name:
        abort(400)
    old_name = album.name
    album.name = name
    log_change(current_user, f'Renamed "{old_name}" album to "{name}"', album=album)
    db.session.commit()
    return name


@edit_bp.route('/album/<int:album_id>/release-date', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_release_date(album_id):
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    value = request.form.get('value', '').strip()
    if value == '':
        album.release_date = None
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        album.release_date = value
    else:
        abort(400)
    log_change(current_user, f'Changed release date of "{album.name}" album to {value or "none"}', album=album)
    db.session.commit()
    return value


@edit_bp.route('/album/<int:album_id>/genres', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_genres_edit(album_id):
    """Set genres for an album. Expects genre_ids as comma-separated list."""
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    raw = request.form.get('genre_ids', '').strip()
    genre_ids = [int(x) for x in raw.split(',') if x.strip()] if raw else []
    # Replace all genre associations
    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    for gid in genre_ids:
        db.session.execute(album_genres.insert().values(album_id=album_id, genre_id=gid))
    names = [g.genre for g in Genre.query.filter(Genre.id.in_(genre_ids)).all()] if genre_ids else []
    album.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Set genres of "{album.name}" album to {", ".join(names) or "none"}', album=album)
    db.session.commit()
    return json.dumps(names), 200, {'Content-Type': 'application/json'}


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
    artist.name = name
    existing_slugs = {r[0] for r in db.session.query(Artist.slug).filter(Artist.id != artist_id).all()}
    artist.slug = generate_unique_slug(name, existing_slugs)
    log_change(current_user, f'Renamed "{old_name}" artist to "{name}"', artist=artist)
    db.session.commit()
    return name


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
    artist.is_complete = not artist.is_complete
    db.session.commit()
    return json.dumps({'is_complete': artist.is_complete}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/artist/<int:artist_id>/is-disbanded', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def artist_is_disbanded(artist_id):
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    artist.is_disbanded = not artist.is_disbanded
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
    artist.is_tracked = not artist.is_tracked
    db.session.commit()
    return json.dumps({'is_tracked': artist.is_tracked}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/move-album', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_move_album(song_id):
    """Move a song to any album in the system (same-artist or cross-artist)."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    new_album_id = request.form.get('album_id', '').strip()
    if not new_album_id:
        abort(400)
    new_album_id = int(new_album_id)
    new_album = db.session.get(Album, new_album_id)
    if new_album is None:
        abort(400)

    now = datetime.now(timezone.utc).isoformat()

    # Capture old album IDs and source artist IDs before the move
    old_album_ids = [r[0] for r in db.session.execute(
        db.text('SELECT album_id FROM album_song WHERE song_id = :sid'),
        {'sid': song_id}).fetchall()]
    source_artist_ids = {r[0] for r in db.session.execute(
        db.text('SELECT artist_id FROM artist_song WHERE song_id = :sid'),
        {'sid': song_id}).fetchall()}

    # Find the main artist of the target album (via its existing songs)
    target_artist_id = db.session.execute(db.text(
        'SELECT ars.artist_id FROM artist_song ars '
        'JOIN album_song als ON als.song_id = ars.song_id '
        'WHERE als.album_id = :aid AND ars.artist_is_main = 1 '
        'LIMIT 1'
    ), {'aid': new_album_id}).scalar()

    # Move the song: delete old album links, insert new one
    db.session.execute(
        db.text('DELETE FROM album_song WHERE song_id = :sid'),
        {'sid': song_id})
    next_track = (db.session.execute(db.text(
        'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
    ), {'aid': new_album_id}).scalar())
    db.session.execute(db.text(
        'INSERT INTO album_song (album_id, song_id, track_number) VALUES (:aid, :sid, :tn)'
    ), {'aid': new_album_id, 'sid': song_id, 'tn': next_track})

    # Cross-artist handling: update ArtistSong links
    if target_artist_id and target_artist_id not in source_artist_ids:
        # Add link to target artist as main
        db.session.execute(db.text(
            'INSERT OR IGNORE INTO artist_song (artist_id, song_id, artist_is_main) '
            'VALUES (:aid, :sid, 1)'
        ), {'aid': target_artist_id, 'sid': song_id})

        # Remove source artist links — the song now belongs to the target artist
        for src_id in source_artist_ids:
            if src_id != target_artist_id:
                db.session.execute(db.text(
                    'DELETE FROM artist_song WHERE artist_id = :aid AND song_id = :sid'
                ), {'aid': src_id, 'sid': song_id})

    # Clean up empty albums
    for old_id in old_album_ids:
        if old_id == new_album_id:
            continue
        is_empty = db.session.execute(db.text(
            'SELECT 1 FROM album_song WHERE album_id = :aid LIMIT 1'
        ), {'aid': old_id}).first() is None
        has_artist = db.session.execute(db.text(
            'SELECT 1 FROM album WHERE id = :aid AND artist_id IS NOT NULL'
        ), {'aid': old_id}).first() is not None
        if is_empty and not has_artist:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == old_id))
            db.session.execute(db.text('DELETE FROM album WHERE id = :aid'), {'aid': old_id})

    song.last_updated = now
    new_album.last_updated = now

    # Build audit message
    target_artist_name = ''
    if target_artist_id and target_artist_id not in source_artist_ids:
        target_artist_name = db.session.execute(
            db.text('SELECT name FROM artist WHERE id = :aid'),
            {'aid': target_artist_id}).scalar() or ''
    if target_artist_name:
        log_change(current_user,
                   f'Moved "{song.name}" song to "{new_album.name}" album ({target_artist_name})',
                   song=song, album=new_album)
    else:
        log_change(current_user,
                   f'Moved "{song.name}" song to "{new_album.name}" album',
                   song=song, album=new_album)
    db.session.commit()

    return json.dumps({'album_id': new_album.id, 'album_name': new_album.name}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/search-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def global_search_songs():
    """Search all songs in the database. Used by the Add Artist page."""
    _require_edit_mode()
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    country_id, genre_id = _get_filters()
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
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
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

    country_id, genre_id = _get_filters()
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
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
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

    country_id, genre_id = _get_filters()
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
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
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


@edit_bp.route('/artist/<int:artist_id>/add-album', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def add_album_to_artist(artist_id):
    """Add a new album with songs to an existing artist."""
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)

    try:
        data = json.loads(request.form.get('data', '{}'))
    except json.JSONDecodeError:
        abort(400)

    album_name = data.get('name', '').strip()
    release_date = data.get('release_date', '').strip()
    album_type_id = data.get('album_type_id')
    genre_ids = data.get('genre_ids', [])
    songs = data.get('songs', [])

    if not album_name or album_type_id is None:
        abort(400)
    if release_date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', release_date):
        abort(400)
    if not songs:
        abort(400)

    album = Album(
        name=album_name,
        release_date=release_date or None,
        album_type_id=int(album_type_id),
        submitted_by_id=current_user.id,
    )
    db.session.add(album)
    db.session.flush()

    for gid in genre_ids:
        db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=int(gid)))

    new_song_count = 0
    for track_num, song_data in enumerate(songs, 1):
        existing_song_id = song_data.get('existing_song_id')
        if existing_song_id:
            # Link an existing song to this album
            existing_song = db.session.get(Song, existing_song_id)
            if existing_song is None:
                abort(400)
            already = AlbumSong.query.filter_by(song_id=existing_song_id, album_id=album.id).first()
            if not already:
                db.session.add(AlbumSong(album_id=album.id, song_id=existing_song_id, track_number=track_num))
            # Ensure the current artist is linked to this song so the album appears in their discography
            artist_link = ArtistSong.query.filter_by(artist_id=artist_id, song_id=existing_song_id).first()
            if not artist_link:
                db.session.add(ArtistSong(artist_id=artist_id, song_id=existing_song_id, artist_is_main=False))
        else:
            # Create a new song
            new_song_count += 1
            song = Song(
                name=song_data['name'],
                submitted_by_id=current_user.id,
                is_promoted=song_data.get('is_promoted', False),
                is_remix=song_data.get('is_remix', False),
            )
            db.session.add(song)
            db.session.flush()

            db.session.add(AlbumSong(album_id=album.id, song_id=song.id, track_number=track_num))

            song_artists = song_data.get('artists')
            if song_artists:
                seen = set()
                for sa in song_artists:
                    sa_id = sa.get('artist_id') or artist_id
                    if sa_id in seen:
                        continue
                    seen.add(sa_id)
                    db.session.add(ArtistSong(artist_id=sa_id, song_id=song.id, artist_is_main=sa.get('is_main', True)))
            else:
                db.session.add(ArtistSong(artist_id=artist_id, song_id=song.id, artist_is_main=song_data.get('artist_is_main', True)))

    existing_count = len(songs) - new_song_count
    if existing_count:
        log_change(current_user, f'Added "{album_name}" album with {new_song_count} new and {existing_count} existing songs', artist=artist, album=album)
    else:
        log_change(current_user, f'Added "{album_name}" album with {len(songs)} songs', artist=artist, album=album)
    db.session.commit()

    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/name', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_name(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    name = request.form.get('value', '').strip()
    if not name:
        abort(400)
    old_name = song.name
    song.name = name
    log_change(current_user, f'Renamed "{old_name}" song to "{name}"', song=song)
    db.session.commit()
    return name


@edit_bp.route('/song/<int:song_id>/is-remix', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_is_remix(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.is_remix = not song.is_remix
    label = 'Marked' if song.is_remix else 'Unmarked'
    log_change(current_user, f'{label} "{song.name}" song as remix', song=song)
    db.session.commit()
    checked = 'checked' if song.is_remix else ''
    return f'<input type="checkbox" {checked} hx-post="/edit/song/{song_id}/is-remix" hx-trigger="change" hx-swap="outerHTML" hx-target="this">'


@edit_bp.route('/song/<int:song_id>/is-promoted', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_is_promoted(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.is_promoted = not song.is_promoted
    label = 'Marked' if song.is_promoted else 'Unmarked'
    log_change(current_user, f'{label} "{song.name}" song as promoted', song=song)
    db.session.commit()
    checked = 'checked' if song.is_promoted else ''
    return f'<input type="checkbox" {checked} onchange="updatePromotedStyle(this)" hx-post="/edit/song/{song_id}/is-promoted" hx-trigger="change" hx-swap="outerHTML" hx-target="this">'


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
    # Don't allow if already a child
    existing_link = ArtistArtist.query.filter_by(artist_2=artist_id).first()
    if existing_link:
        return 'Artist is already a subunit or soloist', 400
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


@edit_bp.route('/song/<int:song_id>/artists', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_artists_update(song_id):
    """Add an artist to a song. Expects artist_id and is_main."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    artist_id = request.form.get('artist_id', type=int)
    is_main = request.form.get('is_main', 'true') == 'true'
    if artist_id is None:
        abort(400)
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(400)
    existing = db.session.get(ArtistSong, (artist_id, song_id))
    if existing:
        return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}
    db.session.add(ArtistSong(artist_id=artist_id, song_id=song_id, artist_is_main=is_main))
    song.last_updated = datetime.now(timezone.utc).isoformat()
    label = 'main' if is_main else 'featured'
    log_change(current_user, f'Added "{artist.name}" as {label} artist on "{song.name}" song', song=song)
    db.session.commit()
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/artists/<int:artist_id>', methods=['DELETE'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_artist_remove(song_id, artist_id):
    """Remove an artist from a song."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    # Don't allow removing the last artist
    count = ArtistSong.query.filter_by(song_id=song_id).count()
    if count <= 1:
        return 'Cannot remove the only artist', 400
    existing = db.session.get(ArtistSong, (artist_id, song_id))
    if existing is None:
        abort(404)
    artist = db.session.get(Artist, artist_id)
    artist_name = artist.name if artist else 'Unknown'
    db.session.delete(existing)
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Removed "{artist_name}" from "{song.name}" song', song=song)
    db.session.commit()
    return '', 204


@edit_bp.route('/song/<int:song_id>/artists/<int:artist_id>/role', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_artist_role(song_id, artist_id):
    """Toggle an artist's role (main/featured) on a song."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    existing = db.session.get(ArtistSong, (artist_id, song_id))
    if existing is None:
        abort(404)
    existing.artist_is_main = not existing.artist_is_main
    artist = db.session.get(Artist, artist_id)
    artist_name = artist.name if artist else 'Unknown'
    label = 'main' if existing.artist_is_main else 'featured'
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Changed "{artist_name}" to {label} on "{song.name}" song', song=song)
    db.session.commit()
    return json.dumps({'is_main': existing.artist_is_main}), 200, {'Content-Type': 'application/json'}


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
    artists = Artist.query.order_by(Artist.name).all()
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
        for album in albums_data:
            if album.get('existing_album_id'):
                continue
            if not album.get('name', '').strip():
                errors['albums'] = 'Album name is required.'
                break
            if not album.get('songs'):
                errors['albums'] = 'Each album must have at least one song.'
                break
            if not album.get('genre_ids'):
                errors['albums'] = 'Each album needs at least one genre.'
                break
            release_date = album.get('release_date', '')
            if release_date == '':
                errors['albums'] = 'Album release date is required.'
                break
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', release_date):
                errors['albums'] = 'Release date must be in YYYY-MM-DD format.'
                break
            for song in album.get('songs', []):
                if song.get('existing_song_id'):
                    continue
                artists_list = song.get('artists', [])
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
        artists = Artist.query.order_by(Artist.name).all()
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

    # Generate unique slug
    existing_slugs = {a.slug for a in Artist.query.filter(Artist.slug.isnot(None)).all()}
    slug = generate_unique_slug(name, existing_slugs)

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
            # Link all songs from existing album to the new artist
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

        album = Album(
            name=album_data['name'],
            release_date=album_data.get('release_date') or None,
            album_type_id=album_data['album_type_id'],
            submitted_by_id=current_user.id,
        )
        db.session.add(album)
        db.session.flush()

        for gid in album_data.get('genre_ids', []):
            db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=gid))

        for track_num, song_data in enumerate(album_data.get('songs', []), 1):
            existing_song_id = song_data.get('existing_song_id')
            if existing_song_id:
                existing_song = db.session.get(Song, existing_song_id)
                if existing_song is None:
                    continue
                already = AlbumSong.query.filter_by(song_id=existing_song_id, album_id=album.id).first()
                if not already:
                    db.session.add(AlbumSong(album_id=album.id, song_id=existing_song_id, track_number=track_num))
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
            )
            db.session.add(song_obj)
            db.session.flush()
            total_songs += 1

            db.session.add(AlbumSong(album_id=album.id, song_id=song_obj.id, track_number=track_num))

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
    db.session.commit()

    return redirect(url_for('artists.artist_detail', artist_id=artist.id))


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

        # Clean up albums that are now empty (skip albums with direct artist_id link)
        for row in album_song_rows:
            remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
            if remaining == 0:
                album_obj = db.session.get(Album, row.album_id)
                if album_obj and album_obj.artist_id is None:
                    db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                    db.session.query(Album).filter_by(id=row.album_id).delete()

    # Delete artist relationships (subunits/soloists)
    ArtistArtist.query.filter(
        db.or_(ArtistArtist.artist_1 == artist_id, ArtistArtist.artist_2 == artist_id)
    ).delete(synchronize_session=False)

    # Log before deleting (artist FK will be gone after delete)
    artist_name = artist.name
    db.session.delete(artist)
    log_change(current_user, f'Deleted "{artist_name}" artist with {album_count} albums, {song_count} songs, {rating_count} ratings', change_type='artist')
    db.session.commit()

    return redirect(url_for('artists.artists_list'))


def _verify_password():
    """Check current user's password from form data. Returns True or False."""
    password = request.form.get('password', '')
    if not password:
        return False
    from app.routes.auth import _check_password
    if not current_user.password or not _check_password(current_user.password, password):
        return False
    return True


@edit_bp.route('/album/<int:album_id>/search-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_search_songs(album_id):
    """Search songs not already in this album. Returns JSON list."""
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    # Songs already in this album
    existing_ids = {r.song_id for r in AlbumSong.query.filter_by(album_id=album_id).all()}

    country_id, genre_id = _get_filters()
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
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
    rows = query.distinct().all()

    results = [{'id': s.id, 'name': s.name, 'artist': a.name, 'album': al.name}
               for s, al, a in rows if s.id not in existing_ids]
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/album/<int:album_id>/add-song', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_add_song(album_id):
    """Add an existing song to this album."""
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    song_id = request.form.get('song_id', '').strip()
    if not song_id:
        abort(400)
    song_id = int(song_id)
    song = db.session.get(Song, song_id)
    if song is None:
        abort(400)

    existing = AlbumSong.query.filter_by(song_id=song_id, album_id=album_id).first()
    if existing:
        return json.dumps({'error': 'Song is already in this album'}), 400, {'Content-Type': 'application/json'}

    next_track = db.session.execute(db.text(
        'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
    ), {'aid': album_id}).scalar()

    db.session.add(AlbumSong(album_id=album_id, song_id=song_id, track_number=next_track))

    # Ensure the viewing artist is linked to this song so it appears in their discography
    artist_id = request.form.get('artist_id', '').strip()
    if artist_id:
        artist_id = int(artist_id)
        artist_link = ArtistSong.query.filter_by(artist_id=artist_id, song_id=song_id).first()
        if not artist_link:
            db.session.add(ArtistSong(artist_id=artist_id, song_id=song_id, artist_is_main=False))

    log_change(current_user,
               f'Added "{song.name}" to "{album.name}" album',
               song=song, album=album)
    db.session.commit()

    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/album/<int:album_id>/create-song', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_create_song(album_id):
    """Create a brand-new song and add it to this album.

    Accepts JSON body: {name, artists: [{artist_id, is_main}], is_promoted, is_remix}
    """
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    artists = data.get('artists') or []
    if not name or not artists:
        abort(400)

    # Validate at least one main artist
    has_main = any(a.get('is_main') for a in artists)
    if not has_main:
        return json.dumps({'error': 'At least one main artist is required'}), 400, {'Content-Type': 'application/json'}

    song = Song(
        name=name,
        submitted_by_id=current_user.id,
        is_promoted=bool(data.get('is_promoted')),
        is_remix=bool(data.get('is_remix')),
    )
    db.session.add(song)
    db.session.flush()

    next_track = db.session.execute(db.text(
        'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
    ), {'aid': album_id}).scalar()

    db.session.add(AlbumSong(album_id=album_id, song_id=song.id, track_number=next_track))

    seen = set()
    for a in artists:
        aid = int(a['artist_id'])
        if aid in seen:
            continue
        seen.add(aid)
        db.session.add(ArtistSong(artist_id=aid, song_id=song.id, artist_is_main=bool(a.get('is_main'))))

    log_change(current_user,
               f'Created "{name}" song in "{album.name}" album',
               song=song, album=album)
    db.session.commit()

    return json.dumps({'ok': True, 'song_id': song.id}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/add-to-album', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def add_song_to_album(song_id):
    """Add a song to an additional album (creates a new AlbumSong link)."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    target_album_id = request.form.get('album_id', '').strip()
    if not target_album_id:
        abort(400)
    target_album_id = int(target_album_id)
    target_album = db.session.get(Album, target_album_id)
    if target_album is None:
        abort(400)

    # Check if already in this album
    existing = AlbumSong.query.filter_by(song_id=song_id, album_id=target_album_id).first()
    if existing:
        return json.dumps({'error': 'Song is already in this album'}), 400, {'Content-Type': 'application/json'}

    # Get next track number
    next_track = db.session.execute(db.text(
        'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
    ), {'aid': target_album_id}).scalar()

    db.session.add(AlbumSong(album_id=target_album_id, song_id=song_id, track_number=next_track))

    log_change(current_user,
               f'Added "{song.name}" to "{target_album.name}" album',
               song=song, album=target_album)
    db.session.commit()

    return json.dumps({'album_id': target_album.id, 'album_name': target_album.name}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/album/<int:album_id>/reorder-song', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def reorder_song(album_id):
    """Move a song up or down within an album."""
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    song_id = int(request.form.get('song_id', 0))
    direction = request.form.get('direction', '')
    if not song_id or direction not in ('up', 'down'):
        abort(400)

    # Get all songs in this album ordered by track_number
    links = AlbumSong.query.filter_by(album_id=album_id).order_by(AlbumSong.track_number).all()
    idx = next((i for i, l in enumerate(links) if l.song_id == song_id), None)
    if idx is None:
        abort(404)

    swap_idx = idx - 1 if direction == 'up' else idx + 1
    if swap_idx < 0 or swap_idx >= len(links):
        return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}

    # Swap track numbers via raw SQL to avoid unique constraint conflict
    tn_a, tn_b = links[idx].track_number, links[swap_idx].track_number
    sid_a, sid_b = links[idx].song_id, links[swap_idx].song_id
    db.session.expire_all()
    db.session.execute(db.text(
        'UPDATE album_song SET track_number = -1 WHERE album_id = :aid AND song_id = :sid'
    ), {'aid': album_id, 'sid': sid_a})
    db.session.execute(db.text(
        'UPDATE album_song SET track_number = :tn WHERE album_id = :aid AND song_id = :sid'
    ), {'aid': album_id, 'sid': sid_b, 'tn': tn_a})
    db.session.execute(db.text(
        'UPDATE album_song SET track_number = :tn WHERE album_id = :aid AND song_id = :sid'
    ), {'aid': album_id, 'sid': sid_a, 'tn': tn_b})
    db.session.commit()

    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/remove-from-album/<int:album_id>', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def remove_song_from_album(song_id, album_id):
    """Remove a song from an album. If it was the song's only album, delete the song too."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)

    link = AlbumSong.query.filter_by(song_id=song_id, album_id=album_id).first()
    if link is None:
        abort(404)

    # Capture artist for redirect before any deletions
    artist_link = ArtistSong.query.filter_by(song_id=song_id).first()
    fallback_artist_id = artist_link.artist_id if artist_link else None

    song_name_val = song.name
    album = db.session.get(Album, album_id)
    album_name_val = album.name if album else '?'

    # Remove the album-song link
    db.session.delete(link)

    # Check if the song is still in any other album
    remaining_albums = AlbumSong.query.filter_by(song_id=song_id).count()
    if remaining_albums == 0:
        # Orphaned song — delete it and its associations
        ArtistSong.query.filter_by(song_id=song_id).delete()
        Rating.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()
        log_change(current_user, f'Removed "{song_name_val}" from "{album_name_val}" (song deleted, was only album)', change_type='song')
    else:
        log_change(current_user, f'Removed "{song_name_val}" from "{album_name_val}"', change_type='song')

    # Clean up album if now empty (skip albums with direct artist_id link)
    remaining_songs = AlbumSong.query.filter_by(album_id=album_id).count()
    if remaining_songs == 0:
        album_obj = db.session.get(Album, album_id)
        if album_obj and album_obj.artist_id is None:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
            db.session.query(Album).filter_by(id=album_id).delete()

    db.session.commit()

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


@edit_bp.route('/song/<int:song_id>/delete', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def delete_song(song_id):
    """Delete a song and clean up empty albums."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    if not _verify_password():
        return 'Incorrect password', 403

    # Capture artist ID before deletions so we can redirect back
    artist_link = ArtistSong.query.filter_by(song_id=song_id).first()
    fallback_artist_id = artist_link.artist_id if artist_link else None

    # Get album links before deleting
    album_song_rows = AlbumSong.query.filter_by(song_id=song_id).all()

    song_name_val = song.name
    ArtistSong.query.filter_by(song_id=song_id).delete()
    Rating.query.filter_by(song_id=song_id).delete()
    AlbumSong.query.filter_by(song_id=song_id).delete()
    db.session.query(Song).filter_by(id=song_id).delete()

    # Clean up albums that are now empty (skip albums with direct artist_id link)
    for row in album_song_rows:
        remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
        if remaining == 0:
            album_obj = db.session.get(Album, row.album_id)
            if album_obj and album_obj.artist_id is None:
                db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                db.session.query(Album).filter_by(id=row.album_id).delete()

    log_change(current_user, f'Deleted "{song_name_val}" song', change_type='song')
    db.session.commit()

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


@edit_bp.route('/album/<int:album_id>/delete-info')
@login_required
@role_required(EDITOR_OR_ADMIN)
def delete_album_info(album_id):
    """Return counts of songs and ratings that would be deleted with this album."""
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    album_songs = AlbumSong.query.filter_by(album_id=album_id).all()
    song_ids = [r.song_id for r in album_songs]
    songs_to_delete = 0
    ratings_to_delete = 0
    for song_id in song_ids:
        other_albums = AlbumSong.query.filter(
            AlbumSong.song_id == song_id, AlbumSong.album_id != album_id
        ).count()
        if other_albums == 0:
            songs_to_delete += 1
            ratings_to_delete += Rating.query.filter_by(song_id=song_id).count()
    return jsonify(songs=len(song_ids), songs_deleted=songs_to_delete,
                   ratings_deleted=ratings_to_delete)


@edit_bp.route('/album/<int:album_id>/delete', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def delete_album(album_id):
    """Delete an album, its songs (unless shared), genres, and ratings."""
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    if not _verify_password():
        return 'Incorrect password', 403

    # Get all songs in this album
    song_ids = [r.song_id for r in AlbumSong.query.filter_by(album_id=album_id).all()]

    # Capture artist ID before deletions so we can redirect back
    fallback_artist_id = None
    if song_ids:
        artist_link = ArtistSong.query.filter(ArtistSong.song_id.in_(song_ids)).first()
        if artist_link:
            fallback_artist_id = artist_link.artist_id

    for song_id in song_ids:
        AlbumSong.query.filter_by(album_id=album_id, song_id=song_id).delete()
        # Only delete song if it's not in any other album
        other_albums = AlbumSong.query.filter_by(song_id=song_id).count()
        if other_albums > 0:
            continue
        ArtistSong.query.filter_by(song_id=song_id).delete()
        Rating.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()

    album_name_val = album.name
    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    db.session.query(Album).filter_by(id=album_id).delete()
    log_change(current_user, f'Deleted "{album_name_val}" album ({len(song_ids)} songs)', change_type='album')
    db.session.commit()

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


@edit_bp.route('/song/<int:song_id>/merge-candidates')
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_candidates(song_id):
    """Return songs matching the kept song's name (case-insensitive, exact or contains)."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    country_id, genre_id = _get_filters()
    like = f'%{song.name}%'
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
        Song.id != song_id,
        ArtistSong.artist_is_main == True,
    )
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
    rows = query.distinct().all()
    results = [{'id': s.id, 'name': s.name, 'artist': a.name, 'album': al.name}
               for s, al, a in rows]
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/merge-search')
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_search(song_id):
    """Search all songs in the database for merge candidates."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}
    country_id, genre_id = _get_filters()
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
        Song.id != song_id,
        ArtistSong.artist_is_main == True,
    )
    if country_id is not None:
        query = query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id == genre_id)
    rows = query.distinct().all()
    results = [{'id': s.id, 'name': s.name, 'artist': a.name, 'album': al.name}
               for s, al, a in rows]
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:kept_song_id>/merge', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_song(kept_song_id):
    """Merge an absorbed song into the kept song."""
    _require_edit_mode()
    kept = db.session.get(Song, kept_song_id)
    if kept is None:
        abort(404)

    absorbed_song_id = request.form.get('absorbed_song_id', type=int)
    if absorbed_song_id is None:
        abort(400)
    if absorbed_song_id == kept_song_id:
        return 'Cannot merge a song with itself', 400
    absorbed = db.session.get(Song, absorbed_song_id)
    if absorbed is None:
        return 'Absorbed song not found', 400

    if not _verify_password():
        return 'Incorrect password', 403

    absorbed_name = absorbed.name

    # Step 1: Merge ratings
    kept_ratings = {r.user_id: r for r in Rating.query.filter_by(song_id=kept_song_id).all()}
    absorbed_ratings = Rating.query.filter_by(song_id=absorbed_song_id).all()
    for ar in absorbed_ratings:
        if ar.user_id not in kept_ratings:
            # No conflict — move rating to kept song
            db.session.execute(db.text(
                'UPDATE rating SET song_id = :kept WHERE song_id = :absorbed AND user_id = :uid'
            ), {'kept': kept_song_id, 'absorbed': absorbed_song_id, 'uid': ar.user_id})
        # else: conflict — kept song's rating survives, absorbed rating will be deleted in step 4

    # Step 2: Merge artist links
    kept_artist_ids = {r[0] for r in db.session.execute(
        db.text('SELECT artist_id FROM artist_song WHERE song_id = :sid'),
        {'sid': kept_song_id}).fetchall()}
    absorbed_artist_links = ArtistSong.query.filter_by(song_id=absorbed_song_id).all()
    for link in absorbed_artist_links:
        if link.artist_id not in kept_artist_ids:
            db.session.execute(db.text(
                'UPDATE artist_song SET song_id = :kept WHERE artist_id = :aid AND song_id = :absorbed'
            ), {'kept': kept_song_id, 'aid': link.artist_id, 'absorbed': absorbed_song_id})

    # Step 3: Merge album links
    kept_album_ids = {r[0] for r in db.session.execute(
        db.text('SELECT album_id FROM album_song WHERE song_id = :sid'),
        {'sid': kept_song_id}).fetchall()}
    absorbed_album_links = AlbumSong.query.filter_by(song_id=absorbed_song_id).all()
    for link in absorbed_album_links:
        if link.album_id not in kept_album_ids:
            next_track = db.session.execute(db.text(
                'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
            ), {'aid': link.album_id}).scalar()
            db.session.execute(db.text(
                'INSERT INTO album_song (album_id, song_id, track_number) VALUES (:aid, :sid, :tn)'
            ), {'aid': link.album_id, 'sid': kept_song_id, 'tn': next_track})

    # Step 4: Delete absorbed song and all remaining references
    Rating.query.filter_by(song_id=absorbed_song_id).delete()
    ArtistSong.query.filter_by(song_id=absorbed_song_id).delete()
    AlbumSong.query.filter_by(song_id=absorbed_song_id).delete()
    db.session.query(Song).filter_by(id=absorbed_song_id).delete()

    # Step 5: Audit log
    kept.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user,
               f'Merged song "{absorbed_name}" (id={absorbed_song_id}) into "{kept.name}" (id={kept_song_id})',
               song=kept)
    db.session.commit()

    # Find the first artist linked to the kept song to redirect to their page
    artist_link = ArtistSong.query.filter_by(song_id=kept_song_id).first()
    if artist_link:
        return redirect(url_for('artists.artist_detail', artist_id=artist_link.artist_id))
    return redirect(request.referrer or url_for('home.home'))


