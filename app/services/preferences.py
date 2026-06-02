"""Viewer-specific display preference helpers shared across routes/services."""
from flask_login import current_user

from app.extensions import db
from app.models.music import Rating, Song


def show_rated_remixes_enabled():
    """Whether the viewer wants remixes they've rated shown even when remixes are hidden."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return bool(getattr(current_user.settings, 'show_rated_remixes', True))
    return False


def rated_remix_override_ids(include_remixes, song_ids=None):
    """Return remix song IDs to keep visible because the viewer rated them.

    Empty when remixes are already shown, the viewer is a guest, or the
    'show rated remixes' setting is off — so callers can apply it unconditionally
    without changing existing behaviour for users who haven't opted in.
    """
    if include_remixes or not show_rated_remixes_enabled():
        return set()
    if song_ids is not None and not song_ids:
        return set()
    q = db.session.query(Rating.song_id).join(Song, Song.id == Rating.song_id).filter(
        Rating.user_id == current_user.id,
        Rating.rating.isnot(None),
        Song.is_remix == True,
    )
    if song_ids is not None:
        q = q.filter(Rating.song_id.in_(song_ids))
    return {row[0] for row in q.all()}
