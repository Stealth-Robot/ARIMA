import json
import time
import uuid
import logging
import threading

from flask import request, session, abort, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist, Song, ArtistSong
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

    # Collect songs without spotify_url for this artist
    links = ArtistSong.query.filter_by(artist_id=artist_id).all()
    song_ids = [l.song_id for l in links]
    songs_to_process = []
    for sid in song_ids:
        song = db.session.get(Song, sid)
        if song and not song.spotify_url:
            songs_to_process.append({'id': song.id, 'name': song.name})

    if not songs_to_process:
        return jsonify({'error': 'All songs already have Spotify links'}), 400

    artist_name = artist.name

    from app.services.spotify import auto_populate_links

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
            result = auto_populate_links(
                artist_name, songs_to_process,
                spotify_url=spotify_url,
                on_progress=on_progress,
                cancel=cancel,
            )
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

    Expects JSON body: {selections: [{song_id, spotify_url}, ...]}
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

    db.session.commit()
    return jsonify({'saved': count})
