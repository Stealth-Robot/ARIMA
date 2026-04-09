"""Spotify Web API integration using Client Credentials flow."""

import os
import re
import time
import logging

import requests

logger = logging.getLogger(__name__)

_BASE = 'https://api.spotify.com/v1'
_TOKEN_URL = 'https://accounts.spotify.com/api/token'

# Module-level token cache
_access_token = None
_token_expires_at = 0


def _get_credentials():
    """Return (client_id, client_secret) or raise if not configured."""
    cid = os.environ.get('SPOTIFY_CLIENT_ID')
    secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not cid or not secret:
        raise SpotifyError('Spotify credentials not configured')
    return cid, secret


def _get_token():
    """Get a valid access token, refreshing if expired."""
    global _access_token, _token_expires_at
    if _access_token and time.time() < _token_expires_at - 60:
        return _access_token
    cid, secret = _get_credentials()
    resp = requests.post(_TOKEN_URL, data={'grant_type': 'client_credentials'},
                         auth=(cid, secret), timeout=10)
    if resp.status_code != 200:
        raise SpotifyError(f'Token request failed: {resp.status_code}')
    data = resp.json()
    _access_token = data['access_token']
    _token_expires_at = time.time() + data.get('expires_in', 3600)
    return _access_token


def _api_get(path_or_url):
    """GET from Spotify API with auth header. Accepts a path or full URL."""
    token = _get_token()
    url = path_or_url if path_or_url.startswith('http') else f'{_BASE}{path_or_url}'
    resp = requests.get(url,
                        headers={'Authorization': f'Bearer {token}'},
                        timeout=15)
    if resp.status_code == 404:
        raise SpotifyError('Not found on Spotify')
    if resp.status_code != 200:
        raise SpotifyError(f'Spotify API error: {resp.status_code}')
    return resp.json()


def _parse_id(url, kind):
    """Extract a Spotify ID from a URL. kind is 'album' or 'artist'."""
    # https://open.spotify.com/album/ABC123?si=xyz
    # https://open.spotify.com/artist/ABC123?si=xyz
    m = re.search(rf'open\.spotify\.com/{kind}/([A-Za-z0-9]+)(?:[/?]|$)', url)
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


def fetch_artist(url):
    """Fetch artist name + full discography from a Spotify artist URL.

    Returns dict: {name, albums: [{name, release_date, album_type_id, tracks: [{name, track_number}]}]}
    """
    artist_id = _parse_id(url, 'artist')
    artist_data = _api_get(f'/artists/{artist_id}')

    # Fetch all albums (paginated, follow next URLs)
    albums_raw = []
    next_url = f'/artists/{artist_id}/albums?include_groups=album,single'
    while next_url:
        page = _api_get(next_url)
        albums_raw.extend(page.get('items', []))
        next_url = page.get('next')

    # Fetch full track listings for each album
    albums = []
    for a in albums_raw:
        try:
            full = _api_get(f'/albums/{a["id"]}')
            tracks = [{'name': t['name'], 'track_number': t['track_number'],
                       'spotify_url': t.get('external_urls', {}).get('spotify', '')}
                      for t in full.get('tracks', {}).get('items', [])]
            albums.append({
                'name': full['name'],
                'release_date': _normalize_date(full.get('release_date', '')),
                'album_type_id': _album_type_id(full.get('album_type', ''), full.get('total_tracks', 0)),
                'tracks': tracks,
            })
        except SpotifyError:
            logger.warning('Failed to fetch album %s, skipping', a.get('id'))
            continue

    return {
        'name': artist_data['name'],
        'albums': albums,
    }


def _normalize_date(date_str):
    """Normalize Spotify dates (YYYY, YYYY-MM, YYYY-MM-DD) to YYYY-MM-DD."""
    if not date_str:
        return ''
    if re.fullmatch(r'\d{4}', date_str):
        return f'{date_str}-01-01'
    if re.fullmatch(r'\d{4}-\d{2}', date_str):
        return f'{date_str}-01'
    return date_str


class SpotifyError(Exception):
    """Raised for any Spotify API or configuration error."""
    pass
