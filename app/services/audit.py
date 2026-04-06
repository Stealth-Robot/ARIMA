"""Audit logging — write changelog entries for every mutation."""

from datetime import datetime, timezone
from urllib.parse import quote

from markupsafe import escape

from app.extensions import db
from app.models.changelog import Changelog
from app.models.music import Artist, ArtistSong, AlbumSong


def _artist_url(artist):
    """Build URL for an artist from the object (prefers slug)."""
    if artist.slug:
        return '/artists/' + quote(artist.slug, safe="().-&+!?@*=' ")
    return '/artists/' + quote(artist.name, safe="().-&+!?@*=' ")



def _make_link(url, text):
    return '<a href="{}" class="changelog-link">{}</a>'.format(escape(url), escape(text))


def build_description_html(description, artist=None, album=None, song=None):
    """Build linked HTML from a changelog description and its related entities.

    Links are built from entity IDs, not substring matching.
    Only quoted names in the description are replaced with links.
    Context (parenthetical suffix) is built with links directly.
    """
    desc = str(escape(description))

    # Build name→link maps from the entities we have
    links = {}  # name -> link html

    if artist:
        links[artist.name] = _make_link(_artist_url(artist), artist.name)
    if album and artist:
        links[album.name] = _make_link(_artist_url(artist) + '#album-' + str(album.id), album.name)
    if song and artist:
        links[song.name] = _make_link(_artist_url(artist) + '#song-' + str(song.id), song.name)

    # Replace only quoted names — songs first (most specific), then albums, then artists
    # This is safe because quotes are unambiguous delimiters
    for name, link in links.items():
        esc_name = str(escape(name))
        for q in ('&#34;', '&quot;', '"'):
            quoted = q + esc_name + q
            if quoted in desc:
                desc = desc.replace(quoted, q + link + q, 1)

    return desc


def _main_artists_for_song(song_id):
    """Return list of (Artist id, name, slug) for a song's main artists."""
    rows = db.session.query(Artist).join(
        ArtistSong, Artist.id == ArtistSong.artist_id
    ).filter(
        ArtistSong.song_id == song_id,
        ArtistSong.artist_is_main == True,
    ).all()
    return rows


def _albums_for_song(song_id):
    """Return list of Album objects for a song."""
    from app.models.music import Album
    rows = db.session.query(Album).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).filter(AlbumSong.song_id == song_id).all()
    return rows


def _main_artists_for_album(album_id):
    """Return list of Artist objects for an album's main artists."""
    rows = db.session.query(Artist).join(
        ArtistSong, Artist.id == ArtistSong.artist_id
    ).join(
        AlbumSong, ArtistSong.song_id == AlbumSong.song_id
    ).filter(
        AlbumSong.album_id == album_id,
        ArtistSong.artist_is_main == True,
    ).distinct().all()
    return rows


def log_change(user, description, artist=None, album=None, song=None, change_type=None):
    """Write a single changelog entry. Call before db.session.commit().

    change_type can be 'song', 'album', or 'artist' to explicitly set the type
    (useful for deletes where the entity is already gone).
    """
    # Resolve change type: song=0, album=1, artist=2, rating=4
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

    # Infer artist from song or album if not explicitly provided
    resolved_artist = artist
    if not resolved_artist and song:
        link = ArtistSong.query.filter_by(song_id=song.id, artist_is_main=True).first()
        if link:
            resolved_artist = db.session.get(Artist, link.artist_id)
    if not resolved_artist and album and album.artist_id:
        resolved_artist = db.session.get(Artist, album.artist_id)

    # Query context entities once
    if song:
        ctx_artists = _main_artists_for_song(song.id)
        ctx_albums = _albums_for_song(song.id)
    elif album:
        ctx_artists = _main_artists_for_album(album.id)
        ctx_albums = []
    else:
        ctx_artists = []
        ctx_albums = []

    # Build plain text context for the description field
    plain_parts = []
    if ctx_artists:
        plain_parts.append(', '.join(a.name for a in ctx_artists))
    if ctx_albums:
        plain_parts.append(', '.join(a.name for a in ctx_albums))
    plain_context = ' (' + ' \u2014 '.join(plain_parts) + ')' if plain_parts else ''

    # Build HTML context with links
    html_parts = []
    if ctx_artists:
        html_parts.append(', '.join(_make_link(_artist_url(a), a.name) for a in ctx_artists))
    if ctx_albums:
        album_links = []
        for alb in ctx_albums:
            if alb.artist_id:
                alb_artist = db.session.get(Artist, alb.artist_id)
                if alb_artist:
                    album_links.append(_make_link(_artist_url(alb_artist) + '#album-' + str(alb.id), alb.name))
                    continue
            album_links.append(str(escape(alb.name)))
        html_parts.append(', '.join(album_links))
    context_html = ' (' + ' \u2014 '.join(html_parts) + ')' if html_parts else ''

    full_desc = description + plain_context
    desc_html = build_description_html(description, artist=resolved_artist, album=album, song=song)
    full_html = desc_html + context_html

    db.session.add(Changelog(
        date=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        artist_id=resolved_artist.id if resolved_artist else None,
        album_id=album.id if album else None,
        song_id=song.id if song else None,
        change_type_id=change_type_id,
        description=full_desc,
        description_html=full_html,
    ))
