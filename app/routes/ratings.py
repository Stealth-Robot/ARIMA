from flask import Blueprint, request, render_template, session
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.music import Rating
from app.decorators import role_required, USER_OR_ABOVE

ratings_bp = Blueprint('ratings', __name__)


@ratings_bp.route('/rate', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def rate():
    """Create or update a rating. Returns a rating_cell fragment for HTMX swap."""
    song_id = request.form.get('song_id', type=int)
    rating_value = request.form.get('rating', type=int)
    note_raw = request.form.get('note')
    note_sent = note_raw is not None
    note = (note_raw.strip() or None) if note_sent else None

    if song_id is None or rating_value is None:
        return 'Missing song_id or rating', 400

    if rating_value < 0 or rating_value > 5:
        return 'Rating must be 0-5', 400

    # Determine target user — editors/admins can write for other users in edit mode
    target_user_id = current_user.id
    requested_user_id = request.form.get('user_id', type=int)
    if requested_user_id and requested_user_id != current_user.id:
        if current_user.is_editor_or_admin and session.get('edit_mode'):
            target_user_id = requested_user_id
        else:
            return 'Forbidden', 403

    # Upsert: get existing or create new
    existing = db.session.get(Rating, (song_id, target_user_id))

    if existing:
        existing.rating = rating_value
        if note_sent:
            existing.note = note
    else:
        existing = Rating(
            song_id=song_id,
            user_id=target_user_id,
            rating=rating_value,
            note=note,
        )
        db.session.add(existing)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return 'Invalid song or user', 400

    return render_template('fragments/rating_cell.html',
                           rating=existing, song_id=song_id, user_id=target_user_id)


@ratings_bp.route('/rate/delete', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def delete_rating():
    """Remove a rating (set back to unrated). Returns empty rating_cell fragment."""
    song_id = request.form.get('song_id', type=int)

    if song_id is None:
        return 'Missing song_id', 400

    # Determine target user — editors/admins can delete for other users in edit mode
    target_user_id = current_user.id
    requested_user_id = request.form.get('user_id', type=int)
    if requested_user_id and requested_user_id != current_user.id:
        if current_user.is_editor_or_admin and session.get('edit_mode'):
            target_user_id = requested_user_id
        else:
            return 'Forbidden', 403

    existing = db.session.get(Rating, (song_id, target_user_id))
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return render_template('fragments/rating_cell.html',
                           rating=None, song_id=song_id, user_id=target_user_id)
