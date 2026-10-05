from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.lookups import Genre, GroupGender
from app.models.music import (Artist, ArtistSong, AlbumSong, Album, Song, Rating,
                               song_genres, SongMiscArtist, MiscArtist)
from app.models.user import User
from app.routes.home import _pick_canonical_album, GENDER_CSS

group_picks_bp = Blueprint('group_picks', __name__)


def _int_list(name):
    out = []
    for v in request.args.getlist(name):
        try:
            out.append(int(v))
        except ValueError:
            pass
    return out


def _int_arg(name):
    try:
        return int(request.args.get(name, '').strip())
    except ValueError:
        return None


def _album_year(album):
    d = album.release_date or ''
    return int(d[:4]) if len(d) >= 4 and d[:4].isdigit() else None


def _parse_filters():
    candidates = User.query.filter(User.sort_order.isnot(None), User.id != current_user.id) \
        .order_by(User.sort_order).all()
    candidate_ids = {u.id for u in candidates}
    return candidates, {
        'user_ids': [uid for uid in _int_list('user_id') if uid in candidate_ids],
        'match': 'all' if request.args.get('match') == 'all' else 'any',
        'genre_ids': _int_list('genre_id'),
        'gender_ids': _int_list('gender_id'),
        'year_from': _int_arg('year_from'),
        'year_to': _int_arg('year_to'),
        'sort': request.args.get('sort') if request.args.get('sort') in SORTS else 'artist',
        'dir': 'desc' if request.args.get('dir') == 'desc' else 'asc',
    }


SORTS = {'artist': 'Artist name', 'year': 'Year', 'score': 'Avg artist score', 'unrated': 'Unrated songs'}


def _artist_scores(keys):
    """Global Stats average score per artist key (misc artists have none)."""
    from app.cache import get_cached_bulk_data
    from app.routes.stats import _get_viewer_settings
    from app.services.stats import get_display_users, get_artist_score_stats
    settings = _get_viewer_settings()
    settings.pop('country_ids')
    bulk = get_cached_bulk_data(**settings)
    users = get_display_users()
    return {k: get_artist_score_stats(int(k[1:]), users, bulk)['global_avg']
            for k in keys if k.startswith('a')}


def _sort_results(grouped, f):
    """Order artists by the chosen sort; entries missing a value always go last."""
    desc = f['dir'] == 'desc'
    if f['sort'] == 'artist':
        grouped.sort(key=lambda p: p[0]['name'].lower(), reverse=desc)
        return grouped
    if f['sort'] == 'unrated':
        values = {p[0]['key']: p[1][0] for p in grouped}
    elif f['sort'] == 'year':
        pick = max if desc else min
        values = {}
        for info, (_, album_list) in grouped:
            years = [y for y in (_album_year(a) for a, _ in album_list if a) if y is not None]
            values[info['key']] = pick(years) if years else None
    else:
        values = _artist_scores([p[0]['key'] for p in grouped])
    grouped.sort(key=lambda p: p[0]['name'].lower())
    present = [p for p in grouped if values.get(p[0]['key']) is not None]
    missing = [p for p in grouped if values.get(p[0]['key']) is None]
    present.sort(key=lambda p: values[p[0]['key']], reverse=desc)
    return present + missing


