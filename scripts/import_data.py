"""Import exported JSON data into the ARIMA database.

Usage:
    flask import-data data.json

Requires: flask seed to have been run first (creates roles, countries, etc.)
"""

import json
import sys

from app.extensions import db
from app.models.user import User, UserSettings
from app.models.music import (
    Artist, Album, Song, Rating, ArtistSong, AlbumSong, ArtistArtist, album_genres,
)
from app.models.changelog import Changelog


def import_data(json_path):
    """Import all data from the exported JSON file.

    WARNING: Run on a fresh database (after flask seed). Not idempotent for songs/ratings.
    """
    # Guard: check if data already exists
    existing_songs = Song.query.count()
    if existing_songs > 0:
        print(f'ERROR: Database already has {existing_songs} songs.')
        print('This import is designed for a fresh database (after flask seed).')
        print('To re-import: delete instance/arima.db, run flask seed, then flask import-data.')
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'Loaded {json_path}')
    print(f'  {len(data["users"])} users')
    print(f'  {len(data["artists"])} artist entries')
    print(f'  {len(data["misc_artists"])} misc songs')
    print(f'  {len(data["changelog"])} changelog entries')

    # Phase 1: Users
    user_map = _import_users(data['users'])

    # Phase 2: Artists (main, subunits, soloists)
    artist_map, song_count, rating_count = _import_artists(data['artists'], user_map)

    # Phase 3: Misc Artists (#35)
    misc_songs, misc_ratings = _import_misc_artists(data['misc_artists'], user_map)

    # Phase 4: Changelog
    cl_count = _import_changelog(data['changelog'], user_map)

    print(f'\n=== IMPORT COMPLETE ===')
    print(f'  Users: {len(user_map)}')
    print(f'  Artists: {len(artist_map)}')
    print(f'  Songs: {song_count + misc_songs}')
    print(f'  Ratings: {rating_count + misc_ratings}')
    print(f'  Changelog: {cl_count}')


def _import_users(users_data):
    """Create user rows. Returns {username: user_id} map."""
    user_map = {}
    # First pass: clear sort_order on existing users to avoid unique conflicts
    for existing_user in User.query.filter(User.sort_order.isnot(None)).all():
        existing_user.sort_order = None
    db.session.flush()

    # Second pass: create/update users with correct sort_order from data.json
    for i, u in enumerate(users_data, 1):
        existing = User.query.filter_by(username=u['username']).first()
        if existing:
            existing.sort_order = i
            user_map[u['username']] = existing.id
            continue

        user = User(
            username=u['username'],
            email=f'{u["username"].lower()}@arima.app',
            password=None,
            role_id=2,  # User role
            created_at='2020-01-01T00:00:00+00:00',
            sort_order=i,
        )
        db.session.add(user)
        db.session.flush()
        user_map[u['username']] = user.id
        print(f'  Created user: {u["username"]} (id={user.id})')

    db.session.commit()
    print(f'  {len(user_map)} users mapped')
    return user_map


def _import_artists(artists_data, user_map):
    """Import all artist entries. Returns (artist_map, song_count, rating_count)."""
    artist_map = {}  # name → artist_id
    total_songs = 0
    total_ratings = 0
    parent_map = {}  # child_name → (parent_name, relationship)

    # First pass: create all artists
    for entry in artists_data:
        name = entry['name']
        if name in artist_map:
            # Duplicate name (e.g. "TWICE" as main and as KPop Demon Hunters subunit)
            # Use "name (parent)" to disambiguate
            if entry['parent']:
                name = f"{entry['name']} [{entry['parent']}]"

        existing = Artist.query.filter_by(name=name).first()
        if existing:
            artist_map[name] = existing.id
            # Main artists override gender (subunits may have created the row first)
            if entry['relationship'] == 'main':
                gender_map_upd = {'female': 0, 'male': 1, 'mixed': 2}
                existing.gender_id = gender_map_upd.get(entry.get('gender', 'mixed'), 2)
        else:
            gender_map = {'female': 0, 'male': 1, 'mixed': 2}
            gender_id = gender_map.get(entry.get('gender', 'mixed'), 2)
            artist = Artist(
                name=name,
                gender_id=gender_id,
                country_id=0,  # Default: Korean
                submitted_by_id=0,
                submission_id=0,
            )
            db.session.add(artist)
            db.session.flush()
            artist_map[name] = artist.id

        # Track parent relationships
        if entry['parent']:
            rel_type = 0 if entry['relationship'] == 'subunit' else 1  # 0=Subunit, 1=Soloist
            parent_map[name] = (entry['parent'], rel_type)

    db.session.commit()
    print(f'  {len(artist_map)} artists created/mapped')

    # Create ArtistArtist relationships
    # Skip if the child is a main artist (has its own sheet) — it shouldn't be a subunit of a project
    main_artist_names = {e['name'] for e in artists_data if e['relationship'] == 'main'}
    rel_count = 0
    for child_name, (parent_name, rel_type) in parent_map.items():
        parent_id = artist_map.get(parent_name)
        child_id = artist_map.get(child_name)
        if parent_id and child_id:
            # Don't make a main artist a child of another artist
            if child_name in main_artist_names:
                continue
            existing = ArtistArtist.query.filter_by(artist_1=parent_id, artist_2=child_id).first()
            if not existing:
                db.session.add(ArtistArtist(
                    artist_1=parent_id, artist_2=child_id, relationship=rel_type
                ))
                rel_count += 1
    db.session.commit()
    print(f'  {rel_count} artist relationships created')

    # Second pass: import albums and songs per artist
    for entry in artists_data:
        name = entry['name']
        if entry['parent'] and name not in artist_map:
            name = f"{entry['name']} [{entry['parent']}]"

        artist_id = artist_map.get(name)
        if not artist_id:
            continue

        for alb_data in entry['albums']:
            songs, ratings = _import_album(artist_id, alb_data, user_map)
            total_songs += songs
            total_ratings += ratings

        if total_songs % 2000 == 0 and total_songs > 0:
            print(f'  ... {total_songs} songs imported')

    print(f'  {total_songs} songs, {total_ratings} ratings imported')
    return artist_map, total_songs, total_ratings


