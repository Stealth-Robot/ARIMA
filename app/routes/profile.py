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
            'theme': session.get('theme', 1),
            'include_featured': session.get('include_featured', False),
            'include_remixes': session.get('include_remixes', False),
            'album_sort_order': session.get('album_sort_order', 'desc'),
        }
    else:
        s = current_user.settings
        settings = {
            'theme': s.theme if s else 0,
            'include_featured': s.include_featured if s else False,
            'include_remixes': s.include_remixes if s else False,
            'album_sort_order': s.album_sort_order if s else 'desc',
        }

    return render_template('profile.html', themes=theme_list, settings=settings)


def _apply_theme_settings(set_field, form):
    """Apply include_featured, include_remixes, and album_sort_order via set_field(key, value).

    When the profile form is submitted it always includes the 'theme' field, so
    checkbox absence means unchecked (False).  When the request comes from the
    navbar or artist page only explicitly present fields are updated.
    """
    from_profile_page = 'theme' in form
    if from_profile_page:
        set_field('include_featured', form.get('include_featured') == 'on')
        set_field('include_remixes', form.get('include_remixes') == 'on')
        val = form.get('album_sort_order')
        set_field('album_sort_order', val if val in ('asc', 'desc') else 'desc')
    else:
        if 'include_featured' in form:
            set_field('include_featured', form.get('include_featured') == 'on')
        if 'include_remixes' in form:
            set_field('include_remixes', form.get('include_remixes') == 'on')
        if 'album_sort_order' in form:
            val = form.get('album_sort_order')
            set_field('album_sort_order', val if val in ('asc', 'desc') else 'desc')


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
            from app.cache import clear_theme_cache_for_user
            clear_theme_cache_for_user(current_user.id)
        _apply_theme_settings(lambda k, v: session.__setitem__(k, v), request.form)
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
                from app.cache import clear_theme_cache_for_user
                clear_theme_cache_for_user(current_user.id)
            _apply_theme_settings(lambda k, v: setattr(settings, k, v), request.form)
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


@profile_bp.route('/profile/toggle-edit-mode', methods=['POST'])
@login_required
def toggle_edit_mode():
    """Toggle edit mode for editors and admins."""
    if not current_user.is_editor_or_admin:
        return '', 403
    session['edit_mode'] = not session.get('edit_mode', False)
    return redirect(request.referrer or url_for('home.home'))


@profile_bp.route('/profile/reset-password', methods=['POST'])
@login_required
def reset_password():
    """Reset the current user's password."""
    if current_user.is_system_or_guest:
        return '', 403
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    if not new_password or not confirm_password:
        session['pw_error'] = 'Both fields are required.'
        return redirect(url_for('profile.profile'))
    if new_password != confirm_password:
        session['pw_error'] = 'Passwords do not match.'
        return redirect(url_for('profile.profile'))
    if len(new_password) < 4:
        session['pw_error'] = 'Password must be at least 4 characters.'
        return redirect(url_for('profile.profile'))
    from app.routes.auth import _hash_password
    current_user.password = _hash_password(new_password)
    db.session.commit()
    session['pw_success'] = 'Password updated.'
    return redirect(url_for('profile.profile'))
