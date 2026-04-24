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
            if a.name == 'Misc. Artists':
                return True
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

    # --- Rename legacy "Misc. Artists - X" subunits to short names ---
    children = Artist.query.join(
        ArtistArtist, ArtistArtist.artist_2 == Artist.id
    ).filter(ArtistArtist.artist_1 == misc.id).all()
    existing_slugs = {a.slug for a in Artist.query.all() if a.slug}
    prefixes = ['Misc. Artists - ', 'Misc Artists - ']
    renamed = False
    for child in children:
        for pfx in prefixes:
            if child.name.startswith(pfx):
                short_name = child.name[len(pfx):]
                existing_slugs.discard(child.slug)
                child.name = short_name
                child.slug = generate_unique_slug(short_name, existing_slugs)
                existing_slugs.add(child.slug)
                renamed = True
                break
    # Rename albums using raw SQL (avoids ORM full-table scan)
    if renamed:
        for pattern, prefix_len in [('Misc. Artists - %', 16), ('Misc Artists - %', 15)]:
            db.session.execute(db.text(
                'UPDATE album SET name = SUBSTR(name, :plen) '
                'WHERE name LIKE :pattern'
            ), {'plen': prefix_len + 1, 'pattern': pattern})
        db.session.flush()

    # --- Country subunits ---
    existing_children = {a.name: a for a in children}
    existing_country_ids = {a.country_id for a in children}

    countries = Country.query.order_by(Country.id).all()
    genres = Genre.query.order_by(Genre.id).all()

    for country in countries:
        subunit_name = country.country
        if subunit_name not in existing_children and country.id not in existing_country_ids:
            slug = generate_unique_slug(subunit_name, existing_slugs)
            existing_slugs.add(slug)
            sub = Artist(name=subunit_name, slug=slug,
                         gender_id=misc.gender_id, country_id=country.id,
                         submitted_by_id=0)
            db.session.add(sub)
            db.session.flush()
            db.session.add(ArtistArtist(artist_1=misc.id, artist_2=sub.id, relationship=0))
            existing_children[subunit_name] = sub
            existing_country_ids.add(country.id)

    db.session.flush()

    # --- Merge duplicate/orphan albums into canonical genre albums ---
    genre_names = {g.genre.lower(): g.genre for g in genres}
    for child in existing_children.values():
        # Build map of canonical genre albums (with artist_id) by lowercase name
        canonical = {}
        for row in db.session.execute(db.text(
            'SELECT id, name FROM album WHERE artist_id = :cid'
        ), {'cid': child.id}).fetchall():
            canonical[row[1].lower()] = row[0]

        # Find all non-canonical albums linked to this child via songs
        dupes = db.session.execute(db.text(
            'SELECT DISTINCT a.id, a.name FROM album a '
            'JOIN album_song als ON als.album_id = a.id '
            'JOIN artist_song ars ON ars.song_id = als.song_id AND ars.artist_is_main = 1 '
            'WHERE ars.artist_id = :cid AND (a.artist_id IS NULL OR a.artist_id != :cid)'
        ), {'cid': child.id}).fetchall()

        for dupe_id, dupe_name in dupes:
            # Match by name, or map "Misc. Artists" to child's country genre
            target_id = canonical.get(dupe_name.lower())
            if not target_id and dupe_name in ('Misc. Artists', 'Misc Artists'):
                # Try matching by the album's genre tag
                genre_row = db.session.execute(db.text(
                    'SELECT g.genre FROM album_genres ag '
                    'JOIN genre g ON g.id = ag.genre_id '
                    'WHERE ag.album_id = :aid LIMIT 1'
                ), {'aid': dupe_id}).first()
                if genre_row:
                    target_id = canonical.get(genre_row[0].lower())

            if target_id and target_id != dupe_id:
                # Move songs from dupe to target
                max_track = db.session.execute(db.text(
                    'SELECT COALESCE(MAX(track_number), 0) FROM album_song WHERE album_id = :aid'
                ), {'aid': target_id}).scalar()
                songs = db.session.execute(db.text(
                    'SELECT song_id FROM album_song '
                    'WHERE album_id = :aid ORDER BY track_number'
                ), {'aid': dupe_id}).fetchall()
                for (song_id,) in songs:
                    max_track += 1
                    db.session.execute(db.text(
                        'INSERT OR IGNORE INTO album_song (album_id, song_id, track_number) '
                        'VALUES (:aid, :sid, :tn)'
                    ), {'aid': target_id, 'sid': song_id, 'tn': max_track})
                db.session.execute(db.text('DELETE FROM album_song WHERE album_id = :aid'), {'aid': dupe_id})
                db.session.execute(db.text('DELETE FROM album_genres WHERE album_id = :aid'), {'aid': dupe_id})
                db.session.execute(db.text('DELETE FROM album WHERE id = :aid'), {'aid': dupe_id})
            elif not target_id:
                db.session.execute(db.text(
                    'UPDATE album SET artist_id = :cid WHERE id = :aid'
                ), {'cid': child.id, 'aid': dupe_id})

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
            album_name = genre.genre
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
