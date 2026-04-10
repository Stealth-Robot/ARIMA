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
    from app.models.user import DEFAULT_RATING_LABELS
    if current_user.is_system_or_guest:
        settings = {
            'theme': session.get('theme', 1),
            'include_featured': session.get('include_featured', False),
            'include_remixes': session.get('include_remixes', False),
            'album_sort_order': session.get('album_sort_order', 'desc'),
            'song_button_size': session.get('song_button_size', 13),
            'rating_labels': DEFAULT_RATING_LABELS,
            'show_my_key': False,
            'show_default_key': True,
            'hide_autogen_youtube': session.get('hide_autogen_youtube', False),
            'hide_all_youtube': session.get('hide_all_youtube', False),
            'hide_all_spotify': session.get('hide_all_spotify', False),
            'show_track_numbers': session.get('show_track_numbers', True),
        }
    else:
        s = current_user.settings
        settings = {
            'theme': s.theme if s else 0,
            'include_featured': s.include_featured if s else False,
            'include_remixes': s.include_remixes if s else False,
            'album_sort_order': s.album_sort_order if s else 'desc',
            'song_button_size': s.song_button_size if s else 13,
            'rating_labels': {score: s.rating_label(score) for score in range(6)} if s else DEFAULT_RATING_LABELS,
            'show_my_key': s.show_my_key_bool if s else False,
            'show_default_key': s.show_default_key_bool if s else True,
            'hide_autogen_youtube': getattr(s, 'hide_autogen_youtube', False) if s else False,
            'hide_all_youtube': getattr(s, 'hide_all_youtube', False) if s else False,
            'hide_all_spotify': getattr(s, 'hide_all_spotify', False) if s else False,
            'show_track_numbers': getattr(s, 'show_track_numbers', True) if s else True,
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
        set_field('show_track_numbers', form.get('show_track_numbers') == 'on')
        val = form.get('album_sort_order')
        set_field('album_sort_order', val if val in ('asc', 'desc') else 'desc')
        sbs = form.get('song_button_size', type=int)
        if sbs is not None:
            set_field('song_button_size', max(6, min(30, sbs)))
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
        if 'link_visibility' in request.form:
            session['hide_autogen_youtube'] = request.form.get('hide_autogen_youtube') == 'on'
            session['hide_all_youtube'] = request.form.get('hide_all_youtube') == 'on'
            session['hide_all_spotify'] = request.form.get('hide_all_spotify') == 'on'
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
            if 'link_visibility' in request.form:
                settings.hide_autogen_youtube = request.form.get('hide_autogen_youtube') == 'on'
                settings.hide_all_youtube = request.form.get('hide_all_youtube') == 'on'
                settings.hide_all_spotify = request.form.get('hide_all_spotify') == 'on'
            # Rating key labels + show_my_key (only from profile page form)
            if 'theme' in request.form:
                settings.show_my_key = request.form.get('show_my_key') == 'on'
                settings.show_default_key = request.form.get('show_default_key') == 'on'
                for score in range(6):
                    val = request.form.get(f'rating_label_{score}', '').strip()
                    if val:
                        setattr(settings, f'rating_label_{score}', val[:50])
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


@profile_bp.route('/profile/toggle-rating-mode', methods=['POST'])
@login_required
def toggle_rating_mode():
    """Toggle rating mode between 'self' and 'all' for editors and admins."""
    if not current_user.is_editor_or_admin:
        return '', 403
    current = session.get('rating_mode', 'self')
    session['rating_mode'] = 'all' if current == 'self' else 'self'
    return redirect(request.referrer or url_for('home.home'))


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
