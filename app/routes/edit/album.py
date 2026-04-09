import json
import re
from datetime import datetime, timezone

from flask import request, abort, jsonify, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Album, Song, Artist, ArtistSong, AlbumSong, Rating, album_genres
from app.models.lookups import Genre, AlbumType
from app.services.audit import log_change
from app.services.submission import create_submission, _close_orphaned_submissions
from app.decorators import role_required, EDITOR_OR_ADMIN

from app.routes.edit import edit_bp, _require_edit_mode, _get_filters, _verify_password


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
    if name == old_name:
        return name
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
    new_date = None if value == '' else value
    if new_date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', new_date):
        abort(400)
    if new_date == album.release_date:
        return value
    album.release_date = new_date
    log_change(current_user, f'Changed release date of "{album.name}" album to {value or "none"}', album=album)
    db.session.commit()
    return value


@edit_bp.route('/album/<int:album_id>/type', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def album_type(album_id):
    _require_edit_mode()
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    type_id = request.form.get('album_type_id', '').strip()
    if not type_id:
        abort(400)
    type_id = int(type_id)
    album_type = db.session.get(AlbumType, type_id)
    if album_type is None:
        abort(400)
    if type_id == album.album_type_id:
        return jsonify(id=album_type.id, type=album_type.type)
    album.album_type_id = type_id
    album.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Changed type of "{album.name}" album to {album_type.type}', album=album)
    db.session.commit()
    return jsonify(id=album_type.id, type=album_type.type)


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
    genre_ids = sorted([int(x) for x in raw.split(',') if x.strip()]) if raw else []
    current_ids = sorted([r[1] for r in db.session.execute(
        album_genres.select().where(album_genres.c.album_id == album_id)
    ).fetchall()])
    names = [g.genre for g in Genre.query.filter(Genre.id.in_(genre_ids)).all()] if genre_ids else []
    if genre_ids == current_ids:
        return json.dumps(names), 200, {'Content-Type': 'application/json'}
    # Replace all genre associations
    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    for gid in genre_ids:
        db.session.execute(album_genres.insert().values(album_id=album_id, genre_id=gid))
    album.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Set genres of "{album.name}" album to {", ".join(names) or "none"}', album=album)
    db.session.commit()
    return json.dumps(names), 200, {'Content-Type': 'application/json'}


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

    album_name_val = data.get('name', '').strip()
    release_date = data.get('release_date', '').strip()
    album_type_id = data.get('album_type_id')
    genre_ids = data.get('genre_ids', [])
    songs = data.get('songs', [])

    if not album_name_val or album_type_id is None:
        abort(400)
    if release_date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', release_date):
        abort(400)
    if not genre_ids:
        abort(400)
    if not songs:
        abort(400)

    album = Album(
        name=album_name_val,
        release_date=release_date or None,
        album_type_id=int(album_type_id),
        submitted_by_id=current_user.id,
        artist_id=artist_id,
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
                spotify_url=song_data.get('spotify_url') or None,
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
        log_change(current_user, f'Added "{album_name_val}" album with {new_song_count} new and {existing_count} existing songs', artist=artist, album=album)
    else:
        log_change(current_user, f'Added "{album_name_val}" album with {len(songs)} songs', artist=artist, album=album)

    # Create submissions for the new album and its new songs
    create_submission('album', album.id, current_user.id)
    for als in AlbumSong.query.filter_by(album_id=album.id).all():
        song_obj = db.session.get(Song, als.song_id)
        if song_obj and song_obj.submitted_by_id == current_user.id:
            create_submission('song', song_obj.id, current_user.id)

    db.session.commit()

    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


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
    create_submission('song', song.id, current_user.id)
    db.session.commit()

    return json.dumps({'ok': True, 'song_id': song.id}), 200, {'Content-Type': 'application/json'}


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
    for sid in song_ids:
        other_albums = AlbumSong.query.filter(
            AlbumSong.song_id == sid, AlbumSong.album_id != album_id
        ).count()
        if other_albums == 0:
            songs_to_delete += 1
            ratings_to_delete += Rating.query.filter_by(song_id=sid).count()
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

    # Get all songs in this album
    song_ids = [r.song_id for r in AlbumSong.query.filter_by(album_id=album_id).all()]

    # Skip password for empty orphaned albums (no songs, no artist)
    is_orphan = not song_ids and album.artist_id is None
    if not is_orphan and not _verify_password():
        return 'Incorrect password', 403

    # Capture artist ID before deletions so we can redirect back
    fallback_artist_id = None
    if song_ids:
        artist_link = ArtistSong.query.filter(ArtistSong.song_id.in_(song_ids)).first()
        if artist_link:
            fallback_artist_id = artist_link.artist_id

    for sid in song_ids:
        AlbumSong.query.filter_by(album_id=album_id, song_id=sid).delete()
        # Only delete song if it's not in any other album
        other_albums = AlbumSong.query.filter_by(song_id=sid).count()
        if other_albums > 0:
            continue
        ArtistSong.query.filter_by(song_id=sid).delete()
        Rating.query.filter_by(song_id=sid).delete()
        db.session.query(Song).filter_by(id=sid).delete()
        _close_orphaned_submissions('song', sid, current_user)
        _close_orphaned_submissions(['rating', 'note'], sid, current_user)

    album_name_val = album.name
    # Resolve artist name: try album.artist_id first, fall back to song's main artist
    artist_name_val = None
    if album.artist:
        artist_name_val = album.artist.name
    elif song_ids:
        main_link = ArtistSong.query.filter(ArtistSong.song_id.in_(song_ids), ArtistSong.artist_is_main == True).first()
        if main_link:
            artist_obj = db.session.get(Artist, main_link.artist_id)
            if artist_obj:
                artist_name_val = artist_obj.name
    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    db.session.query(Album).filter_by(id=album_id).delete()
    _close_orphaned_submissions('album', album_id, current_user)
    context = f' ({artist_name_val})' if artist_name_val else ''
    log_change(current_user, f'Deleted "{album_name_val}" album{context} ({len(song_ids)} songs)', change_type='album')
    db.session.commit()

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


@edit_bp.route('/spotify-album')
@login_required
@role_required(EDITOR_OR_ADMIN)
def spotify_album():
    """Fetch album metadata from a Spotify URL for pre-filling the add-album form."""
    _require_edit_mode()
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    from app.services.spotify import fetch_album, SpotifyError
    try:
        data = fetch_album(url)
    except SpotifyError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(data)
