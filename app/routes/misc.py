import json
from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, session, abort, jsonify
from flask_login import login_required, current_user

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.music import (
    Song, Album, Rating, AlbumSong, ArtistSong, MiscArtist, SongMiscArtist,
    song_genres, album_genres, Artist,
)
from app.models.lookups import Country, Genre, AlbumType
from app.models.user import User
from app.models.rules import Rules
from app.services.artist import get_filtered_navbar
from app.services.dates import is_valid_release_date

misc_bp = Blueprint('misc', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}


def _get_user_filters():
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        s = current_user.settings
        return {
            'country_ids': list(s.country_ids or []),
            'genre_ids': list(s.genre_ids or []),
            'include_remixes': s.include_remixes,
            'include_featured': s.include_featured,
            'include_covers': s.include_covers,
            'hide_osts': getattr(s, 'hide_osts', False),
        }
    return {
        'country_ids': list(session.get('country_ids') or []),
        'genre_ids': list(session.get('genre_ids') or []),
        'include_remixes': False,
        'include_featured': False,
        'include_covers': True,
        'hide_osts': session.get('hide_osts', False),
    }


MISC_SORT_FIELDS = {'name', 'release', 'artist', 'added'}


def get_rated_filter():
    """Shared (misc + artist) rated/unrated filter preference."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        val = getattr(current_user.settings, 'rated_filter', None) or 'all'
    else:
        val = session.get('rated_filter') or 'all'
    return val if val in ('all', 'unrated', 'rated') else 'all'


def get_misc_scope_filter():
    """Misc-only 'Show' scope filter preference."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        val = getattr(current_user.settings, 'misc_scope_filter', None) or 'all'
    else:
        val = session.get('misc_scope_filter') or 'all'
    return val if val in ('all', 'misc-only', 'on-artist') else 'all'


def _get_misc_sort():
    """Return (field, direction) for the misc sort, from user settings or session."""
    field, direction = 'added', 'asc'
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        s = current_user.settings
        field = getattr(s, 'misc_sort_field', None) or 'added'
        direction = getattr(s, 'misc_sort_dir', None) or 'asc'
    else:
        field = session.get('misc_sort_field') or 'added'
        direction = session.get('misc_sort_dir') or 'asc'
    if field not in MISC_SORT_FIELDS:
        field = 'added'
    if direction not in ('asc', 'desc'):
        direction = 'asc'
    return field, direction


def _sort_misc_songs(songs_list, field, direction):
    """Sort song rows in place, matching the client-side _miscApplySort semantics."""
    asc = direction == 'asc'
    if field == 'name':
        songs_list.sort(key=lambda r: (r['song'].name or '').lower(), reverse=not asc)
    elif field == 'artist':
        songs_list.sort(key=lambda r: ', '.join(r['main_artists']).lower(), reverse=not asc)
    elif field == 'release':
        songs_list.sort(key=lambda r: (
            (r['album']['release_date'] or '') if r['album'] else '',
            (r['song'].name or '').lower(),
        ), reverse=not asc)
    else:  # 'added' — newest first when ascending, matching the client default
        songs_list.sort(key=lambda r: r['song'].id, reverse=asc)


BYPASS_FILTERS = {
    'country_ids': [], 'genre_ids': [], 'include_remixes': True,
    'include_featured': True, 'include_covers': True, 'hide_osts': False,
}


def _build_misc_shell(bypass_filters=False):
    """Build lightweight page shell: country list with song counts, no song data."""
    from app.services.stats import get_display_users

    filters = dict(BYPASS_FILTERS) if bypass_filters else _get_user_filters()
    sort_field, sort_dir = _get_misc_sort()
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin

    query = db.session.query(
        MiscArtist.country_id,
        func.count(func.distinct(SongMiscArtist.song_id)),
    ).join(SongMiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id)
    if filters['country_ids']:
        query = query.filter(MiscArtist.country_id.in_(filters['country_ids']))
    country_counts = query.group_by(MiscArtist.country_id).all()

    all_countries_map = {c.id: c for c in Country.query.all()}
    country_sections = []
    for cid, count in sorted(country_counts, key=lambda x: all_countries_map.get(x[0], Country()).country if x[0] in all_countries_map else ''):
        country = all_countries_map.get(cid)
        if country:
            country_sections.append({
                'country_id': cid,
                'country_name': country.country,
                'song_count': count,
            })

    return {
        'misc_countries': country_sections,
        'users': get_display_users(),
        'edit_mode': edit_mode,
        'all_genres': Genre.query.order_by(Genre.id).all() if edit_mode else [],
        'all_album_types': AlbumType.query.order_by(AlbumType.id).all() if edit_mode else [],
        'all_countries': Country.query.order_by(Country.id).all() if edit_mode else [],
        'navbar_artists': get_filtered_navbar(),
        'misc_sort_field': sort_field,
        'misc_sort_dir': sort_dir,
        'rated_filter': 'all' if bypass_filters else get_rated_filter(),
        'misc_scope_filter': 'all' if bypass_filters else get_misc_scope_filter(),
        'bypass_filters': bypass_filters,
        'gender_css': GENDER_CSS,
        'assignable_users': User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all() if edit_mode else [],
        'rules': db.session.get(Rules, 1),
    }


