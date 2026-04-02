from flask import Blueprint, request, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.theme import Theme
from app.decorators import role_required, ADMIN

themes_bp = Blueprint('themes', __name__)

# Colour columns to display/edit
COLOUR_COLS = [c.name for c in Theme.__table__.columns if c.name not in ('id', 'name', 'user_id')]


@themes_bp.route('/themes')
@login_required
def themes_list():
    """Browse all themes with colour previews."""
    themes = Theme.query.order_by(Theme.id).all()
    theme_data = []
    for t in themes:
        if t.name:
            display_name = t.name
        elif t.owner:
            display_name = f"{t.owner.username}'s Theme"
        else:
            display_name = f'Theme #{t.id}'
        colours = {col: getattr(t, col) for col in COLOUR_COLS}
        theme_data.append({
            'theme': t,
            'display_name': display_name,
            'colours': colours,
            'can_edit': _can_edit(t),
        })
    return render_template('themes.html', themes=theme_data, colour_cols=COLOUR_COLS)


@themes_bp.route('/themes/<int:theme_id>/edit', methods=['GET'])
@login_required
def theme_edit(theme_id):
    """Edit theme form."""
    t = db.session.get(Theme, theme_id)
    if not t or not _can_edit(t):
        return redirect(url_for('themes.themes_list'))
    colours = {col: getattr(t, col) for col in COLOUR_COLS}
    return render_template('theme_edit.html', edit_theme=t, colours=colours, colour_cols=COLOUR_COLS)


@themes_bp.route('/themes/<int:theme_id>', methods=['POST'])
@login_required
def theme_save(theme_id):
    """Save theme colour changes."""
    t = db.session.get(Theme, theme_id)
    if not t or not _can_edit(t):
        return redirect(url_for('themes.themes_list'))

    for col in COLOUR_COLS:
        value = request.form.get(col, '').strip()
        setattr(t, col, value if value else None)

    db.session.commit()
    from app.cache import clear_theme_cache_for_theme
    clear_theme_cache_for_theme(theme_id)
    return redirect(url_for('themes.themes_list'))


def _can_edit(theme):
    """Check if current user can edit this theme."""
    if theme.id in (0, 1):
        return current_user.is_admin
    if theme.user_id == current_user.id:
        return True
    return False
