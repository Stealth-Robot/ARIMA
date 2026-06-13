import os
import time
import uuid
import shutil
import threading

from flask import (Blueprint, request, render_template, redirect, url_for,
                   current_app, jsonify)
from flask_login import login_required, current_user

from sqlalchemy import func

from app.extensions import db
from app.models.lookups import Genre, Country
from app.decorators import role_required, ADMIN
from app.cache import clear_filter_cache

admin_bp = Blueprint('admin', __name__)

# In-memory bulk Spotify fill jobs (mirrors the per-artist auto-spotify flow).
_bulk_spotify_jobs = {}
_bulk_spotify_cancel = {}
_BULK_JOB_TTL = 1800  # 30 minutes


def _bulk_sweep():
    now = time.time()
    for k in [k for k, v in _bulk_spotify_jobs.items()
              if now - v.get('_ts', 0) > _BULK_JOB_TTL]:
        _bulk_spotify_jobs.pop(k, None)


@admin_bp.route('/admin')
@login_required
@role_required(ADMIN)
def admin_page():
    from app.services.billing import get_billing_cycles
    from app.models.music import Artist, Album
    genres = Genre.query.order_by(func.lower(Genre.genre)).all()
    countries = Country.query.order_by(func.lower(Country.country)).all()
    artists_missing = Artist.query.filter(
        db.or_(Artist.spotify_url.is_(None), Artist.spotify_url == '')).count()
    albums_missing = Album.query.filter(
        db.or_(Album.spotify_url.is_(None), Album.spotify_url == '')).count()
    return render_template('admin.html', genres=genres, countries=countries,
                           billing_cycles=get_billing_cycles(),
                           artists_missing=artists_missing,
                           albums_missing=albums_missing)


@admin_bp.route('/admin/billing-costs', methods=['POST'])
@login_required
@role_required(ADMIN)
def save_billing_costs():
    """Save the manually-entered real cost for each billing cycle."""
    from app.models.billing_cost import BillingCost
    for key, raw in request.form.items():
        if not key.startswith('cost_'):
            continue
        cycle_start = key[len('cost_'):]
        raw = raw.strip()
        if raw == '':
            continue
        existing = db.session.get(BillingCost, cycle_start)
        try:
            amount = float(raw)
        except ValueError:
            continue
        if existing:
            existing.amount = amount
        else:
            db.session.add(BillingCost(cycle_start=cycle_start, amount=amount))
    db.session.commit()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/add-genre', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_genre():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('admin.admin_page'))

    if Genre.query.filter(db.func.lower(Genre.genre) == name.lower()).first():
        return redirect(url_for('admin.admin_page'))

    max_id = db.session.query(db.func.max(Genre.id)).scalar() or -1
    db.session.add(Genre(id=max_id + 1, genre=name))
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/add-country', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_country():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('admin.admin_page'))

    if Country.query.filter(db.func.lower(Country.country) == name.lower()).first():
        return redirect(url_for('admin.admin_page'))

    max_id = db.session.query(db.func.max(Country.id)).scalar() or -1
    db.session.add(Country(id=max_id + 1, country=name))
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/delete-genre/<int:genre_id>', methods=['POST'])
@login_required
@role_required(ADMIN)
def delete_genre(genre_id):
    from app.routes.edit import _verify_password
    if not _verify_password():
        return 'Incorrect password', 403

    genre = db.session.get(Genre, genre_id)
    if genre is None:
        return 'Not found', 404

    # 'OST' is special-cased by name in filtering logic across the app
    if genre.genre == 'OST':
        return 'OST cannot be deleted', 400

    from app.models.music import song_genres, album_genres
    db.session.execute(song_genres.delete().where(song_genres.c.genre_id == genre.id))
    db.session.execute(album_genres.delete().where(album_genres.c.genre_id == genre.id))
    db.session.delete(genre)
    db.session.commit()
    clear_filter_cache()
    from app.cache import clear_stats_cache
    clear_stats_cache()
    return '', 200


@admin_bp.route('/admin/delete-country/<int:country_id>', methods=['POST'])
@login_required
@role_required(ADMIN)
def delete_country(country_id):
    from app.routes.edit import _verify_password
    if not _verify_password():
        return 'Incorrect password', 403

    country = db.session.get(Country, country_id)
    if country is None:
        return 'Not found', 404

    from app.models.music import Artist, MiscArtist
    in_use = (Artist.query.filter_by(country_id=country.id).first()
              or MiscArtist.query.filter_by(country_id=country.id).first())
    if in_use:
        return 'Country is still in use', 400

    db.session.delete(country)
    db.session.commit()
    clear_filter_cache()
    return '', 200


