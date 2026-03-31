from flask import Blueprint, request, session, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.theme import Theme
from app.models.user import UserSettings

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
@login_required
def profile():
    """Profile page — user settings."""
    themes = Theme.query.order_by(Theme.id).all()
    # Build display names for themes
    theme_list = []
    for t in themes:
        if t.name:
            display = t.name
        elif t.owner:
            display = f"{t.owner.username}'s Theme"
        else:
            display = f'Theme #{t.id}'
        theme_list.append({'id': t.id, 'name': display})

    # Current settings
    if current_user.is_system_or_guest:
        settings = {
            'theme': session.get('theme', 0),
            'include_featured': session.get('include_featured', False),
            'include_remixes': session.get('include_remixes', False),
        }
    else:
        s = current_user.settings
        settings = {
            'theme': s.theme if s else 0,
            'include_featured': s.include_featured if s else False,
            'include_remixes': s.include_remixes if s else False,
        }

    return render_template('profile.html', themes=theme_list, settings=settings)


@profile_bp.route('/profile/settings', methods=['POST'])
@login_required
def update_settings():
    """Update user settings (filters, toggles, theme). Used by navbar, profile page, and remix toggle."""
    if current_user.is_system_or_guest:
        # Guest: store in session only
        if 'country' in request.form:
            val = request.form.get('country')
            session['country'] = int(val) if val and val != '' else None
        if 'genre' in request.form:
            val = request.form.get('genre')
            session['genre'] = int(val) if val and val != '' else None
        if 'theme' in request.form:
            val = request.form.get('theme')
            session['theme'] = int(val) if val else 0
        if 'theme' in request.form:
            session['include_featured'] = request.form.get('include_featured') == 'on'
            session['include_remixes'] = request.form.get('include_remixes') == 'on'
        else:
            if 'include_featured' in request.form:
                session['include_featured'] = request.form.get('include_featured') == 'on'
            if 'include_remixes' in request.form:
                session['include_remixes'] = request.form.get('include_remixes') == 'on'
    else:
        settings = current_user.settings
        if not settings:
            settings = UserSettings(user_id=current_user.id)
            db.session.add(settings)
            current_user.settings = settings
        if settings:
            if 'country' in request.form:
                val = request.form.get('country')
                settings.country = int(val) if val and val != '' else None
            if 'genre' in request.form:
                val = request.form.get('genre')
                settings.genre = int(val) if val and val != '' else None
            if 'theme' in request.form:
                val = request.form.get('theme')
                settings.theme = int(val) if val else 0
            # Checkboxes: if submitted from profile page (has theme field), absence = unchecked = False
            if 'theme' in request.form:
                settings.include_featured = request.form.get('include_featured') == 'on'
                settings.include_remixes = request.form.get('include_remixes') == 'on'
            else:
                # From navbar/artist page — only update if explicitly present
                if 'include_featured' in request.form:
                    settings.include_featured = request.form.get('include_featured') == 'on'
                if 'include_remixes' in request.form:
                    settings.include_remixes = request.form.get('include_remixes') == 'on'
            db.session.commit()

    # If from profile page, redirect back; if HTMX, empty 200
    if request.headers.get('HX-Request'):
        return '', 200
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/image', methods=['POST'])
@login_required
def update_image():
    """Update profile image URL."""
    if current_user.is_system_or_guest:
        return redirect(url_for('profile.profile'))

    image_url = request.form.get('profile_image', '').strip()
    current_user.profile_image = image_url or None
    db.session.commit()
    return redirect(url_for('profile.profile'))
