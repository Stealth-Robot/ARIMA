import json
from datetime import datetime, timezone

from flask import request, abort, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Album, Song, Artist, ArtistSong, AlbumSong, Rating, album_genres
from app.services.audit import log_change
from app.services.submission import _close_orphaned_submissions
from app.decorators import role_required, EDITOR_OR_ADMIN

from app.routes.edit import edit_bp, _require_edit_mode, _get_filters, _verify_password


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


@edit_bp.route('/song/<int:song_id>/note', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_note(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    note = (request.form.get('value', '') or '').strip() or None
    old_note = song.note
    song.note = note
    if note and not old_note:
        log_change(current_user, f'Added note to "{song.name}"', song=song)
    elif not note and old_note:
        log_change(current_user, f'Removed note from "{song.name}"', song=song)
    elif note != old_note:
        log_change(current_user, f'Updated note on "{song.name}"', song=song)
    db.session.commit()
    return note or ''


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

    # Find the main artist of the target album (via its existing songs,
    # falling back to the album's direct artist_id for empty albums)
    target_artist_id = db.session.execute(db.text(
        'SELECT ars.artist_id FROM artist_song ars '
        'JOIN album_song als ON als.song_id = ars.song_id '
        'WHERE als.album_id = :aid AND ars.artist_is_main = 1 '
        'LIMIT 1'
    ), {'aid': new_album_id}).scalar()
    if target_artist_id is None:
        target_artist_id = db.session.execute(db.text(
            'SELECT artist_id FROM album WHERE id = :aid'
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
    # Resolve artist name: try album.artist_id first, fall back to song's main artist
    album_artist_name = None
    if album and album.artist:
        album_artist_name = album.artist.name
    elif album:
        artist_link = ArtistSong.query.filter_by(song_id=song_id, artist_is_main=True).first()
        if artist_link:
            from app.models.music import Artist
            artist_obj = db.session.get(Artist, artist_link.artist_id)
            if artist_obj:
                album_artist_name = artist_obj.name

    # Remove the album-song link
    db.session.delete(link)

    # Check if the song is still in any other album
    remaining_albums = AlbumSong.query.filter_by(song_id=song_id).count()
    if remaining_albums == 0:
        # Orphaned song — delete it and its associations
        ArtistSong.query.filter_by(song_id=song_id).delete()
        Rating.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()
        _close_orphaned_submissions('song', song_id, current_user)
        _close_orphaned_submissions('rating', song_id, current_user)
        log_change(current_user, f'Removed "{song_name_val}" from "{album_name_val}" (song deleted, was only album)', change_type='song')
    else:
        log_change(current_user, f'Removed "{song_name_val}" from "{album_name_val}"', change_type='song')

    # Clean up album if now empty
    remaining_songs = AlbumSong.query.filter_by(album_id=album_id).count()
    if remaining_songs == 0:
        delete_album = request.form.get('delete_album') == '1'
        album_obj = db.session.get(Album, album_id)
        if album_obj and delete_album:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
            db.session.query(Album).filter_by(id=album_id).delete()
            _close_orphaned_submissions('album', album_id, current_user)
            context = f' ({album_artist_name})' if album_artist_name else ''
            log_change(current_user, f'Deleted empty album "{album_name_val}"{context}', change_type='album')
        elif album_obj and not album_obj.artist_id and fallback_artist_id:
            # Ensure the empty album has an artist_id so it shows in the discography
            album_obj.artist_id = fallback_artist_id

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
    _close_orphaned_submissions('song', song_id, current_user)
    _close_orphaned_submissions('rating', song_id, current_user)

    # Clean up albums that are now empty (skip albums with direct artist_id link)
    for row in album_song_rows:
        remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
        if remaining == 0:
            album_obj = db.session.get(Album, row.album_id)
            if album_obj and album_obj.artist_id is None:
                db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                db.session.query(Album).filter_by(id=row.album_id).delete()
                _close_orphaned_submissions('album', row.album_id, current_user)

    log_change(current_user, f'Deleted "{song_name_val}" song', change_type='song')
    db.session.commit()

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


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
    artist_name_val = artist.name if artist else 'Unknown'
    db.session.delete(existing)
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Removed "{artist_name_val}" from "{song.name}" song', song=song)
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
    artist_name_val = artist.name if artist else 'Unknown'
    label = 'main' if existing.artist_is_main else 'featured'
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Changed "{artist_name_val}" to {label} on "{song.name}" song', song=song)
    db.session.commit()
    return json.dumps({'is_main': existing.artist_is_main}), 200, {'Content-Type': 'application/json'}


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
