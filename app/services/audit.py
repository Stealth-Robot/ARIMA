"""Audit logging — write changelog entries for every mutation."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.changelog import Changelog


def log_change(user, description, artist=None, album=None, song=None):
    """Write a single changelog entry. Call before db.session.commit()."""
    db.session.add(Changelog(
        date=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        artist_id=artist.id if artist else None,
        album_id=album.id if album else None,
        song_id=song.id if song else None,
        description=description,
    ))