def _build_country_data(country_id, bypass_filters=False):
    """Build genre → songs data for a single country."""
    from app.services.stats import get_display_users

    filters = dict(BYPASS_FILTERS) if bypass_filters else _get_user_filters()
    sort_field, sort_dir = _get_misc_sort()
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin

    sma_rows = db.session.query(
        SongMiscArtist.song_id, SongMiscArtist.misc_artist_id, SongMiscArtist.artist_is_main,
        MiscArtist.name, MiscArtist.country_id,
    ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
        MiscArtist.country_id == country_id,
    ).all()

    song_ids = {r[0] for r in sma_rows}
    if not song_ids:
        return {'misc_genres': [], 'users': get_display_users(), 'edit_mode': edit_mode, 'country_id': country_id}

    song_misc_artists = defaultdict(list)
    for sid, maid, is_main, ma_name, cid in sma_rows:
        song_misc_artists[sid].append({
            'id': maid, 'name': ma_name, 'country_id': cid, 'is_main': is_main,
        })

    all_sma_rows = db.session.query(
        SongMiscArtist.song_id, SongMiscArtist.misc_artist_id, SongMiscArtist.artist_is_main,
        MiscArtist.name, MiscArtist.country_id,
    ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
        SongMiscArtist.song_id.in_(song_ids),
    ).all()
    for sid, maid, is_main, ma_name, cid in all_sma_rows:
        existing = song_misc_artists.get(sid, [])
        if not any(m['id'] == maid for m in existing):
            song_misc_artists[sid].append({
                'id': maid, 'name': ma_name, 'country_id': cid, 'is_main': is_main,
            })

    songs = Song.query.filter(Song.id.in_(song_ids)).all()
    song_map = {s.id: s for s in songs}

    sg_rows = db.session.execute(
        song_genres.select().where(song_genres.c.song_id.in_(song_ids))
    ).fetchall()
    song_genre_map = defaultdict(set)
    for sid, gid in sg_rows:
        song_genre_map[sid].add(gid)

    sa_rows = db.session.query(
        ArtistSong.song_id, ArtistSong.artist_id, ArtistSong.artist_is_main,
        Artist.name, Artist.gender_id,
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(song_ids)
    ).all()
    song_real_artists = defaultdict(list)
    for sid, aid, is_main, a_name, gid in sa_rows:
        song_real_artists[sid].append({
            'artist_id': aid, 'name': a_name, 'is_main': is_main, 'gender_id': gid,
        })

    as_rows = db.session.query(
        AlbumSong.song_id, Album.id, Album.name, Album.release_date, Album.album_type_id,
    ).join(Album, Album.id == AlbumSong.album_id).filter(
        AlbumSong.song_id.in_(song_ids)
    ).all()
    song_album_map = {}
    for sid, alid, al_name, al_date, al_type in as_rows:
        if sid not in song_album_map:
            song_album_map[sid] = {
                'id': alid, 'name': al_name, 'release_date': al_date, 'album_type_id': al_type,
            }

    ratings_rows = Rating.query.filter(Rating.song_id.in_(song_ids)).all()
    ratings_map = defaultdict(dict)
    for r in ratings_rows:
        ratings_map[r.song_id][r.user_id] = r

    all_genres = {g.id: g for g in Genre.query.all()}
    ost_genre = Genre.query.filter_by(genre='OST').first()
    ost_genre_id = ost_genre.id if ost_genre else None
    ANIME_GENDER_ID = 3

    def _is_anime_song(sid):
        return any(a['gender_id'] == ANIME_GENDER_ID for a in song_real_artists.get(sid, []) if a['is_main'])

    def _collab_labels(sid):
        misc_as = song_misc_artists.get(sid, [])
        real_as = song_real_artists.get(sid, [])
        main_names = [a['name'] for a in misc_as if a['is_main']]
        feat_names = [a['name'] for a in misc_as if not a['is_main']]
        for a in real_as:
            if a['is_main']:
                main_names.append(a['name'])
            else:
                feat_names.append(a['name'])
        return main_names, feat_names

    from app.services.preferences import rated_remix_override_ids
    keep_remix_ids = rated_remix_override_ids(filters['include_remixes'], set(song_map.keys()))

    genre_data = defaultdict(list)
    for sid, song in song_map.items():
        if not edit_mode:
            if not filters['include_remixes'] and song.is_remix and sid not in keep_remix_ids:
                continue
            if not filters['include_covers'] and song.is_cover:
                continue
            if not filters['include_featured']:
                main_names, _ = _collab_labels(sid)
                if not main_names:
                    continue
        genre_ids = song_genre_map.get(sid, set())
        if filters['hide_osts'] and ost_genre_id and genre_ids == {ost_genre_id} and not _is_anime_song(sid):
            continue
        if filters['genre_ids']:
            if not genre_ids.intersection(set(filters['genre_ids'])):
                continue

        genres = genre_ids if genre_ids else {0}
        album_info = song_album_map.get(sid)
        main_names, feat_names = _collab_labels(sid)

        song_row = {
            'song': song,
            'main_artists': main_names,
            'feat_artists': feat_names,
            'album': album_info,
            'genres': [all_genres[gid].genre for gid in genres if gid in all_genres],
            'genre_ids': genres,
            'ratings': ratings_map.get(sid, {}),
            'misc_artists': song_misc_artists.get(sid, []),
            'real_artists': song_real_artists.get(sid, []),
        }
        for gid in genres:
            genre_data[gid].append(song_row)

    genre_sections = []
    for gid in sorted(genre_data.keys(), key=lambda g: all_genres.get(g, Genre()).genre if g in all_genres else 'Uncategorized'):
        genre = all_genres.get(gid)
        genre_name = genre.genre if genre else 'Uncategorized'
        songs_list = genre_data[gid]
        _sort_misc_songs(songs_list, sort_field, sort_dir)
        genre_sections.append({
            'genre_id': gid,
            'genre_name': genre_name,
            'songs': songs_list,
        })

    return {
        'misc_genres': genre_sections,
        'users': get_display_users(),
        'edit_mode': edit_mode,
        'country_id': country_id,
    }


