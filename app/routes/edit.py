import json
import re

from flask import Blueprint, request, session, abort, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Album, Song, Artist
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
    _require_edit_mode()
    countries = Country.query.order_by(Country.id).all()
    genres = Genre.query.order_by(Genre.id).all()
    album_types = AlbumType.query.order_by(AlbumType.id).all()
    genders = GroupGender.query.order_by(GroupGender.id).all()
    artists = Artist.query.order_by(Artist.name).all()
    album_types_js = [{'id': t.id, 'type': t.type} for t in album_types]
    genres_js = [{'id': g.id, 'genre': g.genre} for g in genres]
    return render_template('add_artist.html',
                           countries=countries, genres=genres,
                           album_types=album_types, genders=genders,
                           artists=artists, errors={}, form_data={},
                           album_types_js=album_types_js, genres_js=genres_js)


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
            if not album.get('release_date'):
                errors['albums'] = 'Album release date is required.'
                break

    if errors:
        countries = Country.query.order_by(Country.id).all()
        genres = Genre.query.order_by(Genre.id).all()
        album_types = AlbumType.query.order_by(AlbumType.id).all()
        genders = GroupGender.query.order_by(GroupGender.id).all()
        artists = Artist.query.order_by(Artist.name).all()
        album_types_js = [{'id': t.id, 'type': t.type} for t in album_types]
        genres_js = [{'id': g.id, 'genre': g.genre} for g in genres]
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
                               album_types_js=album_types_js, genres_js=genres_js), 422

    # Generate unique slug
    existing_slugs = {a.slug for a in Artist.query.filter(Artist.slug.isnot(None)).all()}
    slug = generate_unique_slug(name, existing_slugs)

    artist_data = {
        'name': name,
        'gender_id': int(gender_id),
        'country_id': int(country_id),
        'slug': slug,
    }

    submission = create_submission(current_user, artist_data, albums_data)

    # Find the newly created artist from this submission
    new_artist = Artist.query.filter_by(submission_id=submission.id).first()
    if new_artist and not new_artist.slug:
        new_artist.slug = slug
        db.session.commit()

    if new_artist:
        return redirect(url_for('artists.artist_detail', artist_slug=new_artist.slug or str(new_artist.id)))
    return redirect(url_for('artists.artists_list'))
