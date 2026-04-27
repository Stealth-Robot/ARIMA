import json
import random

from flask import Blueprint, render_template, session
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, func

from app.extensions import db
from app.models.music import (Artist, ArtistArtist, ArtistSubscription, ArtistSong,
                               AlbumSong, Album, Song, Rating, album_genres)
from app.models.user import UserSettings

SUBUNIT = 0

home_bp = Blueprint('home', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}
ANIME_GENDER_ID = 3


def _pick_canonical_album(albums, artist_id):
    def key(a):
        return (0 if a.artist_id == artist_id else 1, a.release_date or '', a.name.lower())
    return min(albums, key=key)


def _get_rating_backlog():
    sub_artists = (Artist.query
                   .join(ArtistSubscription, and_(
                       ArtistSubscription.artist_id == Artist.id,
                       ArtistSubscription.user_id == current_user.id))
                   .all())
    if not sub_artists:
        return [], {}

    settings = current_user.settings if (
        current_user.is_authenticated and not current_user.is_system_or_guest
    ) else None

    country_ids = list((settings.country_ids if settings else None) or session.get('country_ids') or [])
    genre_ids = list((settings.genre_ids if settings else None) or session.get('genre_ids') or [])
    include_remixes = getattr(settings, 'include_remixes', False) if settings else False
    include_featured = getattr(settings, 'include_featured', False) if settings else False
    hide_osts = getattr(settings, 'hide_osts', False) if settings else session.get('hide_osts', False)
    hide_dupes = getattr(settings, 'hide_duplicate_songs', False) if settings else False

    if country_ids:
        country_set = set(country_ids)
        sub_artists = [a for a in sub_artists if a.country_id in country_set]

    if not sub_artists:
        return [], {}

    sub_artist_ids_set = {a.id for a in sub_artists}
    subunit_rels = ArtistArtist.query.filter(
        ArtistArtist.artist_1.in_(sub_artist_ids_set),
        ArtistArtist.relationship == SUBUNIT).all()
    if subunit_rels:
        child_ids = [r.artist_2 for r in subunit_rels if r.artist_2 not in sub_artist_ids_set]
        if child_ids:
            subunit_artists = Artist.query.filter(Artist.id.in_(child_ids)).all()
            if country_ids:
                subunit_artists = [a for a in subunit_artists if a.country_id in country_set]
            sub_artists.extend(subunit_artists)

    sub_artist_map = {a.id: a for a in sub_artists}
    sub_artist_ids = list(sub_artist_map.keys())

    all_song_ids = {r.song_id for r in ArtistSong.query.filter(
        ArtistSong.artist_id.in_(sub_artist_ids)).all()}
    if not all_song_ids:
        return [], {}

    rated_ids = {r.song_id for r in Rating.query.filter(
        Rating.user_id == current_user.id,
        Rating.song_id.in_(all_song_ids)).all()}

    album_song_rows = (db.session.query(AlbumSong.song_id, AlbumSong.track_number, Album)
                        .join(Album, Album.id == AlbumSong.album_id)
                        .options(selectinload(Album.genres))
                        .filter(AlbumSong.song_id.in_(all_song_ids))
                        .all())
    albums_by_song = {}
    track_by_song_album = {}
    for song_id, track_num, album in album_song_rows:
        albums_by_song.setdefault(song_id, []).append(album)
        track_by_song_album[(song_id, album.id)] = track_num

    main_song_ids = None
    if not include_featured:
        main_song_ids = {r.song_id for r in ArtistSong.query.filter(
            ArtistSong.artist_id.in_(sub_artist_ids),
            ArtistSong.artist_is_main == True).all()}

    song_artist_rows = ArtistSong.query.filter(
        ArtistSong.song_id.in_(all_song_ids),
        ArtistSong.artist_id.in_(sub_artist_ids),
        ArtistSong.artist_is_main == True).all()
    artist_by_song = {}
    for r in song_artist_rows:
        artist_by_song.setdefault(r.song_id, r.artist_id)

    songs = Song.query.filter(Song.id.in_(all_song_ids)).all()

    backlog = {}
    backlog_song_ids = set()
    for song in songs:
        if song.id in rated_ids:
            continue

        if not include_remixes and song.is_remix:
            continue

        if not include_featured and main_song_ids is not None and song.id not in main_song_ids:
            continue

        song_albums = albums_by_song.get(song.id, [])
        if not song_albums:
            continue

        artist_id = artist_by_song.get(song.id)
        if artist_id is None:
            continue
        artist = sub_artist_map[artist_id]

        if hide_osts and artist.gender_id != ANIME_GENDER_ID:
            if all(any(g.genre == 'OST' for g in a.genres) for a in song_albums):
                continue

        if genre_ids:
            genre_set = set(genre_ids)
            if not any(any(g.id in genre_set for g in a.genres) for a in song_albums):
                continue

        if hide_dupes and len(song_albums) > 1:
            pass

        backlog.setdefault(artist, []).append(song)
        backlog_song_ids.add(song.id)

    grouped = {}
    for artist, artist_songs in backlog.items():
        album_groups = {}
        for song in artist_songs:
            song_albums = albums_by_song.get(song.id, [])
            if not song_albums:
                continue
            canonical = _pick_canonical_album(song_albums, artist.id)
            track_num = track_by_song_album.get((song.id, canonical.id), 0)
            album_groups.setdefault(canonical, []).append((song, track_num))
        for alb in album_groups:
            album_groups[alb].sort(key=lambda pair: pair[1])
        sorted_albums = sorted(album_groups.items(),
                               key=lambda pair: (pair[0].release_date or '', pair[0].name.lower()))
        song_count = sum(len(trks) for _, trks in sorted_albums)
        grouped[artist] = (song_count, [(alb, [s for s, _ in trks]) for alb, trks in sorted_albums])

    ratings_map = {}
    if backlog_song_ids:
        for r in Rating.query.filter(Rating.song_id.in_(backlog_song_ids)).all():
            ratings_map.setdefault(r.song_id, {})[r.user_id] = r

    return sorted(grouped.items(), key=lambda pair: pair[0].name.lower()), ratings_map


