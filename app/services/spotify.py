"""Spotify Web API integration using Client Credentials flow."""

import os
import re
import time
import logging
import threading

import requests

logger = logging.getLogger(__name__)

_BASE = 'https://api.spotify.com/v1'
_TOKEN_URL = 'https://accounts.spotify.com/api/token'

# Module-level token cache
_access_token = None
_token_expires_at = 0

# Rate throttle — serialises all Spotify calls across threads
_rate_lock = threading.Lock()
_last_request_at = 0.0
_MIN_INTERVAL = 0.5  # seconds between any two Spotify API calls

# Thread-local status callback for progress reporting from low-level functions
_local = threading.local()


def _status(msg):
    """Report a low-level status message to the current thread's progress callback."""
    cb = getattr(_local, 'on_status', None)
    if cb:
        cb(msg)


def _throttle():
    """Ensure minimum interval between Spotify API calls."""
    global _last_request_at
    with _rate_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            _status(f'Throttling ({wait:.1f}s)...')
            time.sleep(wait)
        _last_request_at = time.time()


def _get_credentials():
    """Return (client_id, client_secret) or raise if not configured."""
    cid = os.environ.get('SPOTIFY_CLIENT_ID')
    secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not cid or not secret:
        raise SpotifyError('Spotify credentials not configured')
    return cid, secret


def _get_token(_retries=3):
    """Get a valid access token, refreshing if expired."""
    global _access_token, _token_expires_at
    if _access_token and time.time() < _token_expires_at - 60:
        return _access_token
    _status('Refreshing auth token...')
    cid, secret = _get_credentials()
    _throttle()
    resp = requests.post(_TOKEN_URL, data={'grant_type': 'client_credentials'},
                         auth=(cid, secret), timeout=10)
    if resp.status_code == 429:
        try:
            wait = int(resp.headers.get('Retry-After', 5))
        except (ValueError, TypeError):
            wait = 5
        if wait > 30:
            mins = (wait + 59) // 60
            raise SpotifyError(f'Spotify rate limit too long ({mins} min). Please wait and try again later.')
        if _retries > 0:
            _status(f'Token rate-limited, waiting {wait}s...')
            time.sleep(wait)
            return _get_token(_retries=_retries - 1)
        raise SpotifyError('Spotify is rate-limiting requests. Please wait a minute and try again.')
    if resp.status_code != 200:
        raise SpotifyError(f'Token request failed: {resp.status_code}')
    _status('Auth token OK')
    data = resp.json()
    _access_token = data['access_token']
    _token_expires_at = time.time() + data.get('expires_in', 3600)
    return _access_token


def _api_get(path_or_url, _retries=3):
    """GET from Spotify API with auth header. Accepts a path or full URL."""
    token = _get_token()
    url = path_or_url if path_or_url.startswith('http') else f'{_BASE}{path_or_url}'
    # Friendly label for the URL
    label = url.replace(_BASE, '')
    if len(label) > 60:
        label = label[:57] + '...'
    _throttle()
    _status(f'Requesting {label}')
    resp = requests.get(url,
                        headers={'Authorization': f'Bearer {token}'},
                        timeout=15)
    if resp.status_code == 404:
        raise SpotifyError('Not found on Spotify')
    if resp.status_code == 429:
        try:
            wait = int(resp.headers.get('Retry-After', 5))
        except (ValueError, TypeError):
            wait = 5
        if wait > 30:
            mins = (wait + 59) // 60
            raise SpotifyError(f'Spotify rate limit too long ({mins} min). Please wait and try again later.')
        _status(f'Rate-limited on {label}, waiting {wait}s (retries left: {_retries - 1})...')
        logger.warning('_api_get: 429, Retry-After=%d, retries left=%d', wait, _retries - 1)
        if _retries > 0:
            time.sleep(wait)
            return _api_get(path_or_url, _retries=_retries - 1)
        raise SpotifyError('Spotify is rate-limiting requests. Please wait a minute and try again.')
    if resp.status_code != 200:
        body = ''
        try:
            body = resp.json().get('error', {}).get('message', '')
        except Exception:
            pass
        detail = f' — {body}' if body else ''
        raise SpotifyError(f'Spotify API error: {resp.status_code}{detail} ({label})')
    _status(f'Got {label} (HTTP {resp.status_code})')
    return resp.json()


def _parse_id(url, kind):
    """Extract a Spotify ID from a URL. kind is 'album' or 'artist'."""
    # https://open.spotify.com/album/ABC123?si=xyz
    # https://open.spotify.com/artist/ABC123?si=xyz
    m = re.search(rf'open\.spotify\.com/(?:intl-[a-z]+/)?{kind}/([A-Za-z0-9]+)(?:[/?]|$)', url)
    if not m:
        raise SpotifyError(f'Invalid Spotify {kind} URL')
    return m.group(1)


_TYPE_MAP = {'album': 0, 'single': 2, 'compilation': 0}


