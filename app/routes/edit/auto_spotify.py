import json
import time
import uuid
import logging
import threading

from flask import request, session, abort, jsonify, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong
from app.services.audit import log_change
from app.decorators import role_required, EDITOR_OR_ADMIN

from app.routes.edit import edit_bp, _require_edit_mode

logger = logging.getLogger(__name__)

_auto_spotify_jobs = {}
_auto_spotify_cancels = {}
_JOB_TTL = 600  # 10 minutes (review phase can take a while)


def _sweep_old_jobs():
    now = time.time()
    stale = [k for k, v in _auto_spotify_jobs.items() if now - v.get('_ts', 0) > _JOB_TTL]
    for k in stale:
        _auto_spotify_jobs.pop(k, None)


@edit_bp.route('/artist/<int:artist_id>/auto-spotify', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def auto_spotify_start(artist_id):
    """Start auto-populating Spotify links for an artist's songs."""
    _require_edit_mode()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)

    spotify_url = request.form.get('spotify_url', '').strip() or None

    # Collect songs without spotify_url for this artist, plus a few existing
    # linked track URLs we can use to auto-detect the artist's Spotify page.
    links = ArtistSong.query.filter_by(artist_id=artist_id).all()
    song_ids = [l.song_id for l in links]
    songs_to_process = []
    linked_track_urls = []
    for sid in song_ids:
        song = db.session.get(Song, sid)
        if not song:
            continue
        if song.spotify_url:
            if '/track/' in song.spotify_url and len(linked_track_urls) < 8:
                linked_track_urls.append(song.spotify_url)
        else:
            songs_to_process.append({'id': song.id, 'name': song.name})

    # Proceed as long as there's something to do: songs to link, a pasted URL,
    # or a linked track we can derive the artist/album links from.
    if not songs_to_process and not spotify_url and not linked_track_urls:
        return jsonify({'error': 'All songs already have Spotify links'}), 400

    artist_name = artist.name

    from app.services.spotify import (
        auto_populate_links, artist_url_from_track, _normalize_name,
        SpotifyError)

    app = current_app._get_current_object()

    _sweep_old_jobs()

    user_id = current_user.id
    old_cancel = _auto_spotify_cancels.pop(user_id, None)
    if old_cancel:
        old_cancel.set()

    job_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    _auto_spotify_cancels[user_id] = cancel
    _auto_spotify_jobs[job_id] = {
        'progress': 'Starting...', 'percent': 0, '_ts': time.time(),
    }

    def on_progress(msg, pct):
        _auto_spotify_jobs[job_id] = {
            'progress': msg, 'percent': pct, '_ts': time.time(),
        }

    def run():
        try:
            resolved_url = spotify_url
            if not resolved_url and linked_track_urls:
                on_progress('Detecting artist from existing links...', 2)
                for turl in linked_track_urls:
                    if cancel.is_set():
                        break
                    try:
                        cand = artist_url_from_track(turl, expected_name=artist_name)
                    except SpotifyError:
                        cand = None
                    if cand:
                        resolved_url = cand
                        break
            result = auto_populate_links(
                artist_name, songs_to_process,
                spotify_url=resolved_url,
                on_progress=on_progress,
                cancel=cancel,
            )

            # Resolve artist + album links against the local DB so the review
            # modal can list exactly what will change (only where empty).
            with app.app_context():
                artist_obj = db.session.get(Artist, artist_id)
                a_url = result.get('artist_spotify_url')
                if artist_obj and a_url and not artist_obj.spotify_url:
                    result['artist_link'] = {
                        'artist_id': artist_id,
                        'name': artist_obj.name,
                        'spotify_url': a_url,
                    }
                else:
                    result['artist_link'] = None

                album_links = result.get('album_links') or {}
                album_matches = []
                if album_links:
                    # An artist's albums are primarily linked through their
                    # songs (album.artist_id is usually NULL); mirror the
                    # discography query so song-associated albums are included.
                    albums = []
                    seen_ids = set()
                    if song_ids:
                        albums = (db.session.query(Album)
                                  .join(AlbumSong,
                                        Album.id == AlbumSong.album_id)
                                  .filter(AlbumSong.song_id.in_(song_ids))
                                  .distinct().all())
                        seen_ids = {a.id for a in albums}
                    direct = (db.session.query(Album)
                              .filter(Album.artist_id == artist_id,
                                      ~Album.id.in_(seen_ids)
                                      if seen_ids else db.true())
                              .all())
                    albums.extend(direct)
                    for album in albums:
                        if album.spotify_url:
                            continue
                        url = album_links.get(_normalize_name(album.name))
                        if url:
                            album_matches.append({
                                'album_id': album.id,
                                'name': album.name,
                                'spotify_url': url,
                            })
                result['album_matches'] = album_matches
                result.pop('album_links', None)
                result.pop('artist_spotify_url', None)

            _auto_spotify_jobs[job_id] = {
                'done': True,
                'data': result,
                '_ts': time.time(),
            }
        except Exception as e:
            if not cancel.is_set():
                _auto_spotify_jobs[job_id] = {
                    'error': str(e) or 'Auto-populate failed',
                    '_ts': time.time(),
                }
        finally:
            _auto_spotify_cancels.pop(user_id, None)
            if cancel.is_set():
                _auto_spotify_jobs.pop(job_id, None)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'job_id': job_id, 'total_songs': len(songs_to_process)})


