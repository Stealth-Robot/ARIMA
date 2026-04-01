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


def _hex_to_rgb(hex_str):
    """Convert '#RRGGBB' to (r, g, b) tuple."""
    h = hex_str.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r, g, b):
    """Convert (r, g, b) to '#RRGGBB'."""
    return f'#{int(r):02X}{int(g):02X}{int(b):02X}'


def _lerp_colour(hex1, hex2, t):
    """Linear interpolation between two hex colours. t=0 → hex1, t=1 → hex2."""
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)
    r = r1 + (r2 - r1) * t
    g = g1 + (g2 - g1) * t
    b = b1 + (b2 - b1) * t
    return _rgb_to_hex(r, g, b)


def score_to_colour(value, theme):
    """Get heat map colour for an average score (0-5).

    Step-based matching (not gradient) — matches spreadsheet conditional formatting.
    """
    if value is None or value == 0:
        return '#FFFFFF'
    if value >= 5.0:
        return theme.get('rating_5_bg', '#FF0016')
    if value >= 4.5:
        return theme.get('heatmap_high', '#FFB7FE')
    if value >= 3.5:
        return theme.get('rating_4_bg', '#FF8E1E')
    if value >= 2.5:
        return theme.get('rating_3_bg', '#FEFF2A')
    if value >= 1.5:
        return theme.get('rating_2_bg', '#9EFFA4')
    return theme.get('rating_1_bg', '#8AB5FC')


def score_to_style(value, theme):
    """Get bg + text colour for an average score (0-5).

    Returns dict with 'bg' and 'text' hex values, or None for zero/unrated.
    Uses same step logic as score_to_colour but pairs with the nearest rating text colour.
    """
    if value is None:
        return None
    if value >= 5.0:
        return {'bg': theme.get('rating_5_bg', '#FF0016'), 'text': theme.get('rating_5_text', '#000000')}
    if value >= 4.5:
        return {'bg': theme.get('rating_5_bg', '#FF0016'), 'text': theme.get('rating_5_text', '#000000')}
    if value >= 3.5:
        return {'bg': theme.get('rating_4_bg', '#FF8E1E'), 'text': theme.get('rating_4_text', '#000000')}
    if value >= 2.5:
        return {'bg': theme.get('rating_3_bg', '#FEFF2A'), 'text': theme.get('rating_3_text', '#000000')}
    if value >= 1.5:
        return {'bg': theme.get('rating_2_bg', '#9EFFA4'), 'text': theme.get('rating_2_text', '#FFFFFF')}
    if value >= 1.0:
        return {'bg': theme.get('rating_1_bg', '#8AB5FC'), 'text': theme.get('rating_1_text', '#FFFFFF')}
    return {'bg': theme.get('rating_0_bg', '#9200FC'), 'text': theme.get('rating_0_text', '#FFFFFF')}


def pct_to_colour(value, theme):
    """Get heat map colour for a completion percentage (0-100).

    Purple→orange gradient matching spreadsheet colour scale.
    """
    if value is None or value == 0:
        return '#FFFFFF'

    low = theme.get('pct_low', '#833AB4')   # Purple at 0%
    high = theme.get('pct_high', '#FCB045')  # Orange at 100%

    t = min(value, 100) / 100.0
    return _lerp_colour(low, high, t)


def rating_cell_style(score, theme):
    """Get inline CSS for a rating cell (background + text colour).

    Returns dict with 'bg' and 'text' hex values, or None for unrated.
    """
    if score is None:
        return None

    bg = theme.get(f'rating_{score}_bg')
    if not bg:
        return None

    text = theme.get(f'rating_{score}_text', '#000000')
    return {'bg': bg, 'text': text}