@admin_bp.route('/admin/rename-genre', methods=['POST'])
@login_required
@role_required(ADMIN)
def rename_genre():
    genre_id = request.form.get('id', '').strip()
    name = request.form.get('name', '').strip()
    if not genre_id or not name:
        return redirect(url_for('admin.admin_page'))

    genre = db.session.get(Genre, int(genre_id))
    if genre is None:
        return redirect(url_for('admin.admin_page'))

    # 'OST' is special-cased by name in filtering logic across the app; renaming it
    # would silently break those lookups, so it cannot be renamed.
    if genre.genre == 'OST':
        return redirect(url_for('admin.admin_page'))

    if name.lower() != genre.genre.lower() and Genre.query.filter(
        db.func.lower(Genre.genre) == name.lower(), Genre.id != genre.id
    ).first():
        return redirect(url_for('admin.admin_page'))

    genre.genre = name
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/rename-country', methods=['POST'])
@login_required
@role_required(ADMIN)
def rename_country():
    country_id = request.form.get('id', '').strip()
    name = request.form.get('name', '').strip()
    if not country_id or not name:
        return redirect(url_for('admin.admin_page'))

    country = db.session.get(Country, int(country_id))
    if country is None:
        return redirect(url_for('admin.admin_page'))

    if name.lower() != country.country.lower() and Country.query.filter(
        db.func.lower(Country.country) == name.lower(), Country.id != country.id
    ).first():
        return redirect(url_for('admin.admin_page'))

    country.country = name
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/replace-database', methods=['GET', 'POST'])
@login_required
@role_required(ADMIN)
def replace_database():
    """Replace the SQLite database file with an uploaded one."""
    if request.method == 'GET':
        return render_template('replace_database.html')

    from app.routes.edit import _verify_password
    if not _verify_password():
        return 'Incorrect password', 403

    uploaded = request.files.get('database')
    if not uploaded or not uploaded.filename.endswith('.db'):
        return 'No valid .db file uploaded', 400

    header = uploaded.read(16)
    uploaded.seek(0)
    if header[:16] != b'SQLite format 3\x00':
        return 'File is not a valid SQLite database', 400

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    if not db_path.startswith('/'):
        db_path = os.path.join(current_app.instance_path, db_path)

    db.session.remove()
    db.engine.dispose()

    if os.path.exists(db_path):
        shutil.copy2(db_path, db_path + '.bak')

    uploaded.save(db_path)

    for ext in ('-wal', '-shm'):
        wal_path = db_path + ext
        if os.path.exists(wal_path):
            os.remove(wal_path)

    return redirect(url_for('home.home'))


@admin_bp.route('/admin/bump-globe-ratings', methods=['POST'])
@login_required
@role_required(ADMIN)
def bump_globe_ratings():
    """Change user Globe's 3/5 ratings to 4/5.

    A song is skipped (left at 3/5) when Globe's note for it contains both the
    words "not" and "playlist" (whole words, case-insensitive) — those are his
    explicit "a 3, but not a playlist add" calls and should stay a 3.
    """
    import re
    from app.models.music import Rating
    from app.models.user import User
    from app.services.audit import log_change
    from app.cache import clear_stats_cache

    globe = User.query.filter(db.func.lower(User.username) == 'globe').first()
    if globe is None:
        return jsonify({'error': 'User Globe not found'}), 404

    has_not = re.compile(r'\bnot\b', re.IGNORECASE)
    has_playlist = re.compile(r'\bplaylist\b', re.IGNORECASE)

    updated = 0
    skipped = 0
    for r in Rating.query.filter_by(user_id=globe.id, rating=3).all():
        note = r.note or ''
        if has_not.search(note) and has_playlist.search(note):
            skipped += 1
            continue
        r.rating = 4
        updated += 1

    if updated:
        log_change(current_user,
                   f"Changed {updated} of Globe's song ratings from 3/5 to 4/5 "
                   f"(skipped {skipped} \"not playlist\" notes)",
                   change_type='rating')

    db.session.commit()
    clear_stats_cache()
    return jsonify({'updated': updated, 'skipped': skipped})