@edit_bp.route('/auto-spotify/progress')
@login_required
@role_required(EDITOR_OR_ADMIN)
def auto_spotify_progress():
    """Poll progress of an auto-spotify job."""
    job_id = request.args.get('job_id', '')
    job = _auto_spotify_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Unknown job'}), 404
    return jsonify({k: v for k, v in job.items() if k != '_ts'})


@edit_bp.route('/auto-spotify/confirm', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def auto_spotify_confirm():
    """Save confirmed Spotify URL selections.

    Expects JSON body:
      {selections: [{song_id, spotify_url}, ...],
       artist_link: {artist_id, spotify_url} | null,
       album_selections: [{album_id, spotify_url}, ...]}

    Every entry is an explicit, user-reviewed selection and is applied only
    where the target currently has no link (never overwriting).
    """
    data = request.get_json(silent=True)
    if not data or 'selections' not in data:
        abort(400)

    count = 0
    for sel in data['selections']:
        song_id = sel.get('song_id')
        spotify_url = sel.get('spotify_url', '').strip()
        if not song_id or not spotify_url:
            continue
        if not spotify_url.startswith('https://'):
            continue
        song = db.session.get(Song, song_id)
        if not song:
            continue
        if song.spotify_url:
            continue  # don't overwrite existing
        song.spotify_url = spotify_url
        log_change(current_user, f'Auto-linked Spotify to "{song.name}"',
                   song=song, change_type='link')
        count += 1

    artist_count = 0
    album_count = 0

    art = data.get('artist_link')
    if art and (art.get('spotify_url') or '').startswith('https://'):
        artist = db.session.get(Artist, art.get('artist_id'))
        if artist and not artist.spotify_url:
            artist.spotify_url = art['spotify_url']
            log_change(current_user, f'Auto-linked Spotify to "{artist.name}"',
                       artist=artist, change_type='link')
            artist_count += 1

    for sel in data.get('album_selections', []):
        url = (sel.get('spotify_url') or '').strip()
        if not url.startswith('https://'):
            continue
        album = db.session.get(Album, sel.get('album_id'))
        if album and not album.spotify_url:
            album.spotify_url = url
            log_change(current_user, f'Auto-linked Spotify to "{album.name}" album',
                       album=album, change_type='link')
            album_count += 1

    db.session.commit()
    return jsonify({'saved': count, 'artist_saved': artist_count,
                    'albums_saved': album_count})