def _album_type_id(spotify_type, total_tracks):
    """Map Spotify album_type to our type IDs: 0=Album, 1=EP, 2=Single."""
    if spotify_type == 'single':
        return 2 if total_tracks <= 2 else 1  # 1-2 tracks = Single, 3+ = EP
    return _TYPE_MAP.get(spotify_type, 0)


def fetch_album(url):
    """Fetch album metadata from a Spotify album URL.

    Returns dict: {name, release_date, album_type_id, tracks: [{name, track_number}]}
    """
    album_id = _parse_id(url, 'album')
    data = _api_get(f'/albums/{album_id}')
    tracks = []
    for t in data.get('tracks', {}).get('items', []):
        tracks.append({
            'name': t['name'],
            'track_number': t['track_number'],
            'spotify_url': t.get('external_urls', {}).get('spotify', ''),
        })
    return {
        'name': data['name'],
        'release_date': _normalize_date(data.get('release_date', '')),
        'album_type_id': _album_type_id(data.get('album_type', ''), data.get('total_tracks', 0)),
        'tracks': tracks,
    }


class _Cancelled(Exception):
    """Raised when an import is cancelled."""
    pass


def fetch_artist(url, on_progress=None, cancel=None):
    """Fetch artist name + full discography from a Spotify artist URL.

    on_progress: optional callback(message, percent) for streaming progress.
    cancel: optional threading.Event — set it to abort the import.
    Returns dict: {name, albums: [{name, release_date, album_type_id, tracks: [{name, track_number}]}]}
    """
    _current_pct = [0]

    def _check():
        if cancel and cancel.is_set():
            raise _Cancelled('Import cancelled')

    def _progress(msg, pct):
        _current_pct[0] = pct
        if on_progress:
            on_progress(msg, pct)

    # Wire up thread-local so _api_get/_throttle report to the modal
    if on_progress:
        _local.on_status = lambda msg: on_progress(msg, _current_pct[0])

    try:
        _check()
        _progress('Connecting to Spotify...', 0)
        artist_id = _parse_id(url, 'artist')
        artist_data = _api_get(f'/artists/{artist_id}')
        artist_name = artist_data['name']
        _progress(f'Found: {artist_name}', 10)

        # Fetch all albums (paginated)
        albums_raw = []
        offset = 0
        while True:
            _check()
            page = _api_get(f'/artists/{artist_id}/albums?include_groups=album,single&limit=10&offset={offset}')
            items = page.get('items', [])
            albums_raw.extend(items)
            _progress(f'Scanning discography... ({len(albums_raw)} albums found)', 20)
            if not items or not page.get('next'):
                break
            offset += len(items)

        total = len(albums_raw)
        _progress(f'Found {total} albums', 30)

        # Filter out entries without valid IDs
        albums_raw = [a for a in albums_raw if a and a.get('id')]
        total = len(albums_raw)

        # Fetch full track listings one album at a time
        albums = []
        for idx, raw in enumerate(albums_raw):
            _check()
            pct = 30 + int(65 * ((idx + 1) / max(total, 1)))
            _progress(f'Loading tracks ({idx + 1} of {total})', pct)
            try:
                full = _api_get(f'/albums/{raw["id"]}')
            except SpotifyError as e:
                logger.warning('Failed to fetch album %s: %s', raw['id'], e)
                continue
            tracks = [{'name': t['name'], 'track_number': t['track_number'],
                       'spotify_url': t.get('external_urls', {}).get('spotify', '')}
                      for t in full.get('tracks', {}).get('items', [])]
            albums.append({
                'name': full['name'],
                'release_date': _normalize_date(full.get('release_date', '')),
                'album_type_id': _album_type_id(full.get('album_type', ''), full.get('total_tracks', 0)),
                'tracks': tracks,
            })

        _progress('Almost done...', 95)
        return {
            'name': artist_name,
            'albums': albums,
        }
    finally:
        _local.on_status = None


def _normalize_date(date_str):
    """Normalize Spotify dates (YYYY, YYYY-MM, YYYY-MM-DD) to YYYY-MM-DD."""
    if not date_str:
        return ''
    if re.fullmatch(r'\d{4}', date_str):
        return f'{date_str}-01-01'
    if re.fullmatch(r'\d{4}-\d{2}', date_str):
        return f'{date_str}-01'
    return date_str


def search_track(track_name, artist_name):
    """Search Spotify for a track by name and artist.

    Only returns tracks where the artist appears in the track's artist list.
    Returns list of up to 5 candidates: [{name, album, artists, spotify_url}]
    """
    q = f'track:{track_name} artist:{artist_name}'
    data = _api_get(f'/search?q={requests.utils.quote(q)}&type=track&limit=10')
    items = data.get('tracks', {}).get('items', [])
    norm_artist = _normalize_name(artist_name)
    results = []
    for item in items:
        url = item.get('external_urls', {}).get('spotify', '')
        if not url:
            continue
        track_artists = item.get('artists', [])
        artist_match = any(
            _normalize_name(a['name']) == norm_artist
            or norm_artist in _normalize_name(a['name'])
            or _normalize_name(a['name']) in norm_artist
            for a in track_artists
        )
        if not artist_match:
            continue
        artists = ', '.join(a['name'] for a in track_artists)
        results.append({
            'name': item['name'],
            'album': item.get('album', {}).get('name', ''),
            'artists': artists,
            'spotify_url': url,
        })
        if len(results) >= 5:
            break
    return results


