from flask import Blueprint, request, session
from flask_login import login_required, current_user

from app.extensions import db

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile/settings', methods=['POST'])
@login_required
def update_settings():
    """Update user settings (filters, toggles). Used by navbar dropdowns and profile page."""
    country = request.form.get('country')
    genre = request.form.get('genre')

    # Convert "All" / empty to None
    country_id = int(country) if country and country != '' else None
    genre_id = int(genre) if genre and genre != '' else None

    if current_user.is_system_or_guest:
        # Guest: store in session only
        session['country'] = country_id
        session['genre'] = genre_id
    else:
        settings = current_user.settings
        if settings:
            if 'country' in request.form:
                settings.country = country_id
            if 'genre' in request.form:
                settings.genre = genre_id
            db.session.commit()

    # Return empty 200 — HTMX will re-fetch the page content separately
    return '', 200
