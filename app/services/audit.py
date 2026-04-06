"""Audit logging — write changelog entries for every mutation."""

from datetime import datetime, timezone
from urllib.parse import quote

from markupsafe import escape

from app.extensions import db
from app.models.changelog import Changelog
from app.models.music import Artist, ArtistSong, AlbumSong


def _artist_url(name):
    return '/artists/' + quote(name, safe="().-&+!?@*=' ")


def _make_link(url, text):
    return '<a href="{}" class="changelog-link">{}</a>'.format(escape(url), escape(text))


def build_description_html(description, artist=None, album=None, song=None, all_artist_names=None):
    """Build linked HTML from a changelog description and its related entities.

    Pass all_artist_names (list of strings) to avoid a DB query per call during bulk operations.
    """
    desc = str(escape(description))

    # Build name→link maps from the entities we have
    artist_map = {}
    album_map = {}
    song_map = {}

    if artist:
        artist_map[artist.name] = _make_link(_artist_url(artist.name), artist.name)
    if album and artist:
        album_map[album.name] = _make_link(_artist_url(artist.name) + '#album-' + str(album.id), album.name)
    if song and artist:
        song_map[song.name] = _make_link(_artist_url(artist.name) + '#song-' + str(song.id), song.name)

    # Also resolve any artist names in context strings (parenthetical text)
    if all_artist_names is None:
        all_artist_names = [r[0] for r in db.session.query(Artist.name).all()]
    for aname in all_artist_names:
        if aname not in artist_map and aname in description:
            artist_map[aname] = _make_link(_artist_url(aname), aname)

    # Phase 1: Replace quoted names (songs → albums → artists)
    for entity_map in (song_map, album_map, artist_map):
        for name, link in entity_map.items():
            esc_name = str(escape(name))
            for q in ('&#34;', '&quot;', '"'):
                quoted = q + esc_name + q
                if quoted in desc:
                    desc = desc.replace(quoted, q + link + q, 1)

    # Phase 2: Replace remaining unquoted names (longest first)
    all_names = list(song_map.items()) + list(album_map.items()) + list(artist_map.items())
    all_names.sort(key=lambda x: len(x[0]), reverse=True)
    for name, link in all_names:
        esc_name = str(escape(name))
        if len(esc_name) < 2:
            continue
        idx = desc.find(esc_name)
        if idx == -1:
            continue
        before = desc[:idx]
        if before.rfind('<a ') > before.rfind('</a>'):
            continue
        desc = desc[:idx] + link + desc[idx + len(esc_name):]

    return desc


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

    full_desc = description + context
    db.session.add(Changelog(
        date=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        artist_id=resolved_artist.id if resolved_artist else None,
        album_id=album.id if album else None,
        song_id=song.id if song else None,
        change_type_id=change_type_id,
        description=full_desc,
        description_html=build_description_html(
            full_desc, artist=resolved_artist, album=album, song=song),
    ))