def _build_results(f, only_key=None):
    """Return [(info, (count, [(album, [songs])]))] for songs the group rated and I haven't."""
    q = db.session.query(Rating.song_id).filter(
        Rating.user_id.in_(f['user_ids']), Rating.rating.isnot(None)).group_by(Rating.song_id)
    if f['match'] == 'all':
        q = q.having(func.count(func.distinct(Rating.user_id)) == len(f['user_ids']))
    mine = db.session.query(Rating.song_id).filter(
        Rating.user_id == current_user.id, Rating.rating.isnot(None))
    song_ids = {r[0] for r in q.filter(~Rating.song_id.in_(mine)).all()}
    if not song_ids:
        return []

    artist_by_song = {}
    for sid, artist in (db.session.query(ArtistSong.song_id, Artist)
                        .join(Artist, Artist.id == ArtistSong.artist_id)
                        .filter(ArtistSong.song_id.in_(song_ids), ArtistSong.artist_is_main == True)
                        .order_by(Artist.id).all()):
        artist_by_song.setdefault(sid, artist)
    misc_by_song = {}
    for sid, misc in (db.session.query(SongMiscArtist.song_id, MiscArtist)
                      .join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id)
                      .filter(SongMiscArtist.song_id.in_(song_ids), SongMiscArtist.artist_is_main == True)
                      .order_by(MiscArtist.id).all()):
        if sid not in artist_by_song:
            misc_by_song.setdefault(sid, misc)

    def key_of(sid):
        if sid in artist_by_song:
            return f'a{artist_by_song[sid].id}'
        if sid in misc_by_song:
            return f'm{misc_by_song[sid].id}'
        return None

    song_ids = {sid for sid in song_ids if key_of(sid) and (only_key is None or key_of(sid) == only_key)}
    if not song_ids:
        return []

    albums_by_song = {}
    track_by_song_album = {}
    for sid, track, album in (db.session.query(AlbumSong.song_id, AlbumSong.track_number, Album)
                              .join(Album, Album.id == AlbumSong.album_id)
                              .options(selectinload(Album.genres), selectinload(Album.album_type),
                                       selectinload(Album.alt_names))
                              .filter(AlbumSong.song_id.in_(song_ids)).all()):
        albums_by_song.setdefault(sid, []).append(album)
        track_by_song_album[(sid, album.id)] = track

    song_genre_map = {}
    if f['genre_ids']:
        for sid, gid in db.session.execute(
                song_genres.select().where(song_genres.c.song_id.in_(song_ids))).fetchall():
            song_genre_map.setdefault(sid, set()).add(gid)

    genre_set = set(f['genre_ids'])
    gender_set = set(f['gender_ids'])
    year_from, year_to = f['year_from'], f['year_to']
    groups = {}
    for song in Song.query.options(selectinload(Song.aliases)).filter(Song.id.in_(song_ids)).all():
        artist = artist_by_song.get(song.id)
        misc = misc_by_song.get(song.id)
        song_albums = albums_by_song.get(song.id, [])

        if gender_set and (artist is None or artist.gender_id not in gender_set):
            continue
        if genre_set:
            genres = set(song_genre_map.get(song.id, set()))
            for a in song_albums:
                genres |= {g.id for g in a.genres}
            if not genres & genre_set:
                continue
        if year_from is not None or year_to is not None:
            years = [y for y in (_album_year(a) for a in song_albums) if y is not None]
            if not years:
                continue
            year = min(years)
            if (year_from is not None and year < year_from) or (year_to is not None and year > year_to):
                continue

        key = key_of(song.id)
        if artist is not None:
            info = {'name': artist.name, 'url': f'/artists/{artist.id}',
                    'gender_css': GENDER_CSS.get(artist.gender_id), 'key': key}
        else:
            info = {'name': misc.name, 'url': f'/misc?song={song.id}', 'gender_css': None, 'key': key}
        canonical = _pick_canonical_album(song_albums, artist.id if artist else None) if song_albums else None
        track = track_by_song_album.get((song.id, canonical.id), 0) if canonical else 0
        group = groups.setdefault(key, {'info': info, 'albums': {}})
        group['albums'].setdefault(canonical, []).append((song, track))

    grouped = []
    for group in groups.values():
        album_list = []
        for album, pairs in group['albums'].items():
            pairs.sort(key=lambda p: (p[1], p[0].name.lower()))
            album_list.append((album, [s for s, _ in pairs]))
        album_list.sort(key=lambda p: ((p[0].release_date or '') if p[0] else '',
                                       p[0].name.lower() if p[0] else ''),
                        reverse=f['sort'] == 'year' and f['dir'] == 'desc')
        # Album-less (misc) songs go last in either direction.
        album_list.sort(key=lambda p: p[0] is None)
        grouped.append((group['info'], (sum(len(s) for _, s in album_list), album_list)))
    return _sort_results(grouped, f)


