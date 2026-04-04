"""Fetch exact release dates for albums from MusicBrainz API.

Usage:
    flask fetch-album-dates

Rate limit: 1 request per second (MusicBrainz policy).
Queries all albums with YYYY-01-01 dates and logs findings to album_dates_log.txt.
Does NOT modify the database — the log file is reviewed and applied separately.

Log format (tab-separated):
    FOUND    album_id    old_date    new_date    score    artist    album_name
    NOTFOUND album_id    old_date    -           -        artist    album_name
    YEARMISMATCH album_id old_date   found_date  score    artist    album_name
    ERROR    album_id    old_date    -           -        artist    album_name
"""

import json
import socket
import time
import urllib.request
import urllib.parse
import urllib.error

from app.extensions import db
from app.models.music import Album, AlbumSong, ArtistSong, Artist

USER_AGENT = 'ARIMA/1.0 (music rating app; album date lookup)'
MB_API = 'https://musicbrainz.org/ws/2/release/'
LOG_PATH = 'album_dates_log.txt'


def _mb_search(artist_name, album_name, year=None):
    """Search MusicBrainz for a release. Returns (date_str, score) or (None, 0)."""
    query_parts = [
        f'release:"{album_name}"',
        f'artist:"{artist_name}"',
    ]
    if year:
        query_parts.append(f'date:{year}')

    query = ' AND '.join(query_parts)
    params = urllib.parse.urlencode({'query': query, 'fmt': 'json', 'limit': '5'})
    url = f'{MB_API}?{params}'

    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, socket.timeout, OSError):
        return None, 0

    releases = data.get('releases', [])
    if not releases:
        return None, 0

    for release in releases:
        date = release.get('date', '')
        score = release.get('score', 0)

        if len(date) == 10 and score >= 80:
            return date, score
        if len(date) == 7 and score >= 80:
            return f'{date}-01', score

    return None, 0


def _mb_search_loose(artist_name, album_name):
    """Looser search without year constraint."""
    query = f'release:"{album_name}" AND artist:"{artist_name}"'
    params = urllib.parse.urlencode({'query': query, 'fmt': 'json', 'limit': '5'})
    url = f'{MB_API}?{params}'

    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, socket.timeout, OSError):
        return None, 0

    releases = data.get('releases', [])
    for release in releases:
        date = release.get('date', '')
        score = release.get('score', 0)
        if len(date) >= 7 and score >= 90:
            if len(date) == 7:
                date = f'{date}-01'
            return date[:10], score

    return None, 0


def fetch_album_dates():
    """Query MusicBrainz for exact dates and log results to file."""
    albums = Album.query.filter(
        Album.release_date.isnot(None),
        Album.release_date.like('%-01-01'),
    ).all()
    print(f'{len(albums)} albums with year-only dates', flush=True)

    # Build album → primary artist mapping in bulk (avoid N+1 queries)
    album_ids = [a.id for a in albums]
    # Get one song_id per album
    album_song_rows = db.session.query(
        AlbumSong.album_id, db.func.min(AlbumSong.song_id).label('song_id')
    ).filter(AlbumSong.album_id.in_(album_ids)).group_by(AlbumSong.album_id).all()

    song_to_album = {row.song_id: row.album_id for row in album_song_rows}
    song_ids = list(song_to_album.keys())

    # Get primary artist for each song
    artist_song_rows = db.session.query(
        ArtistSong.song_id, Artist.name
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(song_ids),
        ArtistSong.artist_is_main == True,
    ).all()

    album_artist = {}
    for row in artist_song_rows:
        album_id = song_to_album.get(row.song_id)
        if album_id and album_id not in album_artist:
            album_artist[album_id] = row.name

    print(f'{len(album_artist)} albums matched to artists', flush=True)
    print(f'Logging to {LOG_PATH}', flush=True)

    # Resume support: read existing log to skip already-processed albums
    done_ids = set()
    import os
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    try:
                        done_ids.add(int(parts[1]))
                    except ValueError:
                        pass
        print(f'Resuming: {len(done_ids)} albums already processed', flush=True)

    found = 0
    not_found = 0
    year_mismatch = 0
    errors = 0
    processed = 0

    mode = 'a' if done_ids else 'w'
    with open(LOG_PATH, mode, encoding='utf-8', buffering=1) as log:
        if not done_ids:
            log.write('# Album date lookup results\n')
            log.write('# STATUS\\tALBUM_ID\\tOLD_DATE\\tNEW_DATE\\tSCORE\\tARTIST\\tALBUM_NAME\n')

        for album in albums:
            if album.id in done_ids:
                continue

            artist_name = album_artist.get(album.id)
            if not artist_name:
                log.write(f'ERROR\t{album.id}\t{album.release_date}\t-\t-\t-\t{album.name}\n')
                errors += 1
                continue

            album_name = album.name
            year = album.release_date[:4]

            time.sleep(1.1)
            processed += 1

            date, score = _mb_search(artist_name, album_name, year)

            if not date:
                time.sleep(1.1)
                processed += 1
                date, score = _mb_search_loose(artist_name, album_name)

            if date and date != album.release_date:
                if date[:4] != year and abs(int(date[:4]) - int(year)) > 1:
                    log.write(f'YEARMISMATCH\t{album.id}\t{album.release_date}\t{date}\t{score}\t{artist_name}\t{album_name}\n')
                    year_mismatch += 1
                else:
                    log.write(f'FOUND\t{album.id}\t{album.release_date}\t{date}\t{score}\t{artist_name}\t{album_name}\n')
                    found += 1
            else:
                log.write(f'NOTFOUND\t{album.id}\t{album.release_date}\t-\t-\t{artist_name}\t{album_name}\n')
                not_found += 1

            if processed % 100 == 0:
                log.flush()
                print(f'  ... {processed} processed, {found} found, {not_found} not found', flush=True)

    print(f'\n=== FETCH COMPLETE ===')
    print(f'  API calls: {processed}')
    print(f'  Found: {found}')
    print(f'  Not found: {not_found}')
    print(f'  Year mismatch (skipped): {year_mismatch}')
    print(f'  Errors: {errors}')
    print(f'  Log: {LOG_PATH}')