@home_bp.route('/toggle-hide-disbanded', methods=['POST'])
@login_required
def toggle_hide_disbanded():
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.session.add(settings)
    settings.hide_disbanded_maintained = not UserSettings._as_bool(settings.hide_disbanded_maintained)
    db.session.commit()
    return json.dumps({'hide_disbanded': settings.hide_disbanded_maintained}), 200, {'Content-Type': 'application/json'}


@home_bp.route('/shuffle')
@login_required
def shuffle():
    if not current_user.can_rate:
        return '', 204
    backlog, _ = _get_rating_backlog()
    if not backlog:
        return '', 204
    candidates = []
    for artist, (_count, album_groups) in backlog:
        for album, songs in album_groups:
            for song in songs:
                candidates.append((song, artist, album))
    if not candidates:
        return '', 204
    song, artist, album = random.choice(candidates)

    from urllib.parse import quote
    from app.services.stats import get_display_users
    artist_url = '/artists/' + quote(artist.name, safe="().-&+!?@*=' ")
    users = get_display_users()
    ratings = {r.user_id: r for r in Rating.query.filter_by(song_id=song.id).all()}

    song_artists_rows = db.session.query(
        ArtistSong.artist_id, ArtistSong.artist_is_main, Artist.name, Artist.gender_id
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id == song.id
    ).all()
    from app.routes.artists import _collab_labels_from_song_artists
    sa_map = {song.id: [{'artist_id': a, 'name': n, 'is_main': m, 'gender_id': g}
                        for a, m, n, g in song_artists_rows]}
    collab_label = _collab_labels_from_song_artists(sa_map, artist).get(song.id, '')

    return render_template('fragments/shuffle_card.html',
                           song=song, artist=artist, album=album,
                           artist_url=artist_url, artist_id=artist.id,
                           users=users, ratings=ratings,
                           collab_label=collab_label,
                           gender_css=GENDER_CSS)


@home_bp.route('/')
@login_required
def home():
    owned = (Artist.query
             .filter_by(owner_id=current_user.id, is_complete=False)
             .options(joinedload(Artist.country))
             .order_by(func.lower(Artist.name))
             .all())
    settings = current_user.settings if (
        current_user.is_authenticated and not current_user.is_system_or_guest
    ) else None
    hide_disbanded = UserSettings._as_bool(settings.hide_disbanded_maintained) if settings else True

    has_any_maintained = db.session.query(
        Artist.query.filter_by(maintainer_id=current_user.id).exists()
    ).scalar()

    maintained_q = Artist.query.filter_by(maintainer_id=current_user.id)
    if hide_disbanded:
        maintained_q = maintained_q.filter_by(is_disbanded=False)
    maintained = (maintained_q
                  .options(joinedload(Artist.country))
                  .order_by(func.lower(Artist.name))
                  .all())
    backlog = []
    ratings_map = {}
    users = []
    if current_user.can_rate:
        backlog, ratings_map = _get_rating_backlog()
        if backlog:
            from app.services.stats import get_display_users
            users = get_display_users()
    return render_template('home.html', owned_artists=owned,
                           maintained_artists=maintained, backlog=backlog,
                           ratings=ratings_map, users=users,
                           gender_css=GENDER_CSS,
                           hide_disbanded=hide_disbanded,
                           has_any_maintained=has_any_maintained)