@misc_bp.route('/misc')
@login_required
def misc_page():
    data = _build_misc_shell(bypass_filters=request.args.get('nofilter') == '1')
    return render_template('misc.html', **data)


@misc_bp.route('/misc/country/<int:country_id>')
@login_required
def misc_country(country_id):
    data = _build_country_data(country_id, bypass_filters=request.args.get('nofilter') == '1')
    return render_template('fragments/misc_country.html', **data)


@misc_bp.route('/misc/unrated-count')
@login_required
def unrated_count():
    filters = _get_user_filters()

    misc_song_ids = {r[0] for r in db.session.query(SongMiscArtist.song_id).distinct().all()}
    if not misc_song_ids:
        return json.dumps({'unrated': 0, 'total': 0}), 200, {'Content-Type': 'application/json'}

    songs = Song.query.filter(Song.id.in_(misc_song_ids)).all()

    sg_rows = db.session.execute(
        song_genres.select().where(song_genres.c.song_id.in_(misc_song_ids))
    ).fetchall()
    song_genre_map = defaultdict(set)
    for sid, gid in sg_rows:
        song_genre_map[sid].add(gid)

    ost_genre = Genre.query.filter_by(genre='OST').first()
    ost_genre_id = ost_genre.id if ost_genre else None
    ANIME_GENDER_ID = 3
    anime_song_ids = set()
    if filters['hide_osts'] and ost_genre_id:
        anime_song_ids = {row[0] for row in db.session.query(ArtistSong.song_id).join(
            Artist, ArtistSong.artist_id == Artist.id
        ).filter(
            ArtistSong.song_id.in_(misc_song_ids),
            ArtistSong.artist_is_main == True,
            Artist.gender_id == ANIME_GENDER_ID,
        ).all()}

    # Country filtering
    if filters['country_ids']:
        sma_countries = db.session.query(
            SongMiscArtist.song_id, MiscArtist.country_id,
        ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
            SongMiscArtist.song_id.in_(misc_song_ids)
        ).all()
        country_set = set(filters['country_ids'])
        valid_song_ids = {sid for sid, cid in sma_countries if cid in country_set}
    else:
        valid_song_ids = misc_song_ids

    rated_ids = {r.song_id for r in Rating.query.filter(
        Rating.user_id == current_user.id,
        Rating.song_id.in_(misc_song_ids)).all()}

    from app.services.preferences import rated_remix_override_ids
    keep_remix_ids = rated_remix_override_ids(filters['include_remixes'], misc_song_ids)

    total = 0
    unrated = 0
    for song in songs:
        if song.id not in valid_song_ids:
            continue
        if not filters['include_remixes'] and song.is_remix and song.id not in keep_remix_ids:
            continue
        if not filters['include_covers'] and song.is_cover:
            continue
        genres = song_genre_map.get(song.id, set())
        if filters['hide_osts'] and ost_genre_id and genres == {ost_genre_id} and song.id not in anime_song_ids:
            continue
        if filters['genre_ids'] and not genres.intersection(set(filters['genre_ids'])):
            continue
        total += 1
        if song.id not in rated_ids:
            unrated += 1

    return json.dumps({'unrated': unrated, 'total': total}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/song/<int:song_id>/country')
@login_required
def song_country(song_id):
    row = db.session.query(MiscArtist.country_id).join(
        SongMiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id
    ).filter(
        SongMiscArtist.song_id == song_id
    ).order_by(SongMiscArtist.artist_is_main.desc()).first()
    if not row:
        return json.dumps({'country_id': None}), 200, {'Content-Type': 'application/json'}
    return json.dumps({'country_id': row[0]}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/search-artists')
@login_required
def search_misc_artists():
    q = request.args.get('q', '').strip()
    query = MiscArtist.query
    if q:
        query = query.filter(MiscArtist.name.ilike(f'%{q}%'))
    results = query.order_by(func.lower(MiscArtist.name)).limit(30).all()
    return json.dumps([
        {'id': ma.id, 'name': ma.name, 'country_id': ma.country_id}
        for ma in results
    ]), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/add-misc-artist', methods=['POST'])
@login_required
def add_misc_artist():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    country_id = data.get('country_id')
    if not name or country_id is None:
        abort(400)
    ma = MiscArtist(name=name, country_id=int(country_id))
    db.session.add(ma)
    log_change(current_user, f'Created misc artist "{name}"', change_type='artist')
    db.session.commit()
    return json.dumps({'id': ma.id, 'name': ma.name, 'country_id': ma.country_id}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/add-song', methods=['POST'])
@login_required
def add_misc_song():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change

    data = request.get_json(silent=True) or {}
    song_name = (data.get('name') or '').strip()
    if not song_name:
        return json.dumps({'error': 'Song name is required'}), 400, {'Content-Type': 'application/json'}

    misc_artists = data.get('misc_artists', [])
    real_artists = data.get('real_artists', [])
    if not misc_artists:
        return json.dumps({'error': 'At least one misc artist is required'}), 400, {'Content-Type': 'application/json'}

    has_main = any(a.get('is_main') for a in misc_artists) or any(a.get('is_main') for a in real_artists)
    if not has_main:
        return json.dumps({'error': 'At least one artist must be marked as main'}), 400, {'Content-Type': 'application/json'}

    genre_ids = data.get('genre_ids', [])
    if not genre_ids:
        return json.dumps({'error': 'At least one genre is required'}), 400, {'Content-Type': 'application/json'}

    song = Song(
        name=song_name,
        submitted_by_id=current_user.id,
        is_promoted=bool(data.get('is_promoted')),
        is_remix=bool(data.get('is_remix')),
        is_cover=bool(data.get('is_cover')),
        spotify_url=data.get('spotify_url') or None,
        youtube_url=data.get('youtube_url') or None,
        note=(data.get('note') or '').strip() or None,
    )
    db.session.add(song)
    db.session.flush()

    # Link misc artists
    for ma_data in misc_artists:
        ma_id = ma_data.get('id')
        if ma_data.get('new'):
            ma = MiscArtist(name=ma_data['name'], country_id=int(ma_data['country_id']))
            db.session.add(ma)
            db.session.flush()
            ma_id = ma.id
        db.session.add(SongMiscArtist(
            song_id=song.id, misc_artist_id=int(ma_id),
            artist_is_main=bool(ma_data.get('is_main', True)),
        ))

    # Link real artists
    for ra_data in real_artists:
        db.session.add(ArtistSong(
            artist_id=int(ra_data['artist_id']), song_id=song.id,
            artist_is_main=bool(ra_data.get('is_main', False)),
        ))

    # Song genres
    for gid in genre_ids:
        db.session.execute(song_genres.insert().values(song_id=song.id, genre_id=int(gid)))

    log_change(current_user, f'Added "{song_name}" misc song', song=song)
    db.session.commit()

    return json.dumps({'ok': True, 'song_id': song.id}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/manage-artists')
@login_required
def manage_misc_artists():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    artists = db.session.query(
        MiscArtist.id, MiscArtist.name, MiscArtist.country_id,
        func.count(SongMiscArtist.song_id).label('song_count'),
    ).outerjoin(SongMiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id).group_by(
        MiscArtist.id
    ).order_by(func.lower(MiscArtist.name)).all()
    countries = Country.query.order_by(Country.id).all()
    return json.dumps({
        'artists': [{'id': a[0], 'name': a[1], 'country_id': a[2], 'song_count': a[3]} for a in artists],
        'countries': [{'id': c.id, 'name': c.country} for c in countries],
    }), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/edit-artist/<int:artist_id>', methods=['POST'])
@login_required
def edit_misc_artist(artist_id):
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    ma = db.session.get(MiscArtist, artist_id)
    if ma is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    old_name = ma.name
    old_country = ma.country_id
    if 'name' in data:
        ma.name = (data['name'] or '').strip() or ma.name
    if 'country_id' in data:
        try:
            cid = int(data['country_id'])
        except (TypeError, ValueError):
            abort(400)
        if db.session.get(Country, cid) is None:
            abort(400)
        ma.country_id = cid
    if ma.name != old_name:
        log_change(current_user, f'Renamed misc artist "{old_name}" to "{ma.name}"', change_type='artist')
    if ma.country_id != old_country:
        log_change(current_user, f'Changed misc artist "{ma.name}" country', change_type='artist')
    db.session.commit()
    return json.dumps({'id': ma.id, 'name': ma.name, 'country_id': ma.country_id}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/delete-artist/<int:artist_id>', methods=['POST'])
@login_required
def delete_misc_artist(artist_id):
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    ma = db.session.get(MiscArtist, artist_id)
    if ma is None:
        abort(404)
    linked = SongMiscArtist.query.filter_by(misc_artist_id=artist_id).count()
    if linked > 0:
        return json.dumps({'error': 'Cannot delete: artist has linked songs'}), 400, {'Content-Type': 'application/json'}
    name = ma.name
    db.session.delete(ma)
    log_change(current_user, f'Deleted misc artist "{name}"', change_type='artist')
    db.session.commit()
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


def _format_credit(pairs):
    """pairs: list of (rank, name) where rank 0 = main, 1 = featured.
    Returns 'Main1, Main2 (feat. Feat1, Feat2)'."""
    mains = sorted(n for r, n in pairs if r == 0)
    feats = sorted(n for r, n in pairs if r != 0)
    s = ', '.join(mains)
    if feats:
        s += (' ' if s else '') + '(feat. ' + ', '.join(feats) + ')'
    return s


@misc_bp.route('/misc/artist-songs')
@login_required
def artist_songs_list():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    ids = request.args.get('ids', '')
    artist_ids = [int(x) for x in ids.split(',') if x.strip().isdigit()]
    if not artist_ids:
        return json.dumps({}), 200, {'Content-Type': 'application/json'}
    rows = db.session.query(
        SongMiscArtist.misc_artist_id, Song.id, Song.name,
    ).join(Song, Song.id == SongMiscArtist.song_id).filter(
        SongMiscArtist.misc_artist_id.in_(artist_ids)
    ).order_by(Song.name).all()

    # Build a per-song artist display string (main first) covering every credit on the
    # song — real and misc, including the misc artist being combined — so the row matches
    # the song's full credit shown elsewhere.
    song_ids = {r[1] for r in rows}
    artist_map = {}
    songs_with_album = set()
    if song_ids:
        for sid, name, is_main in db.session.query(
            ArtistSong.song_id, Artist.name, ArtistSong.artist_is_main
        ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
            ArtistSong.song_id.in_(song_ids)
        ).all():
            artist_map.setdefault(sid, []).append((0 if is_main else 1, name))
        for sid, name, is_main in db.session.query(
            SongMiscArtist.song_id, MiscArtist.name, SongMiscArtist.artist_is_main
        ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
            SongMiscArtist.song_id.in_(song_ids)
        ).all():
            artist_map.setdefault(sid, []).append((0 if is_main else 1, name))
        songs_with_album = {r[0] for r in db.session.query(AlbumSong.song_id).filter(
            AlbumSong.song_id.in_(song_ids)
        ).distinct().all()}

    result = {}
    for ma_id, song_id, song_name in rows:
        arts = _format_credit(artist_map.get(song_id, []))
        result.setdefault(str(ma_id), []).append({
            'id': song_id, 'name': song_name, 'artists': arts,
            'has_album': song_id in songs_with_album,
        })
    return json.dumps(result), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/merge-artists', methods=['POST'])
@login_required
def merge_misc_artists():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    data = request.get_json(silent=True) or {}
    keep_id = data.get('keep_id')
    absorb_id = data.get('absorb_id')
    if not keep_id or not absorb_id:
        abort(400)
    keep_id = int(keep_id)
    absorb_id = int(absorb_id)
    if keep_id == absorb_id:
        abort(400)
    keep = db.session.get(MiscArtist, keep_id)
    absorb = db.session.get(MiscArtist, absorb_id)
    if not keep or not absorb:
        abort(404)
    # Move all song links from absorbed to kept
    links = SongMiscArtist.query.filter_by(misc_artist_id=absorb.id).all()
    for link in links:
        existing = db.session.get(SongMiscArtist, (link.song_id, keep.id))
        if existing:
            db.session.delete(link)
        else:
            link.misc_artist_id = keep.id
    absorb_name = absorb.name
    db.session.delete(absorb)
    log_change(current_user, f'Merged misc artist "{absorb_name}" into "{keep.name}"', change_type='artist')
    db.session.commit()
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/combine-song', methods=['POST'])
@login_required
def combine_misc_song():
    """Merge one of a misc artist's songs into an existing song of a real artist.

    Reuses the song-merge machinery, then drops the misc credit that the merge
    carries onto the kept song so the misc artist isn't re-credited there. When the
    misc artist has no songs left, it is deleted (combining it into the real artist).
    """
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    from app.routes.edit.song import perform_song_merge
    data = request.get_json(silent=True) or {}
    try:
        misc_artist_id = int(data['misc_artist_id'])
        real_artist_id = int(data['real_artist_id'])
        song_id = int(data['song_id'])            # the misc song (absorbed)
        target_song_id = int(data['target_song_id'])  # the real song (kept)
    except (KeyError, TypeError, ValueError):
        abort(400)
    if song_id == target_song_id:
        return jsonify({'error': 'Cannot merge a song into itself'}), 400
    ma = db.session.get(MiscArtist, misc_artist_id)
    real = db.session.get(Artist, real_artist_id)
    if ma is None or real is None:
        abort(404)
    if db.session.get(SongMiscArtist, (song_id, misc_artist_id)) is None:
        return jsonify({'error': 'Song is not linked to this misc artist'}), 400
    if db.session.get(ArtistSong, (real_artist_id, target_song_id)) is None:
        return jsonify({'error': 'Target song does not belong to the selected artist'}), 400
    kept = db.session.get(Song, target_song_id)
    absorbed = db.session.get(Song, song_id)
    if kept is None or absorbed is None:
        return jsonify({'error': 'Song not found'}), 400

    overrides = {}
    if 'name' in data:
        overrides['chosen_name'] = data['name']
    flags = {f: bool(data[f]) for f in ('is_promoted', 'is_lead', 'is_remix', 'is_cover') if f in data}
    if flags:
        overrides['chosen_flags'] = flags
    urls = {f: (data[f] or None) for f in ('spotify_url', 'youtube_url') if f in data}
    if urls:
        overrides['chosen_urls'] = urls
    if 'note' in data:
        overrides['chosen_note'] = data['note'] or None
    if 'ratings' in data:
        overrides['chosen_ratings'] = data['ratings']

    perform_song_merge(kept, absorbed, **overrides)  # commits internally
    db.session.execute(db.text(
        'DELETE FROM song_misc_artist WHERE song_id = :sid AND misc_artist_id = :mid'
    ), {'sid': target_song_id, 'mid': misc_artist_id})

    remaining = SongMiscArtist.query.filter_by(misc_artist_id=misc_artist_id).count()
    deleted = False
    if remaining == 0:
        ma_name = ma.name
        db.session.delete(ma)
        log_change(current_user, f'Combined misc artist "{ma_name}" into "{real.name}"', change_type='artist')
        deleted = True
    db.session.commit()
    return jsonify({'ok': True, 'deleted': deleted, 'remaining': remaining})


@misc_bp.route('/misc/combine-targets')
@login_required
def combine_targets():
    """Target-song candidates for the combine flow: songs the given real artist is on
    (as main OR featured), each with its role and full artist credit (main first)."""
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    try:
        artist_id = int(request.args.get('artist_id'))
    except (TypeError, ValueError):
        abort(400)
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    rows = db.session.query(Song.id, Song.name, ArtistSong.artist_is_main).join(
        ArtistSong, ArtistSong.song_id == Song.id
    ).filter(
        ArtistSong.artist_id == artist_id, Song.name.ilike(f'%{q}%')
    ).all()
    song_ids = {r[0] for r in rows}

    artist_map = {}
    album_map = {}
    if song_ids:
        for sid, name, is_main in db.session.query(
            ArtistSong.song_id, Artist.name, ArtistSong.artist_is_main
        ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
            ArtistSong.song_id.in_(song_ids)
        ).all():
            artist_map.setdefault(sid, []).append((0 if is_main else 1, name))
        for sid, name, is_main in db.session.query(
            SongMiscArtist.song_id, MiscArtist.name, SongMiscArtist.artist_is_main
        ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
            SongMiscArtist.song_id.in_(song_ids)
        ).all():
            artist_map.setdefault(sid, []).append((0 if is_main else 1, name))
        for sid, aname in db.session.query(
            AlbumSong.song_id, Album.name
        ).join(Album, Album.id == AlbumSong.album_id).filter(
            AlbumSong.song_id.in_(song_ids)
        ).all():
            album_map.setdefault(sid, aname)

    results = []
    for sid, sname, is_main in rows:
        results.append({
            'id': sid, 'name': sname,
            'artists': _format_credit(artist_map.get(sid, [])),
            'album': album_map.get(sid, ''),
        })
    results.sort(key=lambda r: r['name'].lower())
    return json.dumps(results[:40]), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/swap-credit', methods=['POST'])
@login_required
def swap_credit():
    """Convert a song's misc-artist credit into a real ArtistSong credit for the artist
    being combined into (preserving main/feat), then drop the misc link. If the song has
    no album yet, an album must be selected/created. Deletes the misc artist when empty.
    """
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    data = request.get_json(silent=True) or {}
    try:
        misc_artist_id = int(data['misc_artist_id'])
        real_artist_id = int(data['real_artist_id'])
        song_id = int(data['song_id'])
    except (KeyError, TypeError, ValueError):
        abort(400)
    ma = db.session.get(MiscArtist, misc_artist_id)
    real = db.session.get(Artist, real_artist_id)
    song = db.session.get(Song, song_id)
    if ma is None or real is None or song is None:
        abort(404)
    link = db.session.get(SongMiscArtist, (song_id, misc_artist_id))
    if link is None:
        return jsonify({'error': 'Song is not linked to this misc artist'}), 400
    is_main = link.artist_is_main

    # If the song has no album yet, one must be chosen or created.
    if AlbumSong.query.filter_by(song_id=song_id).first() is None:
        album_data = data.get('album') or {}
        album = None
        if album_data.get('existing_id'):
            album = db.session.get(Album, int(album_data['existing_id']))
            if album is None:
                return jsonify({'error': 'Album not found'}), 400
        elif album_data.get('name'):
            new_release_date = (album_data.get('release_date') or '').strip() or None
            if new_release_date and not is_valid_release_date(new_release_date):
                return jsonify({'error': 'Invalid release date'}), 400
            album = Album(
                name=album_data['name'].strip(),
                release_date=new_release_date,
                album_type_id=int(album_data.get('album_type_id', 2)),
                submitted_by_id=current_user.id,
                artist_id=real_artist_id,
                note=(album_data.get('note') or '').strip() or None,
            )
            db.session.add(album)
            db.session.flush()
            for gid in album_data.get('genre_ids', []):
                db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=int(gid)))
        else:
            return jsonify({'error': 'album_required', 'needs_album': True}), 400
        next_track = db.session.execute(db.text(
            'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
        ), {'aid': album.id}).scalar()
        db.session.add(AlbumSong(album_id=album.id, song_id=song_id, track_number=next_track))

    # Swap the credit: add a real ArtistSong (if missing), remove the misc link.
    if db.session.get(ArtistSong, (real_artist_id, song_id)) is None:
        db.session.add(ArtistSong(artist_id=real_artist_id, song_id=song_id, artist_is_main=is_main))
    db.session.execute(db.text(
        'DELETE FROM song_misc_artist WHERE song_id = :sid AND misc_artist_id = :mid'
    ), {'sid': song_id, 'mid': misc_artist_id})
    db.session.flush()

    # Ensure the song still has a main artist.
    has_main = (ArtistSong.query.filter_by(song_id=song_id, artist_is_main=True).count() > 0
                or SongMiscArtist.query.filter_by(song_id=song_id, artist_is_main=True).count() > 0)
    if not has_main:
        promote = db.session.get(ArtistSong, (real_artist_id, song_id))
        if promote:
            promote.artist_is_main = True

    log_change(current_user, f'Swapped misc credit "{ma.name}" to "{real.name}" on "{song.name}"', song=song, change_type='song')

    remaining = SongMiscArtist.query.filter_by(misc_artist_id=misc_artist_id).count()
    deleted = False
    if remaining == 0:
        ma_name = ma.name
        db.session.delete(ma)
        log_change(current_user, f'Combined misc artist "{ma_name}" into "{real.name}"', change_type='artist')
        deleted = True
    db.session.commit()
    return jsonify({'ok': True, 'deleted': deleted, 'remaining': remaining})


@misc_bp.route('/misc/combine-auto-merge', methods=['POST'])
@login_required
def combine_auto_merge():
    """Drop the misc artist's credit from any song where the real artist is already
    credited — the song is already the real artist's, so there's nothing to merge.
    Deletes the misc artist if no songs remain linked.
    """
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    data = request.get_json(silent=True) or {}
    try:
        misc_artist_id = int(data['misc_artist_id'])
        real_artist_id = int(data['real_artist_id'])
    except (KeyError, TypeError, ValueError):
        abort(400)
    ma = db.session.get(MiscArtist, misc_artist_id)
    real = db.session.get(Artist, real_artist_id)
    if ma is None or real is None:
        abort(404)

    overlap = [r[0] for r in db.session.query(SongMiscArtist.song_id).join(
        ArtistSong,
        (ArtistSong.song_id == SongMiscArtist.song_id) & (ArtistSong.artist_id == real_artist_id)
    ).filter(SongMiscArtist.misc_artist_id == misc_artist_id).all()]
    for sid in overlap:
        db.session.execute(db.text(
            'DELETE FROM song_misc_artist WHERE song_id = :sid AND misc_artist_id = :mid'
        ), {'sid': sid, 'mid': misc_artist_id})
    if overlap:
        log_change(current_user, f'Dropped redundant "{ma.name}" misc credit from {len(overlap)} song(s) already credited to "{real.name}"', change_type='artist')

    remaining = SongMiscArtist.query.filter_by(misc_artist_id=misc_artist_id).count()
    deleted = False
    if remaining == 0:
        ma_name = ma.name
        db.session.delete(ma)
        log_change(current_user, f'Combined misc artist "{ma_name}" into "{real.name}"', change_type='artist')
        deleted = True
    db.session.commit()
    return jsonify({'ok': True, 'auto_merged': len(overlap), 'deleted': deleted, 'remaining': remaining})


@misc_bp.route('/misc/song/<int:song_id>/misc-artists', methods=['POST'])
@login_required
def update_song_misc_artists(song_id):
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    data = request.get_json(silent=True) or {}

    # Don't allow leaving the song with zero artists (real or misc).
    new_misc_count = len(data.get('misc_artists', []))
    if 'real_artists' in data:
        new_real_count = len(data['real_artists'])
    else:
        new_real_count = ArtistSong.query.filter_by(song_id=song_id).count()
    if new_misc_count + new_real_count == 0:
        return json.dumps({'error': 'Cannot remove the only artist'}), 400, {'Content-Type': 'application/json'}

    # Update misc artists
    SongMiscArtist.query.filter_by(song_id=song_id).delete()
    for ma_data in data.get('misc_artists', []):
        ma_id = ma_data.get('id')
        if ma_data.get('new'):
            ma = MiscArtist(name=ma_data['name'], country_id=int(ma_data['country_id']))
            db.session.add(ma)
            db.session.flush()
            ma_id = ma.id
        db.session.add(SongMiscArtist(
            song_id=song_id, misc_artist_id=int(ma_id),
            artist_is_main=bool(ma_data.get('is_main', True)),
        ))

    # Update real artists if provided
    if 'real_artists' in data:
        ArtistSong.query.filter_by(song_id=song_id).delete()
        for ra in data['real_artists']:
            db.session.add(ArtistSong(
                artist_id=int(ra['artist_id']), song_id=song_id,
                artist_is_main=bool(ra.get('is_main', False)),
            ))

    db.session.flush()
    # Ensure a main remains: if the new set has no main, promote one artist.
    remaining_real = ArtistSong.query.filter_by(song_id=song_id).all()
    remaining_misc = SongMiscArtist.query.filter_by(song_id=song_id).all()
    has_main = any(r.artist_is_main for r in remaining_real) or any(m.artist_is_main for m in remaining_misc)
    if not has_main and (remaining_real or remaining_misc):
        (remaining_real[0] if remaining_real else remaining_misc[0]).artist_is_main = True

    log_change(current_user, f'Updated misc artists on "{song.name}"', song=song)
    db.session.commit()
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/song/<int:song_id>/artists')
@login_required
def get_song_artists(song_id):
    """Return current misc + real artist links for a song."""
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    misc = db.session.query(
        SongMiscArtist.misc_artist_id, MiscArtist.name, MiscArtist.country_id,
        SongMiscArtist.artist_is_main,
    ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
        SongMiscArtist.song_id == song_id
    ).all()
    real = db.session.query(
        ArtistSong.artist_id, Artist.name, ArtistSong.artist_is_main,
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id == song_id
    ).all()
    return json.dumps({
        'misc_artists': [{'id': r[0], 'name': r[1], 'country_id': r[2], 'is_main': r[3]} for r in misc],
        'real_artists': [{'artist_id': r[0], 'name': r[1], 'is_main': r[2]} for r in real],
    }), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/search-real-artists')
@login_required
def search_real_artists():
    """Autocomplete for real Artist records."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}
    results = Artist.query.filter(Artist.name.ilike(f'%{q}%')).order_by(
        func.lower(Artist.name)
    ).limit(20).all()
    return json.dumps([
        {'artist_id': a.id, 'name': a.name}
        for a in results
    ]), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/search-albums')
@login_required
def search_albums():
    """Autocomplete for existing albums (for add-song form)."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}
    results = Album.query.filter(Album.name.ilike(f'%{q}%')).order_by(
        func.lower(Album.name)
    ).limit(20).all()
    return json.dumps([
        {'id': a.id, 'name': a.name, 'release_date': a.release_date or '', 'album_type_id': a.album_type_id}
        for a in results
    ]), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/add-album', methods=['POST'])
@login_required
def add_misc_album():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return json.dumps({'error': 'Album name is required'}), 400, {'Content-Type': 'application/json'}
    release_date = (data.get('release_date') or '').strip() or None
    if release_date and not is_valid_release_date(release_date):
        return json.dumps({'error': 'Invalid release date'}), 400, {'Content-Type': 'application/json'}
    album = Album(
        name=name,
        release_date=release_date,
        album_type_id=int(data.get('album_type_id', 2)),
        submitted_by_id=current_user.id,
        artist_id=None,
        note=(data.get('note') or '').strip() or None,
    )
    db.session.add(album)
    db.session.flush()
    for gid in data.get('genre_ids', []):
        db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=int(gid)))
    log_change(current_user, f'Created misc album "{name}"', album=album, change_type='album')
    db.session.commit()
    return json.dumps({'ok': True, 'album_id': album.id}), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/album/<int:album_id>')
@login_required
def get_album_detail(album_id):
    """Return album details for the album editor popup."""
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    genre_ids = [r[0] for r in db.session.execute(
        album_genres.select().where(album_genres.c.album_id == album_id)
    ).fetchall()]
    return json.dumps({
        'id': album.id, 'name': album.name,
        'release_date': album.release_date or '',
        'album_type_id': album.album_type_id,
        'genre_ids': genre_ids,
    }), 200, {'Content-Type': 'application/json'}


@misc_bp.route('/misc/song/<int:song_id>/move-to-artist', methods=['POST'])
@login_required
def move_song_to_artist(song_id):
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    data = request.get_json(silent=True) or {}

    artists_data = data.get('artists', [])
    if not artists_data:
        return jsonify({'error': 'At least one artist is required'}), 400
    if not any(a.get('is_main') for a in artists_data):
        return jsonify({'error': 'At least one artist must be main'}), 400

    ArtistSong.query.filter_by(song_id=song_id).delete()
    artist_names = []
    for a in artists_data:
        artist = db.session.get(Artist, int(a['artist_id']))
        if not artist:
            return jsonify({'error': f'Artist {a["artist_id"]} not found'}), 404
        db.session.add(ArtistSong(
            artist_id=artist.id, song_id=song_id,
            artist_is_main=bool(a.get('is_main', False)),
        ))
        artist_names.append(artist.name)

    album_data = data.get('album', {})
    album = None
    if album_data.get('existing_id'):
        album = db.session.get(Album, int(album_data['existing_id']))
    elif album_data.get('name'):
        new_release_date = (album_data.get('release_date') or '').strip() or None
        if new_release_date and not is_valid_release_date(new_release_date):
            return jsonify({'error': 'Invalid release date'}), 400
        album = Album(
            name=album_data['name'].strip(),
            release_date=new_release_date,
            album_type_id=int(album_data.get('album_type_id', 2)),
            submitted_by_id=current_user.id,
            artist_id=int(artists_data[0]['artist_id']),
            note=(album_data.get('note') or '').strip() or None,
        )
        db.session.add(album)
        db.session.flush()
        for gid in album_data.get('genre_ids', []):
            db.session.execute(album_genres.insert().values(album_id=album.id, genre_id=int(gid)))

    if album:
        AlbumSong.query.filter_by(song_id=song_id).delete()
        next_track = db.session.execute(db.text(
            'SELECT COALESCE(MAX(track_number), 0) + 1 FROM album_song WHERE album_id = :aid'
        ), {'aid': album.id}).scalar()
        db.session.add(AlbumSong(album_id=album.id, song_id=song_id, track_number=next_track))

    SongMiscArtist.query.filter_by(song_id=song_id).delete()

    log_change(current_user, f'Moved misc song "{song.name}" to {", ".join(artist_names)}', song=song, change_type='song')
    db.session.commit()
    return jsonify({'ok': True})


@misc_bp.route('/misc/set-role', methods=['POST'])
@login_required
def set_misc_role():
    """Set misc owner or maintainer."""
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    kind = request.form.get('kind')
    if kind not in ('owner', 'maintainer'):
        abort(400)
    raw_user_id = request.form.get('user_id', '').strip()
    if raw_user_id:
        user_id = request.form.get('user_id', type=int)
        if user_id is None or db.session.get(User, user_id) is None:
            abort(400)
    else:
        user_id = None
    rules = db.session.get(Rules, 1)
    if not rules:
        abort(500)
    if kind == 'owner':
        rules.misc_owner_id = user_id
    else:
        rules.misc_maintainer_id = user_id
    db.session.commit()
    return jsonify({kind + '_id': user_id})


@misc_bp.route('/misc/spotify-track')
@login_required
def spotify_track():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    from app.services.spotify import fetch_track, SpotifyError
    try:
        data = fetch_track(url)
    except SpotifyError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(data)


@misc_bp.route('/misc/search-artist-albums')
@login_required
def search_artist_albums():
    artist_id = request.args.get('artist_id', type=int)
    if not artist_id:
        return jsonify([])
    albums = (Album.query
              .join(AlbumSong, Album.id == AlbumSong.album_id)
              .join(ArtistSong, ArtistSong.song_id == AlbumSong.song_id)
              .filter(ArtistSong.artist_id == artist_id)
              .distinct()
              .order_by(Album.release_date.desc())
              .all())
    direct = Album.query.filter_by(artist_id=artist_id).all()
    seen = {a.id for a in albums}
    for a in direct:
        if a.id not in seen:
            albums.append(a)
    return jsonify([
        {'id': a.id, 'name': a.name, 'release_date': a.release_date or ''}
        for a in albums
    ])


@misc_bp.route('/misc/spotify-import', methods=['POST'])
@login_required
def spotify_import():
    if not session.get('edit_mode') or not current_user.is_editor_or_admin:
        abort(403)
    from app.services.audit import log_change

    data = request.get_json(silent=True) or {}
    tracks = data.get('tracks', [])
    misc_artists = data.get('misc_artists', [])
    genre_ids = data.get('genre_ids', [])

    if not tracks:
        return jsonify({'error': 'No tracks selected'}), 400
    if not misc_artists:
        return jsonify({'error': 'At least one misc artist is required'}), 400
    if not any(a.get('is_main') for a in misc_artists):
        return jsonify({'error': 'At least one artist must be main'}), 400

    created = 0
    for t in tracks:
        name = (t.get('name') or '').strip()
        if not name:
            continue
        song = Song(
            name=name,
            submitted_by_id=current_user.id,
            spotify_url=t.get('spotify_url') or None,
            youtube_url=t.get('youtube_url') or None,
            note=(t.get('note') or '').strip() or None,
        )
        db.session.add(song)
        db.session.flush()

        for ma in misc_artists:
            ma_id = ma.get('id')
            if ma.get('new'):
                new_ma = MiscArtist(name=ma['name'], country_id=int(ma['country_id']))
                db.session.add(new_ma)
                db.session.flush()
                ma_id = new_ma.id
                ma['id'] = ma_id
                ma.pop('new', None)
            db.session.add(SongMiscArtist(
                song_id=song.id, misc_artist_id=int(ma_id),
                artist_is_main=bool(ma.get('is_main', True)),
            ))

        for gid in genre_ids:
            db.session.execute(song_genres.insert().values(song_id=song.id, genre_id=int(gid)))

        created += 1

    if created:
        log_change(current_user, f'Imported {created} songs from Spotify', change_type='song')
    db.session.commit()
    return jsonify({'ok': True, 'created': created})
