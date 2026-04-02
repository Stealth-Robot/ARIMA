from flask import Blueprint, request, render_template, session
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.music import Rating, Song
from app.decorators import role_required, USER_OR_ABOVE
from app.services.events import publish
from app.services.audit import log_change

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

    if song_id is None:
        return 'Missing song_id', 400

    if rating_value is None and not note:
        return 'Missing rating or note', 400

    if rating_value is not None and (rating_value < 0 or rating_value > 5):
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
        if rating_value is not None:
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

    # Clean up zombie rows (no rating AND no note)
    if existing.rating is None and not existing.note:
        db.session.delete(existing)
        existing = None

    song_obj = db.session.get(Song, song_id)
    if song_obj:
        if rating_value is not None:
            log_change(current_user, f'Rated "{song_obj.name}" {rating_value}/5', song=song_obj)
        elif note_sent:
            log_change(current_user, f'Updated note on "{song_obj.name}"', song=song_obj)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return 'Invalid song or user', 400

    publish('rating-update', {'song_id': song_id, 'user_id': target_user_id})

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
        song_obj = db.session.get(Song, song_id)
        if song_obj:
            log_change(current_user, f'Cleared rating for "{song_obj.name}"', song=song_obj)
        db.session.delete(existing)
        db.session.commit()
        publish('rating-update', {'song_id': song_id, 'user_id': target_user_id})

    return render_template('fragments/rating_cell.html',
                           rating=None, song_id=song_id, user_id=target_user_id)


@ratings_bp.route('/rate/cell')
@login_required
def get_rating_cell():
    """Return a single rating cell fragment (for SSE-triggered refresh)."""
    song_id = request.args.get('song_id', type=int)
    user_id = request.args.get('user_id', type=int)
    if song_id is None or user_id is None:
        return '', 400
    rating = db.session.get(Rating, (song_id, user_id))
    return render_template('fragments/rating_cell.html',
                           rating=rating, song_id=song_id, user_id=user_id)
