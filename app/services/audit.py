"""Audit logging — write changelog entries for every mutation."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.changelog import Changelog
from app.models.music import Artist, ArtistSong, AlbumSong


def _main_artists_for_song(song_id):
    """Return list of main artist names for a song (via ArtistSong.artist_is_main)."""
    rows = db.session.query(Artist.name).join(
        ArtistSong, Artist.id == ArtistSong.artist_id
    ).filter(
        ArtistSong.song_id == song_id,
        ArtistSong.artist_is_main == True,
    ).all()
    return [r[0] for r in rows]


def _albums_for_song(song_id):
    """Return list of album names for a song."""
    from app.models.music import Album
    rows = db.session.query(Album.name).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).filter(AlbumSong.song_id == song_id).all()
    return [r[0] for r in rows]


def _main_artists_for_album(album_id):
    """Return list of main artist names for an album (same logic as navbar search)."""
    rows = db.session.query(Artist.name).join(
        ArtistSong, Artist.id == ArtistSong.artist_id
    ).join(
        AlbumSong, ArtistSong.song_id == AlbumSong.song_id
    ).filter(
        AlbumSong.album_id == album_id,
        ArtistSong.artist_is_main == True,
    ).distinct().all()
    return [r[0] for r in rows]


def _build_context(song=None, album=None):
    """Build a parenthetical context string for changelog descriptions."""
    parts = []
    if song:
        artists = _main_artists_for_song(song.id)
        albums = _albums_for_song(song.id)
        if artists:
            parts.append(', '.join(artists))
        if albums:
            parts.append(', '.join(albums))
    elif album:
        artists = _main_artists_for_album(album.id)
        if artists:
            parts.append(', '.join(artists))
    if parts:
        return ' (' + ' — '.join(parts) + ')'
    return ''


def log_change(user, description, artist=None, album=None, song=None, change_type=None):
    """Write a single changelog entry. Call before db.session.commit().

    change_type can be 'song', 'album', or 'artist' to explicitly set the type
    (useful for deletes where the entity is already gone).
    """
    context = _build_context(song=song, album=album)
    # Resolve change type: song=0, album=1, artist=2
    _type_map = {'song': 0, 'album': 1, 'artist': 2, 'rating': 4}
    if change_type and change_type in _type_map:
        change_type_id = _type_map[change_type]
    elif song:
        change_type_id = 0
    elif album:
        change_type_id = 1
    elif artist:
        change_type_id = 2
    else:
        change_type_id = None
    # Infer artist from song if not explicitly provided
    resolved_artist = artist
    if not resolved_artist and song:
        link = ArtistSong.query.filter_by(song_id=song.id, artist_is_main=True).first()
        if link:
            resolved_artist = db.session.get(Artist, link.artist_id)

    db.session.add(Changelog(
        date=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        artist_id=resolved_artist.id if resolved_artist else None,
        album_id=album.id if album else None,
        song_id=song.id if song else None,
        change_type_id=change_type_id,
        description=description + context,
    ))
