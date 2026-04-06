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
        artists = [a for a in artists if a.country_id == country_id or a.name == 'Misc. Artists']

    if genre_id is not None:
        # Single query: find all artist IDs that have at least one song in an album with this genre
        # Include children (subunits + soloists) mapped back to their parent
        artist_ids = {a.id for a in artists}
        # Build mapping: child_id → parent artist (for artists in navbar)
        child_rels = ArtistArtist.query.filter(ArtistArtist.artist_1.in_(artist_ids)).all()
        child_to_parent = {rel.artist_2: rel.artist_1 for rel in child_rels}
        all_relevant_ids = artist_ids | set(child_to_parent.keys())

        # Find which of these artist IDs have songs in albums with the target genre
        matching_artist_ids = {row[0] for row in db.session.query(ArtistSong.artist_id).join(
            AlbumSong, ArtistSong.song_id == AlbumSong.song_id
        ).join(
            album_genres, AlbumSong.album_id == album_genres.c.album_id
        ).filter(
            ArtistSong.artist_id.in_(all_relevant_ids),
            album_genres.c.genre_id == genre_id
        ).distinct().all()}

        # Map child matches back to parent
        valid_ids = set()
        for aid in matching_artist_ids:
            if aid in artist_ids:
                valid_ids.add(aid)
            elif aid in child_to_parent:
                valid_ids.add(child_to_parent[aid])
        artists = [a for a in artists if a.id in valid_ids or a.name == 'Misc. Artists']

    misc = [a for a in artists if a.name == 'Misc. Artists']
    rest = [a for a in artists if a.name != 'Misc. Artists']
    return misc + rest


def sync_misc_artist_stubs():
    """Ensure Misc. Artists has a country subunit per country and genre albums per subunit.

    Idempotent — safe to call on every seed or after adding a genre/country.
    Does NOT commit; caller must commit.
    """
    from app.models.lookups import Country, Genre

    misc = Artist.query.filter_by(name='Misc. Artists').first()
    if not misc:
        return

    # --- Country subunits ---
    existing_children = {a.name: a for a in Artist.query.join(
        ArtistArtist, ArtistArtist.artist_2 == Artist.id
    ).filter(ArtistArtist.artist_1 == misc.id).all()}
    existing_slugs = {a.slug for a in Artist.query.all() if a.slug}

    countries = Country.query.order_by(Country.id).all()
    genres = Genre.query.order_by(Genre.id).all()

    # Fast exit: if all country subunits exist and the first one has all genre albums,
    # skip the expensive per-child album queries entirely.
    all_present = all(f'Misc. Artists - {c.country}' in existing_children for c in countries)
    if all_present and existing_children:
        sample = next(iter(existing_children.values()))
        if db.session.query(Album).filter(Album.artist_id == sample.id).count() >= len(genres):
            return

    for country in countries:
        subunit_name = f'Misc. Artists - {country.country}'
        if subunit_name not in existing_children:
            slug = generate_unique_slug(subunit_name, existing_slugs)
            existing_slugs.add(slug)
            sub = Artist(name=subunit_name, slug=slug,
                         gender_id=misc.gender_id, country_id=country.id,
                         submitted_by_id=0)
            db.session.add(sub)
            db.session.flush()
            db.session.add(ArtistArtist(artist_1=misc.id, artist_2=sub.id, relationship=0))
            existing_children[subunit_name] = sub

    db.session.flush()

    # --- Genre albums under each subunit ---
    all_children = list(existing_children.values())

    for child in all_children:
        # Albums linked via songs
        song_albums = {row[0] for row in db.session.query(Album.name).join(
            AlbumSong, Album.id == AlbumSong.album_id
        ).join(
            ArtistSong, AlbumSong.song_id == ArtistSong.song_id
        ).filter(ArtistSong.artist_id == child.id).all()}
        # Albums linked directly via artist_id
        direct_albums = {row[0] for row in db.session.query(Album.name).filter(
            Album.artist_id == child.id).all()}
        existing_albums = song_albums | direct_albums

        for genre in genres:
            album_name = f'Misc. Artists - {genre.genre}'
            if album_name not in existing_albums:
                album = Album(name=album_name, album_type_id=0,
                              submitted_by_id=0, artist_id=child.id)
                db.session.add(album)
                db.session.flush()
                db.session.execute(album_genres.insert().values(
                    album_id=album.id, genre_id=genre.id))

    db.session.flush()


def resolve_artist_for_search(artist_id):
    """If the artist is a subunit, return the parent artist ID instead.

    Searching for a subunit should bring up the main artist page.
    """
    parent = get_parent(artist_id)
    return parent.id if parent else artist_id