def _normalize_name(name):
    """Normalize a track name for fuzzy comparison."""
    import unicodedata
    s = name.lower().strip()
    s = unicodedata.normalize('NFKD', s)
    # Strip parenthetical suffixes like (feat. X), (Remix), (Inst.)
    s = re.sub(r'\s*\(.*?\)', '', s)
    # Strip common punctuation
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def auto_populate_links(artist_name, songs, spotify_url=None,
                        on_progress=None, cancel=None):
    """Match songs to Spotify tracks using discography-first, then search fallback.

    artist_name: str
    songs: list of dicts with keys 'id' and 'name'
    spotify_url: optional Spotify artist URL for discography fetch
    on_progress: optional callback(message, percent)
    cancel: optional threading.Event to abort

    Returns dict: {
        auto_matched: [{song_id, song_name, spotify_url}],
        needs_review: [{song_id, song_name, candidates: [{name, album, artists, spotify_url}]}],
        not_found: [{song_id, song_name}],
    }
    """
    _current_pct = [0]

    def _check():
        if cancel and cancel.is_set():
            raise _Cancelled('Cancelled')

    def _progress(msg, pct):
        _current_pct[0] = pct
        if on_progress:
            on_progress(msg, pct)

    if on_progress:
        _local.on_status = lambda msg: on_progress(msg, _current_pct[0])

    try:
        matched_by_link = []
        needs_review = []
        not_found = []

        # Build lookup of unmatched songs
        unmatched = {s['id']: s for s in songs}

        # Phase 1: Discography fetch (if Spotify artist URL provided)
        spotify_tracks = {}  # normalized_name -> spotify_url
        if spotify_url:
            _check()
            _progress('Fetching discography from Spotify...', 5)
            try:
                artist_id = _parse_id(spotify_url, 'artist')
                # Fetch all albums (paginated)
                albums_raw = []
                offset = 0
                while True:
                    _check()
                    page = _api_get(f'/artists/{artist_id}/albums?include_groups=album,single&limit=10&offset={offset}')
                    items = page.get('items', [])
                    albums_raw.extend(items)
                    _progress(f'Scanning discography... ({len(albums_raw)} albums)', 10)
                    if not items or not page.get('next'):
                        break
                    offset += len(items)

                albums_raw = [a for a in albums_raw if a and a.get('id')]
                total_albums = len(albums_raw)

                for idx, raw in enumerate(albums_raw):
                    _check()
                    pct = 10 + int(40 * ((idx + 1) / max(total_albums, 1)))
                    _progress(f'Loading album tracks ({idx + 1} of {total_albums})', pct)
                    try:
                        full = _api_get(f'/albums/{raw["id"]}')
                    except SpotifyError:
                        continue
                    for t in full.get('tracks', {}).get('items', []):
                        url = t.get('external_urls', {}).get('spotify', '')
                        if url:
                            norm = _normalize_name(t['name'])
                            if norm not in spotify_tracks:
                                track_artists = ', '.join(a['name'] for a in t.get('artists', []))
                                spotify_tracks[norm] = {'spotify_url': url, 'artists': track_artists}

                # Match songs against discography
                _progress('Matching songs to discography...', 55)
                matched_ids = []
                for song_id, song in list(unmatched.items()):
                    norm = _normalize_name(song['name'])
                    if norm in spotify_tracks:
                        match = spotify_tracks[norm]
                        matched_by_link.append({
                            'song_id': song_id,
                            'song_name': song['name'],
                            'spotify_url': match['spotify_url'],
                            'artists': match['artists'],
                        })
                        matched_ids.append(song_id)
                for sid in matched_ids:
                    del unmatched[sid]

                _progress(f'Discography matched {len(matched_by_link)} of {len(songs)} songs', 58)

            except SpotifyError as e:
                _progress(f'Discography fetch failed ({e}), falling back to search...', 58)

        # Phase 2: Search fallback for remaining unmatched songs
        remaining = list(unmatched.values())
        total_remaining = len(remaining)
        for idx, song in enumerate(remaining):
            _check()
            pct = 60 + int(35 * ((idx + 1) / max(total_remaining, 1)))
            _progress(f'Searching ({idx + 1} of {total_remaining}): {song["name"]}', pct)
            try:
                candidates = search_track(song['name'], artist_name)
            except SpotifyError:
                candidates = []

            if not candidates:
                not_found.append({'song_id': song['id'], 'song_name': song['name']})
                continue

            needs_review.append({
                'song_id': song['id'],
                'song_name': song['name'],
                'candidates': candidates,
            })

        _progress('Done!', 100)
        return {
            'matched_by_link': matched_by_link,
            'needs_review': needs_review,
            'not_found': not_found,
        }
    finally:
        _local.on_status = None


class SpotifyError(Exception):
    """Raised for any Spotify API or configuration error."""
    pass
