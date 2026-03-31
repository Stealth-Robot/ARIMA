import json

from flask import Blueprint, request, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.models.music import Artist, Album, Song
from app.models.submission import Submission
from app.services.submission import create_submission, approve_submission, reject_submission
from app.decorators import role_required, USER_OR_ABOVE, EDITOR_OR_ADMIN

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


@submissions_bp.route('/submissions')
@login_required
@role_required(EDITOR_OR_ADMIN)
def submissions_list():
    """List pending submissions for review."""
    search = request.args.get('q', '').strip()
    query = Submission.query.filter(Submission.status == 'pending')
    if search:
        # Search by submitted_by username or by artist/album/song names in the submission
        sub_ids_artist = {a.submission_id for a in Artist.query.filter(Artist.name.ilike(f'%{search}%')).all()}
        sub_ids_album = {a.submission_id for a in Album.query.filter(Album.name.ilike(f'%{search}%')).all()}
        sub_ids_song = {s.submission_id for s in Song.query.filter(Song.name.ilike(f'%{search}%')).all()}
        matching_ids = sub_ids_artist | sub_ids_album | sub_ids_song
        if matching_ids:
            query = query.filter(Submission.id.in_(matching_ids))
        else:
            query = query.filter(False)  # no results

    subs = query.order_by(Submission.submitted_at.desc()).all()

    # Build detail data for each submission
    submissions_data = []
    for sub in subs:
        artists = Artist.query.filter_by(submission_id=sub.id).all()
        albums = Album.query.filter_by(submission_id=sub.id).all()
        songs = Song.query.filter_by(submission_id=sub.id).all()
        submissions_data.append({
            'submission': sub,
            'artists': artists,
            'albums': albums,
            'songs': songs,
        })

    return render_template('submissions.html', submissions=submissions_data, search=search)


@submissions_bp.route('/submissions/<int:sub_id>/approve', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def approve(sub_id):
    """Approve a submission with optional song rejections."""
    rejected_ids = request.form.getlist('reject_song_ids', type=int)
    result = approve_submission(sub_id, current_user,
                                rejected_song_ids=set(rejected_ids) if rejected_ids else None)
    if result is None:
        return 'Submission not found or already processed', 404

    if request.headers.get('HX-Request'):
        return render_template('fragments/submission_detail.html', sub=result)
    return redirect(url_for('submissions.submissions_list'))


@submissions_bp.route('/submissions/<int:sub_id>/reject', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def reject(sub_id):
    """Fully reject a submission."""
    reason = request.form.get('rejected_reason', '').strip()
    if not reason:
        return 'Rejection reason is required', 400

    result = reject_submission(sub_id, current_user, reason)
    if result is None:
        return 'Submission not found or already processed', 404

    if request.headers.get('HX-Request'):
        return render_template('fragments/submission_detail.html', sub=result)
    return redirect(url_for('submissions.submissions_list'))
