import json

from flask import Blueprint, request, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.services.submission import create_submission
from app.decorators import role_required, USER_OR_ABOVE

submissions_bp = Blueprint('submissions', __name__)


@submissions_bp.route('/submit', methods=['GET'])
@login_required
@role_required(USER_OR_ABOVE)
def submit_form():
    """Show the content submission form."""
    artists = Artist.query.order_by(Artist.name).all()
    countries = Country.query.order_by(Country.id).all()
    genres = Genre.query.order_by(Genre.id).all()
    album_types = AlbumType.query.order_by(AlbumType.id).all()
    genders = GroupGender.query.order_by(GroupGender.id).all()

    return render_template('submit.html',
                           artists=artists, countries=countries, genres=genres,
                           album_types=album_types, genders=genders)


@submissions_bp.route('/submit', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def submit_content():
    """Process a content submission."""
    # Artist: existing or new
    artist_id = request.form.get('artist_id')
    if artist_id:
        artist_data = {'id': int(artist_id)}
    else:
        artist_data = {
            'name': request.form.get('artist_name', '').strip(),
            'gender_id': int(request.form.get('gender_id', 0)),
            'country_id': int(request.form.get('country_id', 0)),
        }
        if not artist_data['name']:
            return 'Artist name is required', 400

    # Parse albums from form
    # Form sends album data as JSON in a hidden field
    albums_json = request.form.get('albums_data', '[]')
    try:
        albums_data = json.loads(albums_json)
    except json.JSONDecodeError:
        return 'Invalid album data', 400

    if not albums_data:
        return 'At least one album is required', 400

    # Validate each album has songs
    for album in albums_data:
        if not album.get('name', '').strip():
            return 'Album name is required', 400
        if not album.get('songs'):
            return 'Each album must have at least one song', 400
        if not album.get('release_date'):
            return 'Album release date is required', 400

    submission = create_submission(current_user, artist_data, albums_data)

    return redirect(url_for('artists.artists_list'))
