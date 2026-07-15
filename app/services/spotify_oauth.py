"""Spotify user OAuth (Authorization Code flow).

Lets a user link their personal Spotify account on the profile page. Tokens
are persisted on the User model so the connection survives logout; the access
token is refreshed transparently when it nears expiry.

Distinct from app.services.spotify, which uses the app-level Client
Credentials flow for catalog search/import (no user context).
"""

import os
import json
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
_API_BASE = 'https://api.spotify.com/v1'

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


def _raw_credentials(user=None):
    """OAuth-app credentials for this user.

    A user may be assigned a specific OAuth app via user.spotify_oauth_app: a
    suffix (e.g. '2') selecting SPOTIFY_OAUTH_CLIENT_ID_2/SECRET_2 in env. This
    lets a user connect through their own Spotify developer app. An assigned
    suffix does NOT fall back to the default app — a missing suffixed var is a
    misconfiguration, and silently using another app would break token refresh
    (refresh tokens are bound to the app that minted them).

    Unassigned users use the default SPOTIFY_OAUTH_CLIENT_ID/SECRET, which
    itself falls back to the catalog app's SPOTIFY_CLIENT_ID/SECRET.
    """
    suffix = (getattr(user, 'spotify_oauth_app', None) or '').strip()
    if suffix:
        return (os.environ.get(f'SPOTIFY_OAUTH_CLIENT_ID_{suffix}'),
                os.environ.get(f'SPOTIFY_OAUTH_CLIENT_SECRET_{suffix}'))
    cid = os.environ.get('SPOTIFY_OAUTH_CLIENT_ID') or os.environ.get('SPOTIFY_CLIENT_ID')
    secret = os.environ.get('SPOTIFY_OAUTH_CLIENT_SECRET') or os.environ.get('SPOTIFY_CLIENT_SECRET')
    return cid, secret


def is_configured(user=None):
    cid, secret = _raw_credentials(user)
    return bool(cid and secret)


def has_dedicated_oauth_app(user=None):
    """True if a real user-OAuth app is configured for this user (an assigned
    SPOTIFY_OAUTH_CLIENT_ID_<suffix>, or the default SPOTIFY_OAUTH_CLIENT_ID) —
    i.e. NOT the catalog SPOTIFY_CLIENT_ID fallback, which has no redirect URI
    and would fail Spotify's redirect_uri check. Used to gate the connect flow
    so unprovisioned users get guidance instead of a Spotify error page.
    """
    suffix = (getattr(user, 'spotify_oauth_app', None) or '').strip()
    if suffix:
        return bool(os.environ.get(f'SPOTIFY_OAUTH_CLIENT_ID_{suffix}')
                    and os.environ.get(f'SPOTIFY_OAUTH_CLIENT_SECRET_{suffix}'))
    return bool(os.environ.get('SPOTIFY_OAUTH_CLIENT_ID')
                and os.environ.get('SPOTIFY_OAUTH_CLIENT_SECRET'))


def _credentials(user=None):
    cid, secret = _raw_credentials(user)
    if not cid or not secret:
        raise SpotifyOAuthError('Spotify credentials not configured')
    return cid, secret


def _basic_auth_header(user=None):
    cid, secret = _credentials(user)
    token = base64.b64encode(f'{cid}:{secret}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def authorize_url(redirect_uri, state, user=None):
    cid, _ = _credentials(user)
    params = {
        'response_type': 'code',
        'client_id': cid,
        'scope': SCOPES,
        'redirect_uri': redirect_uri,
        'state': state,
        'show_dialog': 'true',
    }
    return f'{_AUTHORIZE_URL}?{urlencode(params)}'


def _token_request(data, user=None):
    try:
        resp = spotify_queue.request(
            'POST', _TOKEN_URL,
            headers=_basic_auth_header(user),
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


def exchange_code(code, redirect_uri, user=None):
    """Trade an authorization code for access + refresh tokens."""
    return _token_request({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }, user)


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


def _error_detail(resp):
    """Extract Spotify's error message from a Web API response, if any.

    Web API errors nest the message under `error.message` (the token endpoint
    uses a flat `error_description` instead). Returns a ': <msg>' suffix or ''.
    """
    try:
        err = (resp.json() or {}).get('error')
        msg = err.get('message') if isinstance(err, dict) else err
    except Exception:
        msg = None
    return f': {msg}' if msg else ''


def create_playlist(user, name, track_uris, public=False):
    """Create a playlist on the user's account and add the given track URIs.

    Returns the new playlist's web URL. Raises SpotifyOAuthError on failure.
    """
    token = get_valid_access_token(user)
    if not token:
        raise SpotifyOAuthError('Spotify account not connected')
    # ApiQueue only forwards data=, so JSON-encode the body and set the header.
    auth = {'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'}
    try:
        # Feb 2026 API change: POST /users/{id}/playlists was removed; the
        # current user's playlist is created via /me/playlists.
        resp = spotify_queue.request(
            'POST', f'{_API_BASE}/me/playlists',
            headers=auth,
            data=json.dumps({'name': name, 'public': public}),
            timeout=15,
        )
    except (ApiQueueError, RateLimitedError) as e:
        raise SpotifyOAuthError(f'Spotify playlist create failed: {e}')
    if resp.status_code not in (200, 201):
        raise SpotifyOAuthError(
            f'Spotify playlist create failed ({resp.status_code})'
            + _error_detail(resp))
    playlist = resp.json()
    playlist_id = playlist.get('id')
    # Spotify caps add-items at 100 URIs per request.
    for i in range(0, len(track_uris), 100):
        batch = track_uris[i:i + 100]
        try:
            # Feb 2026 API change: /playlists/{id}/tracks was renamed to
            # /playlists/{id}/items (body still takes {'uris': [...]}).
            add = spotify_queue.request(
                'POST', f'{_API_BASE}/playlists/{playlist_id}/items',
                headers=auth,
                data=json.dumps({'uris': batch}),
                timeout=15,
            )
        except (ApiQueueError, RateLimitedError) as e:
            raise SpotifyOAuthError(f'Spotify add-tracks failed: {e}')
        if add.status_code not in (200, 201):
            raise SpotifyOAuthError(
                f'Spotify add-tracks failed ({add.status_code})'
                + _error_detail(add))
    return (playlist.get('external_urls') or {}).get('spotify')


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
    }, user)
    user.spotify_access_token = token_data['access_token']
    if token_data.get('refresh_token'):
        user.spotify_refresh_token = token_data['refresh_token']
    user.spotify_token_expires_at = int(
        time.time() + token_data.get('expires_in', 3600))
    db.session.commit()
    return user.spotify_access_token
