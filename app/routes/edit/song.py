import json
from datetime import datetime, timezone

from flask import request, abort, redirect, url_for, jsonify
from flask_login import login_required, current_user

from sqlalchemy import and_, case, func, null, or_, select, text, union

from app.extensions import db
from app.models.music import Album, Song, Artist, ArtistSong, AlbumSong, Rating, SongMiscArtist, MiscArtist, album_genres, song_genres, SongAlias, AlbumAltName
from app.models.duplicate_display_override import DuplicateDisplayOverride
from app.models.not_duplicate import NotDuplicate
from app.services.audit import log_change
from app.services.events import publish
from app.services.proxy_change import close_orphaned_proxy_changes
from app.services.search import text_match, alias_field, native_roman_parts
from app.decorators import role_required, EDITOR_OR_ADMIN

from app.routes.edit import edit_bp, _require_edit_mode, _get_filters, _verify_password, _parse_id_list


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
    if name == old_name:
        return name
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
    song.is_remix = request.form.get('checked') == 'true'
    label = 'Marked' if song.is_remix else 'Unmarked'
    with db.session.no_autoflush:
        log_change(current_user, f'{label} "{song.name}" song as remix', song=song)
    db.session.commit()
    return '', 204


@edit_bp.route('/song/<int:song_id>/is-promoted', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_is_promoted(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.is_promoted = request.form.get('checked') == 'true'
    if not song.is_promoted:
        song.is_lead = False
    label = 'Marked' if song.is_promoted else 'Unmarked'
    with db.session.no_autoflush:
        log_change(current_user, f'{label} "{song.name}" song as promoted', song=song)
    db.session.commit()
    return '', 204


@edit_bp.route('/song/<int:song_id>/is-lead', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_is_lead(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.is_lead = not song.is_lead
    if song.is_lead:
        song.is_promoted = True
    label = 'Marked' if song.is_lead else 'Unmarked'
    with db.session.no_autoflush:
        log_change(current_user, f'{label} "{song.name}" song as lead track', song=song)
    db.session.commit()
    return json.dumps({'is_lead': song.is_lead, 'is_promoted': song.is_promoted}), 200, {'Content-Type': 'application/json'}


THEME_NAMES = {'op': 'Opening', 'ed': 'Ending', 'in': 'Insert'}


def parse_theme(theme_type, theme_number):
    """Validate a theme type/number pair from a form or JSON; abort(400) on bad input."""
    theme_type = (theme_type or '').strip() or None
    if theme_type is not None and theme_type not in THEME_NAMES:
        abort(400)
    if theme_type is None or theme_number in (None, ''):
        return theme_type, None
    try:
        number = int(theme_number)
    except (TypeError, ValueError):
        abort(400)
    if not 1 <= number <= 999:
        abort(400)
    return theme_type, number


@edit_bp.route('/song/<int:song_id>/theme', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_theme(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    theme_type, number = parse_theme(request.form.get('type'), request.form.get('number'))
    if (theme_type, number) == (song.theme_type, song.theme_number):
        return jsonify({'theme_type': song.theme_type or '', 'theme_number': song.theme_number})
    song.theme_type, song.theme_number = theme_type, number
    with db.session.no_autoflush:
        if theme_type:
            label = THEME_NAMES[theme_type] + (f' {number}' if number else '')
            log_change(current_user, f'Marked "{song.name}" song as {label}', song=song)
        else:
            log_change(current_user, f'Cleared theme song type on "{song.name}"', song=song)
    db.session.commit()
    return jsonify({'theme_type': song.theme_type or '', 'theme_number': song.theme_number})


@edit_bp.route('/song/<int:song_id>/is-cover', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_is_cover(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.is_cover = request.form.get('checked') == 'true'
    label = 'Marked' if song.is_cover else 'Unmarked'
    with db.session.no_autoflush:
        log_change(current_user, f'{label} "{song.name}" song as cover', song=song)
    db.session.commit()
    return '', 204


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


@edit_bp.route('/song/<int:song_id>/spotify-url', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_spotify_url(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    url = (request.form.get('value', '') or '').strip() or None
    if url and url.lower() == 'n/a':
        url = 'n/a'  # sentinel: song is not on Spotify
    elif url and not url.startswith('https://'):
        abort(400)
    old = song.spotify_url
    song.spotify_url = url
    if url == 'n/a' and old != 'n/a':
        log_change(current_user, f'Marked "{song.name}" as not on Spotify', song=song, change_type='link')
    elif url and url != 'n/a' and (not old or old == 'n/a'):
        log_change(current_user, f'Added Spotify link to "{song.name}"', song=song, change_type='link')
    elif not url and old:
        log_change(current_user, f'Removed Spotify link from "{song.name}"', song=song, change_type='link')
    elif url != old:
        log_change(current_user, f'Updated Spotify link on "{song.name}"', song=song, change_type='link')
    db.session.commit()
    return url or ''


@edit_bp.route('/song/<int:song_id>/youtube-url', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_youtube_url(song_id):
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    url = (request.form.get('value', '') or '').strip() or None
    if url and not url.startswith('https://'):
        abort(400)
    old = song.youtube_url
    song.youtube_url = url
    if url and not old:
        log_change(current_user, f'Added YouTube link to "{song.name}"', song=song, change_type='link')
    elif not url and old:
        log_change(current_user, f'Removed YouTube link from "{song.name}"', song=song, change_type='link')
    elif url != old:
        log_change(current_user, f'Updated YouTube link on "{song.name}"', song=song, change_type='link')
    db.session.commit()
    return url or ''


@edit_bp.route('/song/<int:song_id>/move-album', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_move_album(song_id):
    """Move a song to any album in the system (same-artist or cross-artist)."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    new_album_id = request.form.get('album_id', type=int)
    if new_album_id is None:
        abort(400)
    new_album = db.session.get(Album, new_album_id)
    if new_album is None:
        abort(400)
    # Edit mode moves the song off the one album row it was picked from, keeping its other albums.
    from_album_id = request.form.get('from_album_id', type=int)

    now = datetime.now(timezone.utc).isoformat()

    # Capture old album IDs and source artist IDs before the move
    old_album_ids = [r[0] for r in db.session.execute(
        db.text('SELECT album_id FROM album_song WHERE song_id = :sid'),
        {'sid': song_id}).fetchall()]
    if from_album_id is not None:
        if from_album_id not in old_album_ids:
            abort(400)
        old_album_ids = [from_album_id]
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
    for old_id in old_album_ids:
        db.session.execute(
            db.text('DELETE FROM album_song WHERE song_id = :sid AND album_id = :aid'),
            {'sid': song_id, 'aid': old_id})
    already_there = db.session.execute(db.text(
        'SELECT 1 FROM album_song WHERE album_id = :aid AND song_id = :sid'
    ), {'aid': new_album_id, 'sid': song_id}).first() is not None
    if not already_there:
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
        still_on_other_albums = db.session.execute(db.text(
            'SELECT 1 FROM album_song WHERE song_id = :sid AND album_id != :aid LIMIT 1'
        ), {'sid': song_id, 'aid': new_album_id}).first() is not None
        for src_id in ([] if still_on_other_albums else source_artist_ids):
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
    target_album_id = request.form.get('album_id', type=int)
    if target_album_id is None:
        abort(400)
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
        close_orphaned_proxy_changes(song_id, current_user)
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
            context = f' ({album_artist_name})' if album_artist_name else ''
            log_change(current_user, f'Deleted empty album "{album_name_val}"{context}', change_type='album')
        elif album_obj and not album_obj.artist_id and fallback_artist_id:
            # Ensure the empty album has an artist_id so it shows in the discography
            album_obj.artist_id = fallback_artist_id

    db.session.commit()
    if fallback_artist_id:
        publish('song-update', {'artist_id': fallback_artist_id})

    if fallback_artist_id:
        return redirect(url_for('artists.artist_detail', artist_id=fallback_artist_id))
    return redirect(request.referrer or url_for('home.home'))


@edit_bp.route('/song/<int:song_id>/split', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def split_song(song_id):
    """Clone a song and its ratings, then replace it in the given album."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    album_id = request.form.get('album_id', type=int)
    if not album_id:
        abort(400)
    link = AlbumSong.query.filter_by(song_id=song_id, album_id=album_id).first()
    if link is None:
        abort(404)

    # Create the clone
    clone = Song(
        name=song.name,
        is_promoted=song.is_promoted,
        is_remix=song.is_remix,
        is_cover=song.is_cover,
        note=song.note,
        spotify_url=song.spotify_url,
        youtube_url=song.youtube_url,
        submitted_by_id=current_user.id,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
    db.session.add(clone)
    db.session.flush()  # get clone.id

    # Copy artist links
    for artist_link in ArtistSong.query.filter_by(song_id=song_id).all():
        db.session.add(ArtistSong(
            artist_id=artist_link.artist_id,
            song_id=clone.id,
            artist_is_main=artist_link.artist_is_main,
        ))

    # Copy ratings and notes
    for r in Rating.query.filter_by(song_id=song_id).all():
        db.session.add(Rating(
            song_id=clone.id,
            user_id=r.user_id,
            rating=r.rating,
            note=r.note,
        ))

    # Copy misc artist links
    for ma_link in SongMiscArtist.query.filter_by(song_id=song_id).all():
        db.session.add(SongMiscArtist(
            song_id=clone.id,
            misc_artist_id=ma_link.misc_artist_id,
            artist_is_main=ma_link.artist_is_main,
        ))

    # Copy song-level genres
    for row in db.session.execute(
        song_genres.select().where(song_genres.c.song_id == song_id)
    ).fetchall():
        db.session.execute(song_genres.insert().values(song_id=clone.id, genre_id=row[1]))

    # Remove original from this album and attach clone
    track = link.track_number
    db.session.delete(link)
    db.session.flush()
    db.session.add(AlbumSong(album_id=album_id, song_id=clone.id, track_number=track))

    album = db.session.get(Album, album_id)
    album_name = album.name if album else '?'
    log_change(current_user, f'Split "{song.name}" in "{album_name}" into new song (id {clone.id})', song=clone)
    db.session.commit()

    return json.dumps({'ok': True, 'new_song_id': clone.id}), 200, {'Content-Type': 'application/json'}


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
    close_orphaned_proxy_changes(song_id, current_user)

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
        publish('song-update', {'artist_id': fallback_artist_id})

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
    # Don't allow removing the last artist (misc artists count toward this too)
    count = ArtistSong.query.filter_by(song_id=song_id).count()
    misc_count = SongMiscArtist.query.filter_by(song_id=song_id).count()
    if count + misc_count <= 1:
        return 'Cannot remove the only artist', 400
    existing = db.session.get(ArtistSong, (artist_id, song_id))
    if existing is None:
        abort(404)
    artist = db.session.get(Artist, artist_id)
    artist_name_val = artist.name if artist else 'Unknown'
    db.session.delete(existing)
    db.session.flush()
    # Ensure a main remains: if removal left no main, promote a remaining artist.
    remaining_real = ArtistSong.query.filter_by(song_id=song_id).all()
    remaining_misc = SongMiscArtist.query.filter_by(song_id=song_id).all()
    has_main = any(r.artist_is_main for r in remaining_real) or any(m.artist_is_main for m in remaining_misc)
    if not has_main and (remaining_real or remaining_misc):
        (remaining_real[0] if remaining_real else remaining_misc[0]).artist_is_main = True
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
    if existing.artist_is_main:
        other_mains = (ArtistSong.query.filter(
                ArtistSong.song_id == song_id, ArtistSong.artist_is_main == True,
                ArtistSong.artist_id != artist_id).count()
            + SongMiscArtist.query.filter_by(song_id=song_id, artist_is_main=True).count())
        if other_mains == 0:
            return 'A song must have at least one main artist', 400
    existing.artist_is_main = not existing.artist_is_main
    artist = db.session.get(Artist, artist_id)
    artist_name_val = artist.name if artist else 'Unknown'
    label = 'main' if existing.artist_is_main else 'featured'
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Changed "{artist_name_val}" to {label} on "{song.name}" song', song=song)
    db.session.commit()
    return json.dumps({'is_main': existing.artist_is_main}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/misc-artists/<int:misc_artist_id>/role', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_misc_artist_role(song_id, misc_artist_id):
    """Toggle a misc artist's role (main/featured) on a song."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    existing = db.session.get(SongMiscArtist, (song_id, misc_artist_id))
    if existing is None:
        abort(404)
    if existing.artist_is_main:
        other_mains = (SongMiscArtist.query.filter(
                SongMiscArtist.song_id == song_id, SongMiscArtist.artist_is_main == True,
                SongMiscArtist.misc_artist_id != misc_artist_id).count()
            + ArtistSong.query.filter_by(song_id=song_id, artist_is_main=True).count())
        if other_mains == 0:
            return 'A song must have at least one main artist', 400
    existing.artist_is_main = not existing.artist_is_main
    misc = db.session.get(MiscArtist, misc_artist_id)
    misc_name_val = misc.name if misc else 'Unknown'
    label = 'main' if existing.artist_is_main else 'featured'
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Changed "{misc_name_val}" to {label} on "{song.name}" song', song=song)
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
    country_ids, genre_ids = _get_filters()
    name_filter = text_match(song.name, Song.name, alias_field(Song.id, SongAlias.song_id, SongAlias.name), split_words=False)
    parts = native_roman_parts(song.name)
    if parts:
        # "踊 Odo" subsumes "踊" and "Odo", which the contains match above can't reach.
        name_filter = or_(name_filter, func.lower(func.trim(Song.name)).in_([p.lower() for p in parts]))
    query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        name_filter,
        Song.id != song_id,
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        query = query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id.in_(genre_ids))
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
    country_ids, genre_ids = _get_filters()
    query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        text_match(q, Song.name, alias_field(Song.id, SongAlias.song_id, SongAlias.name)),
        Song.id != song_id,
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        query = query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        query = query.join(album_genres, Album.id == album_genres.c.album_id).filter(album_genres.c.genre_id.in_(genre_ids))
    rows = query.distinct().all()
    results = [{'id': s.id, 'name': s.name, 'artist': a.name, 'album': al.name}
               for s, al, a in rows]
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:kept_id>/merge-preview/<int:absorbed_id>')
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_preview(kept_id, absorbed_id):
    _require_edit_mode()
    if kept_id == absorbed_id:
        abort(400)
    kept = db.session.get(Song, kept_id)
    absorbed = db.session.get(Song, absorbed_id)
    if kept is None or absorbed is None:
        abort(404)

    from app.models.user import User

    def _song_context(song):
        artist_link = ArtistSong.query.filter_by(song_id=song.id, artist_is_main=True).first()
        artist_name = Artist.query.get(artist_link.artist_id).name if artist_link else None
        album_link = AlbumSong.query.filter_by(song_id=song.id).first()
        album_name = Album.query.get(album_link.album_id).name if album_link else None
        return {
            'id': song.id, 'name': song.name,
            'is_promoted': song.is_promoted, 'is_lead': song.is_lead,
            'is_remix': song.is_remix, 'is_cover': song.is_cover,
            'spotify_url': song.spotify_url, 'youtube_url': song.youtube_url,
            'note': song.note, 'artist': artist_name, 'album': album_name,
        }

    kept_ratings = {r.user_id: r for r in Rating.query.filter_by(song_id=kept_id).all()}
    absorbed_ratings = {r.user_id: r for r in Rating.query.filter_by(song_id=absorbed_id).all()}
    all_user_ids = set(kept_ratings) | set(absorbed_ratings)
    users = {u.id: u.username for u in User.query.filter(User.id.in_(all_user_ids)).all()} if all_user_ids else {}

    ratings = []
    for uid in sorted(all_user_ids):
        kr = kept_ratings.get(uid)
        ar = absorbed_ratings.get(uid)
        ratings.append({
            'user_id': uid, 'username': users.get(uid, '?'),
            'kept_rating': kr.rating if kr else None,
            'kept_note': kr.note if kr else None,
            'absorbed_rating': ar.rating if ar else None,
            'absorbed_note': ar.note if ar else None,
        })

    return jsonify(kept=_song_context(kept), absorbed=_song_context(absorbed), ratings=ratings)


@edit_bp.route('/song/<int:kept_song_id>/merge', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_song(kept_song_id):
    """Merge an absorbed song into the kept song."""
    _require_edit_mode()
    kept = db.session.get(Song, kept_song_id)
    if kept is None:
        abort(404)

    data = request.get_json(silent=True) if request.is_json else None

    absorbed_song_id = (data or {}).get('absorbed_song_id') or request.form.get('absorbed_song_id', type=int)
    if absorbed_song_id is None:
        abort(400)
    try:
        absorbed_song_id = int(absorbed_song_id)
    except (TypeError, ValueError):
        abort(400)
    if absorbed_song_id == kept_song_id:
        return 'Cannot merge a song with itself', 400
    absorbed = db.session.get(Song, absorbed_song_id)
    if absorbed is None:
        return 'Absorbed song not found', 400

    overrides = {}
    if data:
        if 'name' in data:
            overrides['chosen_name'] = data['name']
        flags = {}
        for f in ('is_promoted', 'is_lead', 'is_remix', 'is_cover'):
            if f in data:
                flags[f] = bool(data[f])
        if flags:
            overrides['chosen_flags'] = flags
        urls = {}
        for f in ('spotify_url', 'youtube_url'):
            if f in data:
                urls[f] = data[f] or None
        if urls:
            overrides['chosen_urls'] = urls
        if 'note' in data:
            overrides['chosen_note'] = data['note'] or None
        if 'ratings' in data:
            overrides['chosen_ratings'] = data['ratings']

    perform_song_merge(kept, absorbed, **overrides)

    if data:
        return jsonify(ok=True)
    artist_link = ArtistSong.query.filter_by(song_id=kept_song_id).first()
    if artist_link:
        return redirect(url_for('artists.artist_detail', artist_id=artist_link.artist_id))
    return redirect(request.referrer or url_for('home.home'))


def perform_song_merge(kept, absorbed, *, chosen_name=None, chosen_flags=None,
                       chosen_urls=None, chosen_note=None, chosen_ratings=None):
    """Merge absorbed song into kept song: ratings, links, flags, then delete absorbed."""
    kept_song_id = kept.id
    absorbed_song_id = absorbed.id
    absorbed_name = absorbed.name

    # Step 1: Merge ratings
    kept_ratings = {r.user_id: r for r in Rating.query.filter_by(song_id=kept_song_id).all()}
    absorbed_ratings_list = Rating.query.filter_by(song_id=absorbed_song_id).all()
    absorbed_ratings = {r.user_id: r for r in absorbed_ratings_list}

    if chosen_ratings is not None:
        chosen_map = {int(cr['user_id']): cr for cr in chosen_ratings}
        all_uids = set(kept_ratings) | set(absorbed_ratings)
        for uid in all_uids:
            cr = chosen_map.get(uid)
            chosen_score = cr.get('rating') if cr else None
            chosen_note_val = cr.get('note') if cr else None
            if chosen_score is not None:
                chosen_score = int(chosen_score)
                if chosen_score < 0 or chosen_score > 5:
                    chosen_score = None
            kr = kept_ratings.get(uid)
            ar = absorbed_ratings.get(uid)
            if kr:
                kr.rating = chosen_score
                kr.note = chosen_note_val
            elif ar:
                db.session.execute(db.text(
                    'UPDATE rating SET song_id = :kept WHERE song_id = :absorbed AND user_id = :uid'
                ), {'kept': kept_song_id, 'absorbed': absorbed_song_id, 'uid': uid})
                db.session.flush()
                moved = Rating.query.filter_by(song_id=kept_song_id, user_id=uid).first()
                if moved:
                    moved.rating = chosen_score
                    moved.note = chosen_note_val
    else:
        for ar in absorbed_ratings_list:
            if ar.user_id not in kept_ratings:
                db.session.execute(db.text(
                    'UPDATE rating SET song_id = :kept WHERE song_id = :absorbed AND user_id = :uid'
                ), {'kept': kept_song_id, 'absorbed': absorbed_song_id, 'uid': ar.user_id})
            else:
                kr = kept_ratings[ar.user_id]
                if ar.note:
                    kr.note = f"{kr.note}\n{ar.note}" if kr.note else ar.note

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
            db.session.execute(db.text(
                'DELETE FROM album_song WHERE album_id = :aid AND song_id = :sid'
            ), {'aid': link.album_id, 'sid': absorbed_song_id})
            db.session.execute(db.text(
                'INSERT INTO album_song (album_id, song_id, track_number) VALUES (:aid, :sid, :tn)'
            ), {'aid': link.album_id, 'sid': kept_song_id, 'tn': link.track_number})

    # Step 2b: Merge misc artist links
    kept_misc_ids = {r[0] for r in db.session.execute(
        db.text('SELECT misc_artist_id FROM song_misc_artist WHERE song_id = :sid'),
        {'sid': kept_song_id}).fetchall()}
    for link in SongMiscArtist.query.filter_by(song_id=absorbed_song_id).all():
        if link.misc_artist_id not in kept_misc_ids:
            db.session.execute(db.text(
                'UPDATE song_misc_artist SET song_id = :kept WHERE misc_artist_id = :mid AND song_id = :absorbed'
            ), {'kept': kept_song_id, 'mid': link.misc_artist_id, 'absorbed': absorbed_song_id})

    # Step 2c: Merge song-level genres
    kept_genre_ids = {r[0] for r in db.session.execute(
        db.text('SELECT genre_id FROM song_genres WHERE song_id = :sid'),
        {'sid': kept_song_id}).fetchall()}
    absorbed_genre_ids = {r[0] for r in db.session.execute(
        db.text('SELECT genre_id FROM song_genres WHERE song_id = :sid'),
        {'sid': absorbed_song_id}).fetchall()}
    for gid in absorbed_genre_ids - kept_genre_ids:
        db.session.execute(db.text(
            'INSERT INTO song_genres (song_id, genre_id) VALUES (:sid, :gid)'
        ), {'sid': kept_song_id, 'gid': gid})

    # Step 3b: Carry over flags and links
    if chosen_flags is not None:
        for f in ('is_promoted', 'is_lead', 'is_remix', 'is_cover'):
            if f in chosen_flags:
                setattr(kept, f, chosen_flags[f])
    else:
        if absorbed.is_promoted:
            kept.is_promoted = True
        if absorbed.is_lead:
            kept.is_lead = True
        if absorbed.is_remix:
            kept.is_remix = True
        if absorbed.is_cover:
            kept.is_cover = True

    if chosen_urls is not None:
        if 'spotify_url' in chosen_urls:
            kept.spotify_url = chosen_urls['spotify_url']
        if 'youtube_url' in chosen_urls:
            kept.youtube_url = chosen_urls['youtube_url']
    else:
        if not kept.spotify_url and absorbed.spotify_url:
            kept.spotify_url = absorbed.spotify_url
        if not kept.youtube_url and absorbed.youtube_url:
            kept.youtube_url = absorbed.youtube_url

    if chosen_note is not None:
        kept.note = chosen_note or None
    else:
        if absorbed.note:
            kept.note = f"{kept.note}\n{absorbed.note}" if kept.note else absorbed.note

    # Step 3c: Transfer NotDuplicate pairs from absorbed to kept song
    lo, hi = min(absorbed_song_id, kept_song_id), max(absorbed_song_id, kept_song_id)
    NotDuplicate.query.filter_by(song_id_1=lo, song_id_2=hi).delete()
    for nd in NotDuplicate.query.filter(
        db.or_(NotDuplicate.song_id_1 == absorbed_song_id,
               NotDuplicate.song_id_2 == absorbed_song_id)
    ).all():
        other = nd.song_id_2 if nd.song_id_1 == absorbed_song_id else nd.song_id_1
        new_lo, new_hi = min(other, kept_song_id), max(other, kept_song_id)
        if not NotDuplicate.query.filter_by(song_id_1=new_lo, song_id_2=new_hi).first():
            db.session.add(NotDuplicate(song_id_1=new_lo, song_id_2=new_hi))
        db.session.delete(nd)

    # Step 3d: Clean up stale DuplicateDisplayOverrides
    final_album_ids = {r[0] for r in db.session.execute(
        db.text('SELECT album_id FROM album_song WHERE song_id = :sid'),
        {'sid': kept_song_id}).fetchall()}
    DuplicateDisplayOverride.query.filter(
        DuplicateDisplayOverride.song_id == kept_song_id,
        ~DuplicateDisplayOverride.preferred_album_id.in_(final_album_ids)
    ).delete(synchronize_session=False)

    # Step 3e: Repoint Song of the Day history so it survives the merge
    db.session.execute(db.text(
        'UPDATE song_of_day SET song_id = :kept WHERE song_id = :absorbed'
    ), {'kept': kept_song_id, 'absorbed': absorbed_song_id})

    # Step 4: Delete absorbed song and all remaining references
    Rating.query.filter_by(song_id=absorbed_song_id).delete()
    ArtistSong.query.filter_by(song_id=absorbed_song_id).delete()
    AlbumSong.query.filter_by(song_id=absorbed_song_id).delete()
    SongMiscArtist.query.filter_by(song_id=absorbed_song_id).delete()
    db.session.execute(db.text('DELETE FROM song_genres WHERE song_id = :sid'), {'sid': absorbed_song_id})
    db.session.query(Song).filter_by(id=absorbed_song_id).delete()

    # Step 5: Audit log (before renaming so both original names appear)
    kept.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user,
               f'Merged song "{absorbed_name}" (id={absorbed_song_id}) into "{kept.name}" (id={kept_song_id})',
               song=kept)

    if chosen_name and chosen_name != kept.name:
        kept.name = chosen_name

    db.session.commit()


@edit_bp.route('/song/<int:song_id>/duplicate-override', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def duplicate_override(song_id):
    """Set which album a duplicate song should be displayed under on an artist page."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    album_id = request.form.get('album_id', type=int)
    artist_id = request.form.get('artist_id', type=int)
    if album_id is None or artist_id is None:
        abort(400)
    override = db.session.get(DuplicateDisplayOverride, (song_id, artist_id))
    if override:
        override.preferred_album_id = album_id
    else:
        override = DuplicateDisplayOverride(song_id=song_id, artist_id=artist_id, preferred_album_id=album_id)
        db.session.add(override)
    db.session.commit()
    return '', 204


@edit_bp.route('/song/<int:song_id>/genres', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_genres_edit(song_id):
    """Set song-level genres. Expects genre_ids as comma-separated list."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    from app.models.lookups import Genre
    genre_ids = _parse_id_list(request.form.get('genre_ids', '').strip())
    current_ids = sorted([r[1] for r in db.session.execute(
        song_genres.select().where(song_genres.c.song_id == song_id)
    ).fetchall()])
    genres = Genre.query.filter(Genre.id.in_(genre_ids)).all() if genre_ids else []
    if len(genres) != len(genre_ids):
        abort(400)
    names = [g.genre for g in genres]
    if genre_ids == current_ids:
        return json.dumps(names), 200, {'Content-Type': 'application/json'}
    db.session.execute(song_genres.delete().where(song_genres.c.song_id == song_id))
    for gid in genre_ids:
        db.session.execute(song_genres.insert().values(song_id=song_id, genre_id=gid))
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Set genres of "{song.name}" song to {", ".join(names) or "none"}', song=song)
    db.session.commit()
    return json.dumps(names), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/aliases', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_aliases_edit(song_id):
    """Replace a song's alternative names.

    Aliases make songs findable by romanized/translated titles. Each alias may be
    tagged native_lang 'ja', 'ko', 'zh', 'rom', 'en', or 'other' to designate it the
    native Japanese/Korean/Chinese, romanized, English, or other name (at most one of
    each). Expects JSON: {"aliases": [{"name", "native_lang"}, ...]}.
    """
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    seen = set()
    aliases = []
    used_langs = set()
    for item in payload.get('aliases', []):
        name = (item.get('name') or '').strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        lang = (item.get('native_lang') or '').strip().lower() or None
        if lang not in (None, 'ja', 'ko', 'zh', 'rom', 'en', 'other'):
            abort(400)
        if lang is not None:
            # JP/KR/CN/Other are mutually exclusive, so they collapse to one group key.
            group = 'jkc' if lang in ('ja', 'ko', 'zh', 'other') else lang
            if group in used_langs:
                abort(400)
            used_langs.add(group)
        aliases.append((name, lang))

    def _key(rows):
        return sorted((n, l) for n, l in rows)
    current = _key((a.name, a.native_lang) for a in song.aliases)
    if current == _key(aliases):
        return json.dumps([{'name': n, 'native_lang': l} for n, l in aliases]), 200, {'Content-Type': 'application/json'}
    song.aliases = [SongAlias(name=n, native_lang=l) for n, l in aliases]
    song.last_updated = datetime.now(timezone.utc).isoformat()
    log_change(current_user, f'Updated alternative names for "{song.name}" song', song=song)
    db.session.commit()
    return json.dumps([{'name': n, 'native_lang': l} for n, l in aliases]), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/picker/albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def search_albums():
    """Search albums with artist info for move/add-to-album pickers."""
    _require_edit_mode()
    q = request.args.get('q', '').strip()
    exclude_id = request.args.get('exclude', type=int)
    match = text_match(q, Album.name, Artist.name,
                       alias_field(Album.id, AlbumAltName.album_id, AlbumAltName.name))
    via_songs = (select(Album.id, Album.name, Artist.name, Artist.id)
                 .join(AlbumSong, AlbumSong.album_id == Album.id)
                 .join(ArtistSong, and_(ArtistSong.song_id == AlbumSong.song_id,
                                        ArtistSong.artist_is_main == True))
                 .join(Artist, Artist.id == ArtistSong.artist_id)
                 .where(match))
    owned = (select(Album.id, Album.name, Artist.name, Artist.id)
             .join(Artist, Artist.id == Album.artist_id)
             .where(match))
    rows = db.session.execute(union(via_songs, owned).order_by(text('3, 2')).limit(50)).fetchall()
    results = [{'id': r[0], 'name': r[1], 'artist': r[2], 'artistId': r[3]}
               for r in rows if r[0] != exclude_id]
    return json.dumps(results), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/picker/songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def search_songs():
    """Search songs with artist and album info for merge/link pickers."""
    _require_edit_mode()
    q = request.args.get('q', '').strip()
    exclude_id = request.args.get('exclude', type=int)
    # Exact-name and same-artist matches for the kept song sort first so they survive the LIMIT.
    priority = []
    if exclude_id:
        kept = db.session.execute(
            select(Song.name, ArtistSong.artist_id)
            .join(ArtistSong, and_(ArtistSong.song_id == Song.id, ArtistSong.artist_is_main == True))
            .where(Song.id == exclude_id).limit(1)).fetchone()
        if kept:
            priority = [case((func.lower(Song.name) == func.lower(kept[0]), 0), else_=1),
                        case((Artist.id == kept[1], 0), else_=1)]
    song_alias = alias_field(Song.id, SongAlias.song_id, SongAlias.name)
    rows = db.session.execute(
        select(Song.id, Song.name, Artist.name, Artist.id, Album.name)
        .join(ArtistSong, and_(ArtistSong.song_id == Song.id, ArtistSong.artist_is_main == True))
        .join(Artist, Artist.id == ArtistSong.artist_id)
        .join(AlbumSong, AlbumSong.song_id == Song.id)
        .join(Album, Album.id == AlbumSong.album_id)
        .where(text_match(q, Song.name, Artist.name, song_alias))
        .order_by(*priority, Artist.name, Song.name)
        .limit(100)).fetchall()
    if request.args.get('include_misc') == '1':
        misc_names = (select(func.group_concat(MiscArtist.name, ', '))
                      .select_from(SongMiscArtist)
                      .join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id)
                      .where(SongMiscArtist.song_id == Song.id, SongMiscArtist.artist_is_main == True)
                      .scalar_subquery())
        misc_artist = alias_field(Song.id, SongMiscArtist.song_id, MiscArtist.name,
                                  MiscArtist.id == SongMiscArtist.misc_artist_id,
                                  SongMiscArtist.artist_is_main == True)
        rows = list(rows) + db.session.execute(
            select(Song.id, Song.name, misc_names, null(), func.min(Album.name))
            .outerjoin(AlbumSong, AlbumSong.song_id == Song.id)
            .outerjoin(Album, Album.id == AlbumSong.album_id)
            .where(Song.id.in_(select(SongMiscArtist.song_id).where(SongMiscArtist.artist_is_main == True)),
                   Song.id.not_in(select(ArtistSong.song_id).where(ArtistSong.artist_is_main == True)),
                   text_match(q, Song.name, song_alias, misc_artist))
            .group_by(Song.id).order_by(Song.name).limit(100)).fetchall()
    seen_ids = set()
    results = []
    for r in rows:
        if r[0] != exclude_id and r[0] not in seen_ids:
            seen_ids.add(r[0])
            results.append({'id': r[0], 'name': r[1], 'artist': r[2], 'artistId': r[3], 'album': r[4]})
    return json.dumps(results), 200, {'Content-Type': 'application/json'}
