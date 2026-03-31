from flask import session
from flask_login import current_user

from app.extensions import db
from app.models.theme import Theme


# Colour columns — everything except id, name, user_id
_COLOUR_COLUMNS = None


def _get_colour_columns():
    global _COLOUR_COLUMNS
    if _COLOUR_COLUMNS is None:
        _COLOUR_COLUMNS = [c.name for c in Theme.__table__.columns
                           if c.name not in ('id', 'name', 'user_id')]
    return _COLOUR_COLUMNS


def get_resolved_theme(user):
    """Return a dict of colour_name → hex_value with Classic fallback.

    For logged-in users, reads theme from UserSettings.
    For Guest/anonymous, reads from session cookie (default: Classic).
    """
    classic = db.session.get(Theme, 0)
    if classic is None:
        return {}

    # Determine selected theme ID
    if user.is_authenticated and not user.is_system_or_guest:
        selected_theme_id = user.settings.theme if user.settings else 0
    else:
        selected_theme_id = session.get('theme', 0)

    # Load selected theme (fall back to Classic if missing)
    if selected_theme_id == 0:
        selected = classic
    else:
        selected = db.session.get(Theme, selected_theme_id) or classic

    # Build resolved dict: selected value if not None, else Classic value
    resolved = {}
    for col in _get_colour_columns():
        value = getattr(selected, col)
        resolved[col] = value if value is not None else getattr(classic, col)

    return resolved
