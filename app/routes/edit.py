import json
import re

from flask import Blueprint, request, session, abort, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Album, Song, Artist, ArtistSong, AlbumSong, ArtistArtist, Rating, album_genres
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.services.artist import generate_unique_slug
from app.services.submission import create_submission
from app.decorators import role_required, EDITOR_OR_ADMIN

edit_bp = Blueprint('edit', __name__, url_prefix='/edit')


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
    album.name = name
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
    db.session.commit()
    # Return updated genre names as JSON
    names = [g.genre for g in Genre.query.filter(Genre.id.in_(genre_ids)).all()] if genre_ids else []
    return json.dumps(names), 200, {'Content-Type': 'application/json'}


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
    db.session.commit()
    return json.dumps({'id': country.id, 'country': country.country}), 200, {'Content-Type': 'application/json'}


@edit_bp.route('/song/<int:song_id>/move-album', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def song_move_album(song_id):
    """Move a song from one album to another."""
    _require_edit_mode()
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    new_album_id = request.form.get('album_id', '').strip()
    if not new_album_id:
        abort(400)
    new_album = db.session.get(Album, int(new_album_id))
    if new_album is None:
        abort(400)

    # Remove from current album(s)
    old_album_ids = [r.album_id for r in AlbumSong.query.filter_by(song_id=song_id).all()]
    AlbumSong.query.filter_by(song_id=song_id).delete()

    # Append to end of new album
    max_track = db.session.query(db.func.max(AlbumSong.track_number)).filter_by(album_id=int(new_album_id)).scalar() or 0
    db.session.add(AlbumSong(album_id=int(new_album_id), song_id=song_id, track_number=max_track + 1))

    # Clean up albums that are now empty
    for old_id in old_album_ids:
        if old_id == int(new_album_id):
            continue
        remaining = AlbumSong.query.filter_by(album_id=old_id).count()
        if remaining == 0:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == old_id))
            db.session.query(Album).filter_by(id=old_id).delete()

    db.session.commit()

    return json.dumps({'album_id': new_album.id, 'album_name': new_album.name}), 200, {'Content-Type': 'application/json'}


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

    albums_data = [{
        'name': album_name,
        'release_date': release_date or None,
        'album_type_id': int(album_type_id),
        'genre_ids': [int(gid) for gid in genre_ids],
        'songs': songs,
    }]

    create_submission(current_user, {'id': artist_id}, albums_data)

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
    song.name = name
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
    db.session.commit()
    checked = 'checked' if song.is_promoted else ''
    return f'<input type="checkbox" {checked} onchange="updatePromotedStyle(this)" hx-post="/edit/song/{song_id}/is-promoted" hx-trigger="change" hx-swap="outerHTML" hx-target="this">'


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

    artist_data = {
        'name': name,
        'gender_id': int(gender_id),
        'country_id': int(country_id),
        'slug': slug,
    }

    create_submission(current_user, artist_data, albums_data)

    return redirect(url_for('artists.artist_detail', artist_slug=slug))


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

    # Collect all song IDs linked to this artist
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist_id).all()}

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

        # Clean up albums that are now empty
        for row in album_song_rows:
            remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
            if remaining == 0:
                db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                db.session.query(Album).filter_by(id=row.album_id).delete()

    # Delete artist relationships (subunits/soloists)
    ArtistArtist.query.filter(
        db.or_(ArtistArtist.artist_1 == artist_id, ArtistArtist.artist_2 == artist_id)
    ).delete(synchronize_session=False)

    # Delete the artist
    db.session.delete(artist)
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

    # Get album links before deleting
    album_song_rows = AlbumSong.query.filter_by(song_id=song_id).all()

    ArtistSong.query.filter_by(song_id=song_id).delete()
    Rating.query.filter_by(song_id=song_id).delete()
    AlbumSong.query.filter_by(song_id=song_id).delete()
    db.session.query(Song).filter_by(id=song_id).delete()

    # Clean up albums that are now empty
    for row in album_song_rows:
        remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
        if remaining == 0:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
            db.session.query(Album).filter_by(id=row.album_id).delete()

    db.session.commit()
    return '', 204


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

    for song_id in song_ids:
        AlbumSong.query.filter_by(album_id=album_id, song_id=song_id).delete()
        # Only delete song if it's not in any other album
        other_albums = AlbumSong.query.filter_by(song_id=song_id).count()
        if other_albums > 0:
            continue
        ArtistSong.query.filter_by(song_id=song_id).delete()
        Rating.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()

    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    db.session.query(Album).filter_by(id=album_id).delete()
    db.session.commit()
    return '', 204
