"""Viewer-specific display preference helpers shared across routes/services."""
from flask import session
from flask_login import current_user

from app.extensions import db
from app.models.music import Album, AlbumSong, Rating, Song


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


def year_range_filter():
    """The viewer's navbar Year filter as ``[from, to]`` (inclusive), or ``[]`` when off."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return list(current_user.settings.year_range or [])
    return list(session.get('year_range') or [])


def album_in_year_range(album, year_range):
    """Whether the album's release year falls inside ``[from, to]``."""
    lo, hi = year_range
    return bool(album.release_date) and f'{lo:04d}' <= album.release_date[:4] <= f'{hi:04d}'


def album_year_range_clause(year_range):
    """SQL filter on Album for a ``[from, to]`` release-year range."""
    lo, hi = year_range
    return db.func.substr(Album.release_date, 1, 4).between(f'{lo:04d}', f'{hi:04d}')


def year_range_song_ids(year_range, song_ids=None):
    """Song IDs on at least one album released inside ``[from, to]``."""
    q = db.session.query(AlbumSong.song_id).join(Album, Album.id == AlbumSong.album_id).filter(
        album_year_range_clause(year_range))
    if song_ids is not None:
        q = q.filter(AlbumSong.song_id.in_(list(song_ids)))
    return {row[0] for row in q.distinct().all()}