@admin_bp.route('/admin/bulk-spotify', methods=['POST'])
@login_required
@role_required(ADMIN)
def bulk_spotify_start():
    """Bulk-fill Spotify links for artists (by name) and their albums.

    For each artist still missing a link (up to `limit`), search Spotify by
    name and apply the link only on an exact normalized-name match. When an
    artist is matched, walk its discography and fill that artist's albums
    that match by name. Nothing is overwritten; ambiguous names are skipped.
    """
    from app.models.music import Artist, Album, ArtistSong, AlbumSong
    from app.models.user import User
    from app.services.audit import log_change
    from app.services.spotify import (
        find_artist_url, artist_album_links, _normalize_name, SpotifyError,
        SpotifyRateLimited, cooldown_remaining, cooldown_message)

    # Fail fast if Spotify already has us in a long cooldown.
    remaining = cooldown_remaining()
    if remaining > 120:
        return jsonify({'error': cooldown_message(remaining)}), 429

    try:
        limit = int(request.form.get('limit', 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 500))

    try:
        offset = int(request.form.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    artist_ids = [a.id for a in Artist.query.filter(
        db.or_(Artist.spotify_url.is_(None), Artist.spotify_url == '')
    ).order_by(func.lower(Artist.name)).offset(offset).limit(limit).all()]

    if not artist_ids:
        return jsonify({'error': 'No artists are missing Spotify links'}), 400

    app = current_app._get_current_object()
    user_id = current_user.id
    _bulk_sweep()

    old = _bulk_spotify_cancel.pop(user_id, None)
    if old:
        old.set()

    job_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    _bulk_spotify_cancel[user_id] = cancel
    _bulk_spotify_jobs[job_id] = {'progress': 'Starting...', 'percent': 0,
                                  '_ts': time.time()}

    def on_progress(msg, pct):
        _bulk_spotify_jobs[job_id] = {'progress': msg, 'percent': pct,
                                      '_ts': time.time()}

    def _albums_for_artist(aid):
        """Albums belonging to an artist via their songs, plus any directly
        linked via artist_id (mirrors the discography query)."""
        song_ids = [r.song_id for r in
                    ArtistSong.query.filter_by(artist_id=aid).all()]
        albums = []
        seen = set()
        if song_ids:
            albums = (db.session.query(Album)
                      .join(AlbumSong, Album.id == AlbumSong.album_id)
                      .filter(AlbumSong.song_id.in_(song_ids))
                      .distinct().all())
            seen = {a.id for a in albums}
        direct = (db.session.query(Album).filter(
            Album.artist_id == aid,
            ~Album.id.in_(seen) if seen else db.true()).all())
        albums.extend(direct)
        return albums

    def run():
        with app.app_context():
            user = db.session.get(User, user_id)
            stats = {'artists_filled': 0, 'artists_skipped': 0,
                     'albums_filled': 0, 'total': len(artist_ids)}
            try:
                for i, aid in enumerate(artist_ids):
                    if cancel.is_set():
                        break
                    artist = db.session.get(Artist, aid)
                    if not artist or (artist.spotify_url or '').strip():
                        continue
                    on_progress(f'({i + 1}/{len(artist_ids)}) {artist.name}',
                                int(100 * (i / max(len(artist_ids), 1))))
                    try:
                        match = find_artist_url(artist.name)
                    except SpotifyRateLimited as e:
                        db.session.commit()
                        _bulk_spotify_jobs[job_id] = {
                            'error': str(e), '_ts': time.time()}
                        return
                    except SpotifyError:
                        match = None
                    if not match:
                        stats['artists_skipped'] += 1
                        continue

                    artist.spotify_url = match['url']
                    log_change(user, f'Auto-linked Spotify to "{artist.name}"',
                               artist=artist, change_type='link')
                    stats['artists_filled'] += 1

                    try:
                        links = artist_album_links(match['id'], cancel=cancel)
                    except SpotifyRateLimited as e:
                        db.session.commit()
                        _bulk_spotify_jobs[job_id] = {
                            'error': str(e), '_ts': time.time()}
                        return
                    except SpotifyError:
                        links = {}
                    for album in _albums_for_artist(aid) if links else []:
                        if (album.spotify_url or '').strip():
                            continue
                        url = links.get(_normalize_name(album.name))
                        if url:
                            album.spotify_url = url
                            log_change(
                                user,
                                f'Auto-linked Spotify to "{album.name}" album',
                                album=album, artist=artist, change_type='link')
                            stats['albums_filled'] += 1

                    db.session.commit()

                stats['cancelled'] = cancel.is_set()
                _bulk_spotify_jobs[job_id] = {'done': True, 'data': stats,
                                              '_ts': time.time()}
            except Exception as e:
                db.session.rollback()
                _bulk_spotify_jobs[job_id] = {
                    'error': str(e) or 'Bulk fill failed', '_ts': time.time()}
            finally:
                _bulk_spotify_cancel.pop(user_id, None)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'job_id': job_id, 'total': len(artist_ids)})


@admin_bp.route('/admin/bulk-spotify/progress')
@login_required
@role_required(ADMIN)
def bulk_spotify_progress():
    job = _bulk_spotify_jobs.get(request.args.get('job_id', ''))
    if not job:
        return jsonify({'error': 'Unknown job'}), 404
    return jsonify({k: v for k, v in job.items() if k != '_ts'})
