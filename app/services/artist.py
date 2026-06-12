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


_SYMBOL_MAP = {
    '%': 'pct',
    '&': 'and',
    '+': 'plus',
    '@': 'at',
    '#': 'num',
    '$': 'dollar',
    '!': 'excl',
    '?': 'q',
    '*': 'star',
    '=': 'eq',
}


def slugify(name):
    """Convert an artist name to a URL-safe slug.

    Symbols are converted to readable equivalents instead of being stripped.
    Spaces are preserved (URL-encoded as %20 in links).

    Examples:
        'TWICE'         → 'twice'
        '(G)I-DLE'      → '(g)i-dle'
        'Misc. Artists' → 'misc. artists'
        '100%'          → '100pct'
        'GD & TOP'      → 'gd and top'
    """
    s = name.lower()
    for symbol, replacement in _SYMBOL_MAP.items():
        s = s.replace(symbol, replacement)
    s = re.sub(r'[^a-z0-9() .-]', '', s)  # keep alphanumeric, parens, spaces, dots, hyphens
    s = re.sub(r'\s+', ' ', s)             # collapse multiple spaces
    s = s.strip()
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
    if not rels:
        return [], []
    child_ids = [rel.artist_2 for rel in rels]
    children_by_id = {a.id: a for a in Artist.query.filter(Artist.id.in_(child_ids)).all()}
    subunits = []
    soloists = []
    for rel in rels:
        child = children_by_id.get(rel.artist_2)
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


def get_soloist_parents(artist_id):
    """Return parent Artists if this artist is a soloist, else empty list."""
    rels = ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SOLOIST).all()
    if not rels:
        return []
    parent_ids = [rel.artist_1 for rel in rels]
    return Artist.query.filter(Artist.id.in_(parent_ids)).all()


def get_songs_for_artist(artist_id, include_subunit_songs=True):
    """Get song IDs for an artist.

    If include_subunit_songs is True, unions subunit songs into the set.
    Soloist songs are never included in the parent's set.
    """
    if include_subunit_songs:
        subunits, _ = get_children(artist_id)
        all_ids = [artist_id] + [s.id for s in subunits]
    else:
        all_ids = [artist_id]
    return {row.song_id for row in ArtistSong.query.filter(ArtistSong.artist_id.in_(all_ids)).all()}


def get_discography_songs(artist_id):
    """Get songs for the artist's discography page (browsing).

    Includes subunit songs AND soloist songs (for browsing only).
    Stats pages should use get_songs_for_artist() instead.
    """
    subunits, soloists = get_children(artist_id)
    all_ids = [artist_id] + [c.id for c in subunits + soloists]
    return {row.song_id for row in ArtistSong.query.filter(ArtistSong.artist_id.in_(all_ids)).all()}


def is_subunit(artist_id):
    """Check if an artist is a subunit of another artist."""
    return ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SUBUNIT).first() is not None


def is_soloist(artist_id):
    """Check if an artist is a soloist of another artist."""
    return ArtistArtist.query.filter_by(artist_2=artist_id, relationship=SOLOIST).first() is not None


def soloist_parent_map(artist_ids):
    """Return {artist_id: [parent_ids]} for those artist_ids that are soloists."""
    ids = list(artist_ids)
    if not ids:
        return {}
    rows = ArtistArtist.query.with_entities(ArtistArtist.artist_2, ArtistArtist.artist_1).filter(
        ArtistArtist.relationship == SOLOIST, ArtistArtist.artist_2.in_(ids)).all()
    parents = {}
    for child_id, parent_id in rows:
        parents.setdefault(child_id, []).append(parent_id)
    return parents


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
        country_ids = list(current_user.settings.country_ids or [])
        genre_ids = list(current_user.settings.genre_ids or [])
    else:
        country_ids = list(session.get('country_ids') or [])
        genre_ids = list(session.get('genre_ids') or [])

    if country_ids:
        country_set = set(country_ids)
        # Include parent artists if any of their children match the country
        artist_ids = {a.id for a in artists}
        child_rels = ArtistArtist.query.filter(ArtistArtist.artist_1.in_(artist_ids)).all()
        child_ids_by_parent = {}
        for rel in child_rels:
            child_ids_by_parent.setdefault(rel.artist_1, []).append(rel.artist_2)
        from app.models.music import Artist as ArtistModel
        child_country = {}
        all_child_ids = [cid for cids in child_ids_by_parent.values() for cid in cids]
        if all_child_ids:
            for row in db.session.query(ArtistModel.id, ArtistModel.country_id).filter(ArtistModel.id.in_(all_child_ids)).all():
                child_country[row[0]] = row[1]
        def matches_country(a):
            if a.country_id in country_set:
                return True
            for cid in child_ids_by_parent.get(a.id, []):
                if child_country.get(cid) in country_set:
                    return True
            return False
        artists = [a for a in artists if matches_country(a)]

    if genre_ids:
        # Single query: find all artist IDs that have at least one song in an album with any selected genre
        # Include children (subunits + soloists) mapped back to their parent
        artist_ids = {a.id for a in artists}
        # Build mapping: child_id → parent artist (for artists in navbar)
        child_rels = ArtistArtist.query.filter(ArtistArtist.artist_1.in_(artist_ids)).all()
        child_to_parent = {rel.artist_2: rel.artist_1 for rel in child_rels}
        all_relevant_ids = artist_ids | set(child_to_parent.keys())

        # Find which of these artist IDs have songs in albums with any of the target genres
        matching_artist_ids = {row[0] for row in db.session.query(ArtistSong.artist_id).join(
            AlbumSong, ArtistSong.song_id == AlbumSong.song_id
        ).join(
            album_genres, AlbumSong.album_id == album_genres.c.album_id
        ).filter(
            ArtistSong.artist_id.in_(all_relevant_ids),
            album_genres.c.genre_id.in_(genre_ids)
        ).distinct().all()}

        # Map child matches back to parent
        valid_ids = set()
        for aid in matching_artist_ids:
            if aid in artist_ids:
                valid_ids.add(aid)
            elif aid in child_to_parent:
                valid_ids.add(child_to_parent[aid])
        artists = [a for a in artists if a.id in valid_ids]

    return [a for a in artists if a.name != 'Misc. Artists']


def resolve_artist_for_search(artist_id):
    """If the artist is a subunit, return the parent artist ID instead.

    Searching for a subunit should bring up the main artist page.
    """
    parent = get_parent(artist_id)
    return parent.id if parent else artist_id
