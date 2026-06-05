"""Spotify user OAuth (Authorization Code flow).

Lets a user link their personal Spotify account on the profile page. Tokens
are persisted on the User model so the connection survives logout; the access
token is refreshed transparently when it nears expiry.

Distinct from app.services.spotify, which uses the app-level Client
Credentials flow for catalog search/import (no user context).
"""

import os
import time
import base64
import logging
from urllib.parse import urlencode

from app.extensions import db
from app.services.api_queue import (
    spotify_queue, ApiQueueError, RateLimitedError)

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = 'https://accounts.spotify.com/authorize'
_TOKEN_URL = 'https://accounts.spotify.com/api/token'
_ME_URL = 'https://api.spotify.com/v1/me'

# Broad scope set: view account, read/modify library + playlists, and control
# playback. Spotify only grants what the user approves on the consent screen.
SCOPES = ' '.join([
    'user-read-private',
    'user-read-email',
    'playlist-read-private',
    'playlist-read-collaborative',
    'playlist-modify-public',
    'playlist-modify-private',
    'ugc-image-upload',
    'user-library-read',
    'user-library-modify',
    'user-top-read',
    'user-read-recently-played',
    'user-read-playback-state',
    'user-modify-playback-state',
    'user-read-currently-playing',
    'user-follow-read',
    'user-follow-modify',
])


class SpotifyOAuthError(Exception):
    pass


def _raw_credentials():
    """OAuth-app credentials, falling back to the main app's if unset.

    Lets you run a separate Spotify app for user OAuth (SPOTIFY_OAUTH_CLIENT_ID/
    SECRET) than the one used for catalog API calls (SPOTIFY_CLIENT_ID/SECRET).
    """
    cid = os.environ.get('SPOTIFY_OAUTH_CLIENT_ID') or os.environ.get('SPOTIFY_CLIENT_ID')
    secret = os.environ.get('SPOTIFY_OAUTH_CLIENT_SECRET') or os.environ.get('SPOTIFY_CLIENT_SECRET')
    return cid, secret


def is_configured():
    cid, secret = _raw_credentials()
    return bool(cid and secret)


def _credentials():
    cid, secret = _raw_credentials()
    if not cid or not secret:
        raise SpotifyOAuthError('Spotify credentials not configured')
    return cid, secret


def _basic_auth_header():
    cid, secret = _credentials()
    token = base64.b64encode(f'{cid}:{secret}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def authorize_url(redirect_uri, state):
    cid, _ = _credentials()
    params = {
        'response_type': 'code',
        'client_id': cid,
        'scope': SCOPES,
        'redirect_uri': redirect_uri,
        'state': state,
        'show_dialog': 'true',
    }
    return f'{_AUTHORIZE_URL}?{urlencode(params)}'


def _token_request(data):
    try:
        resp = spotify_queue.request(
            'POST', _TOKEN_URL,
            headers=_basic_auth_header(),
            data=data,
            timeout=10,
        )
    except RateLimitedError as e:
        raise SpotifyOAuthError(str(e))
    except ApiQueueError as e:
        raise SpotifyOAuthError(f'Spotify token request failed: {e}')
    if resp.status_code != 200:
        detail = ''
        try:
            body = resp.json()
            detail = body.get('error_description') or body.get('error') or ''
        except Exception:
            pass
        raise SpotifyOAuthError(
            f'Spotify token request failed ({resp.status_code})'
            + (f': {detail}' if detail else ''))
    return resp.json()


def exchange_code(code, redirect_uri):
    """Trade an authorization code for access + refresh tokens."""
    return _token_request({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    })


def fetch_me(access_token):
    """Fetch the linked account's profile (id, display name, avatar)."""
    try:
        resp = spotify_queue.request(
            'GET', _ME_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
    except (ApiQueueError, RateLimitedError) as e:
        raise SpotifyOAuthError(f'Spotify profile request failed: {e}')
    if resp.status_code != 200:
        raise SpotifyOAuthError(
            f'Spotify profile request failed ({resp.status_code})')
    data = resp.json()
    images = data.get('images') or []
    return {
        'id': data.get('id'),
        'display_name': data.get('display_name') or data.get('id'),
        'image': images[0]['url'] if images else None,
    }


def store_connection(user, token_data, profile):
    """Persist token + account info from a fresh authorization on the user."""
    user.spotify_user_id = profile.get('id')
    user.spotify_display_name = profile.get('display_name')
    user.spotify_image = profile.get('image')
    user.spotify_access_token = token_data['access_token']
    # A refresh token is only returned on the initial authorization.
    if token_data.get('refresh_token'):
        user.spotify_refresh_token = token_data['refresh_token']
    user.spotify_token_expires_at = int(
        time.time() + token_data.get('expires_in', 3600))
    db.session.commit()


def disconnect(user):
    user.spotify_user_id = None
    user.spotify_display_name = None
    user.spotify_image = None
    user.spotify_access_token = None
    user.spotify_refresh_token = None
    user.spotify_token_expires_at = None
    db.session.commit()


def get_valid_access_token(user):
    """Return a usable access token for the user, refreshing if near expiry.

    Returns None if the user isn't connected. Raises SpotifyOAuthError if a
    refresh is needed but fails (e.g. revoked access).
    """
    if not user.spotify_refresh_token:
        return None
    expires_at = user.spotify_token_expires_at or 0
    if user.spotify_access_token and time.time() < expires_at - 60:
        return user.spotify_access_token
    token_data = _token_request({
        'grant_type': 'refresh_token',
        'refresh_token': user.spotify_refresh_token,
    })
    user.spotify_access_token = token_data['access_token']
    if token_data.get('refresh_token'):
        user.spotify_refresh_token = token_data['refresh_token']
    user.spotify_token_expires_at = int(
        time.time() + token_data.get('expires_in', 3600))
    db.session.commit()
    return user.spotify_access_token