def _columns(candidates, user_ids):
    selected = set(user_ids)
    return [current_user] + [u for u in candidates if u.id in selected]


@group_picks_bp.route('/group-picks')
@login_required
def group_picks():
    candidates, f = _parse_filters()
    results = _build_results(f) if f['user_ids'] else []
    ctx = dict(results=results, user_ids=f['user_ids'],
               query_string=request.query_string.decode())
    if request.headers.get('HX-Request'):
        return render_template('fragments/group_picks_results.html', **ctx)
    return render_template('group_picks.html', **ctx, **{k: v for k, v in f.items() if k != 'user_ids'},
                           candidates=candidates, sorts=SORTS,
                           genres=Genre.query.order_by(func.lower(Genre.genre)).all(),
                           genders=GroupGender.query.order_by(GroupGender.id).all())


@group_picks_bp.route('/group-picks/group/<key>')
@login_required
def group_picks_group(key):
    candidates, f = _parse_filters()
    if not f['user_ids']:
        abort(404)
    results = _build_results(f, only_key=key)
    if not results:
        return ''
    _, (_, album_groups) = results[0]
    song_ids = [s.id for _, songs in album_groups for s in songs]
    ratings_map = {}
    for r in Rating.query.filter(Rating.song_id.in_(song_ids)).all():
        ratings_map.setdefault(r.song_id, {})[r.user_id] = r
    return render_template('fragments/group_picks_group.html', album_groups=album_groups,
                           ratings=ratings_map, users=_columns(candidates, f['user_ids']))


@group_picks_bp.route('/group-picks/playlist', methods=['POST'])
@login_required
def group_picks_playlist():
    """Create a Spotify playlist from the first N songs in page order."""
    from datetime import datetime
    from app.services import spotify_oauth
    from app.services.spotify import to_app_uri
    _, f = _parse_filters()
    if not f['user_ids']:
        return jsonify({'error': 'Pick at least one person first.'}), 400
    if spotify_oauth.get_valid_access_token(current_user) is None:
        return jsonify({'error': 'not_connected'}), 400
    body = request.get_json(silent=True) or {}
    try:
        count = int(body.get('count'))
    except (TypeError, ValueError):
        count = 0
    if count < 1:
        return jsonify({'error': 'Enter how many songs to include.'}), 400

    uris = []
    skipped = 0
    for _, (_, album_groups) in _build_results(f):
        for _, songs in album_groups:
            for song in songs:
                uri = to_app_uri(song.spotify_url) if song.spotify_url else None
                # Linkless songs don't count toward N; the next song takes their place.
                if uri and uri.startswith('spotify:track:'):
                    uris.append(uri)
                else:
                    skipped += 1
                if len(uris) >= count:
                    break
            if len(uris) >= count:
                break
        if len(uris) >= count:
            break
    if not uris:
        return jsonify({'error': 'no_tracks'})

    name = (body.get('name') or '').strip()[:100] or \
        f'ARIMA - Group Picks - {datetime.now().strftime("%Y-%m-%d")}'
    try:
        url = spotify_oauth.create_playlist(current_user, name, uris, public=False)
    except spotify_oauth.SpotifyOAuthError as e:
        return jsonify({'error': str(e)}), 502
    settings = getattr(current_user, 'settings', None)
    return jsonify({
        'url': url,
        'app_uri': to_app_uri(url) if url else None,
        'open_in_app': getattr(settings, 'spotify_open_in_app', True) if settings else True,
        'added': len(uris),
        'skipped': skipped,
    })