def _import_album(artist_id, alb_data, user_map):
    """Import a single album with songs. Returns (song_count, rating_count)."""
    # Create album
    release_date = f'{alb_data["year"]}-01-01' if alb_data.get('year') else None
    album = Album(
        name=alb_data['name'],
        release_date=release_date,
        album_type_id=0,  # Default: Album
        submitted_by_id=0,
        submission_id=0,
    )
    db.session.add(album)
    db.session.flush()

    # Default genre: Kpop
    db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=0))

    song_count = 0
    rating_count = 0

    for song_data in alb_data['songs']:
        song = Song(
            name=song_data['name'],
            submitted_by_id=0,
            submission_id=0,
            is_promoted=song_data.get('is_promoted', False),
            is_remix=False,
        )
        db.session.add(song)
        db.session.flush()

        # AlbumSong
        db.session.add(AlbumSong(
            album_id=album.id,
            song_id=song.id,
            track_number=song_data['track_number'],
        ))

        # ArtistSong
        db.session.add(ArtistSong(
            artist_id=artist_id,
            song_id=song.id,
            artist_is_main=True,
        ))

        # Ratings
        for username, rating_val in song_data.get('ratings', {}).items():
            user_id = user_map.get(username)
            if user_id:
                db.session.add(Rating(
                    song_id=song.id,
                    user_id=user_id,
                    rating=rating_val,
                ))
                rating_count += 1

        song_count += 1

    db.session.commit()
    return song_count, rating_count


def _import_misc_artists(misc_data, user_map):
    """Import Misc. Artists as a single artist with flat song list (#35)."""
    if not misc_data:
        return 0, 0

    # Create or find "Misc. Artists" artist
    misc_artist = Artist.query.filter_by(name='Misc. Artists').first()
    if not misc_artist:
        misc_artist = Artist(
            name='Misc. Artists',
            gender_id=2,  # Mixed
            country_id=0,  # Korean
            submitted_by_id=0,
            submission_id=0,
        )
        db.session.add(misc_artist)
        db.session.flush()

    # Create single album
    misc_album = Album(
        name='Misc. Artists',
        release_date=None,
        album_type_id=0,
        submitted_by_id=0,
        submission_id=0,
    )
    db.session.add(misc_album)
    db.session.flush()
    db.session.execute(album_genres.insert().values(album_id=misc_album.id, genre_id=0))

    song_count = 0
    rating_count = 0

    for i, entry in enumerate(misc_data, 1):
        # Song name includes artist: "Song Name (Artist Name)"
        display_name = f'{entry["song_name"]} ({entry["artist_name"]})'

        song = Song(
            name=display_name,
            submitted_by_id=0,
            submission_id=0,
        )
        db.session.add(song)
        db.session.flush()

        db.session.add(AlbumSong(album_id=misc_album.id, song_id=song.id, track_number=i))
        db.session.add(ArtistSong(artist_id=misc_artist.id, song_id=song.id, artist_is_main=True))

        for username, rating_val in entry.get('ratings', {}).items():
            user_id = user_map.get(username)
            if user_id:
                db.session.add(Rating(song_id=song.id, user_id=user_id, rating=rating_val))
                rating_count += 1

        song_count += 1

    db.session.commit()
    print(f'  Misc. Artists: {song_count} songs, {rating_count} ratings')
    return song_count, rating_count


def _import_changelog(changelog_data, user_map):
    """Import changelog entries."""
    count = 0
    for entry in changelog_data:
        user_id = user_map.get(entry['user']) if entry['user'] else None
        db.session.add(Changelog(
            date=entry['date'] or '2020-01-01',
            user_id=user_id,
            description=entry['description'],
        ))
        count += 1

    db.session.commit()
    print(f'  {count} changelog entries imported')
    return count
