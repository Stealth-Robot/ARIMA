from flask import Blueprint, request, render_template
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
    # Rating can come from form data or HX-Prompt header (inline prompt from artists page)
    rating_value = request.form.get('rating', type=int)
    if rating_value is None:
        prompt = request.headers.get('HX-Prompt', '').strip()
        if prompt.isdigit():
            rating_value = int(prompt)
    note = request.form.get('note', '').strip() or None

    if song_id is None or rating_value is None:
        return 'Missing song_id or rating', 400

    if rating_value < 0 or rating_value > 5:
        return 'Rating must be 0-5', 400

    # Upsert: get existing or create new
    existing = db.session.get(Rating, (song_id, current_user.id))

    if existing:
        existing.rating = rating_value
        existing.note = note
    else:
        existing = Rating(
            song_id=song_id,
            user_id=current_user.id,
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
                           rating=existing, song_id=song_id, user_id=current_user.id)


@ratings_bp.route('/rate/delete', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def delete_rating():
    """Remove a rating (set back to unrated). Returns empty rating_cell fragment."""
    song_id = request.form.get('song_id', type=int)

    if song_id is None:
        return 'Missing song_id', 400

    existing = db.session.get(Rating, (song_id, current_user.id))
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return render_template('fragments/rating_cell.html',
                           rating=None, song_id=song_id, user_id=current_user.id)
