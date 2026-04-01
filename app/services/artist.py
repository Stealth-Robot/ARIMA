"""Artist relationship logic: subunit/soloist display rules.

Key rules:
- Subunit (relationship=0): songs counted in parent stats, nested under parent in UI
- Soloist (relationship=1): standalone row in stats, NOT counted in parent stats
- Nesting is exactly one level deep (subunits cannot have subunits)
"""

import re

from flask import session
from flask_login import current_user

from sqlalchemy import func

from app.extensions import db
from app.models.music import Artist, ArtistArtist, ArtistSong, Song, Album, AlbumSong, album_genres


def slugify(name):
    """Convert an artist name to a URL-safe slug.

    Examples:
        'TWICE'         → 'twice'
        '(G)I-DLE'      → 'gi-dle'
        'Misc. Artists' → 'misc-artists'
    """
    s = name.lower()
    s = re.sub(r'\s+', '-', s)           # spaces → hyphens
    s = re.sub(r'[^a-z0-9-]', '', s)    # strip non-alphanumeric except hyphens
    s = re.sub(r'-{2,}', '-', s)        # collapse multiple hyphens
    s = s.strip('-')
    return s


def generate_unique_slug(name, existing_slugs):
    """Return a unique slug for name, appending -2/-3/... if needed."""
    base = slugify(name)
    candidate = base
    counter = 2
    while candidate in existing_slugs:
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate

SUBUNIT = 0
SOLOIST = 1


def get_children(artist_id):
    """Return (subunits, soloists) as lists of Artist objects."""
    rels = ArtistArtist.query.filter_by(artist_1=artist_id).all()
    subunits = []
    soloists = []
    for rel in rels:
        child = db.session.get(Artist, rel.artist_2)
        if child:
            if rel.relationship == SUBUNIT:
                subunits.append(child)
            elif rel.relationship == SOLOIST:
                soloists.append(child)
    return subunits, soloists


def get_parent(artist_id):
    """Return the parent Artist if this artist is a subunit, else None."""
    rel = ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SUBUNIT).first()
    if rel:
        return db.session.get(Artist, rel.artist_1)
    return None


def get_soloist_parent(artist_id):
    """Return the parent Artist if this artist is a soloist, else None."""
    rel = ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SOLOIST).first()
    if rel:
        return db.session.get(Artist, rel.artist_1)
    return None


def get_songs_for_artist(artist_id, include_subunit_songs=True):
    """Get song IDs for an artist.

    If include_subunit_songs is True, unions subunit songs into the set.
    Soloist songs are never included in the parent's set.
    """
    # Artist's own songs
    own = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist_id).all()}

    if include_subunit_songs:
        subunits, _ = get_children(artist_id)
        for sub in subunits:
            sub_songs = {row.song_id for row in ArtistSong.query.filter_by(artist_id=sub.id).all()}
            own |= sub_songs

    return own


def get_discography_songs(artist_id):
    """Get songs for the artist's discography page (browsing).

    Includes subunit songs AND soloist songs (for browsing only).
    Stats pages should use get_songs_for_artist() instead.
    """
    own = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist_id).all()}
    subunits, soloists = get_children(artist_id)
    for child in subunits + soloists:
        child_songs = {row.song_id for row in ArtistSong.query.filter_by(artist_id=child.id).all()}
        own |= child_songs
    return own


def is_subunit(artist_id):
    """Check if an artist is a subunit of another artist."""
    return ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SUBUNIT).first() is not None


def is_soloist(artist_id):
    """Check if an artist is a soloist of another artist."""
    return ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SOLOIST).first() is not None


def get_top_level_artists(bulk=None):
    """Get artists that should appear as standalone rows in stats/navbar.

    Returns artists that are NOT subunits. Soloists ARE included (they get their own row).
    If bulk data is provided, uses pre-loaded subunit IDs to avoid an extra query.
    """
    if bulk is not None:
        subunit_ids = bulk.subunit_ids
    else:
        subunit_ids = {row.artist_2 for row in ArtistArtist.query.filter_by(relationship=SUBUNIT).all()}
    return Artist.query.filter(~Artist.id.in_(subunit_ids) if subunit_ids else Artist.id.isnot(None)).order_by(func.lower(Artist.name)).all()


def get_navbar_artists():
    """Get artists for the bottom navbar on the Artists page.

    Subunits are excluded (accessed via parent only). Soloists get their own entry.
    """
    return get_top_level_artists()


def get_filtered_navbar():
    """Get navbar artists filtered by the current user's country/genre settings."""
    artists = get_navbar_artists()

    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        country_id = current_user.settings.country
        genre_id = current_user.settings.genre
    else:
        country_id = session.get('country')
        genre_id = session.get('genre')

    if country_id is not None:
        artists = [a for a in artists if a.country_id == country_id]

    if genre_id is not None:
        filtered = []
        for a in artists:
            song_ids = get_discography_songs(a.id)
            if not song_ids:
                continue
            has_genre = db.session.query(Album).join(
                AlbumSong, Album.id == AlbumSong.album_id
            ).join(
                album_genres, Album.id == album_genres.c.album_id
            ).filter(
                AlbumSong.song_id.in_(song_ids),
                album_genres.c.genre_id == genre_id
            ).first() is not None
            if has_genre:
                filtered.append(a)
        artists = filtered

    misc = [a for a in artists if a.name == 'Misc. Artists']
    rest = [a for a in artists if a.name != 'Misc. Artists']
    return misc + rest


def resolve_artist_for_search(artist_id):
    """If the artist is a subunit, return the parent artist ID instead.

    Searching for a subunit should bring up the main artist page.
    """
    parent = get_parent(artist_id)
    return parent.id if parent else artist_id
