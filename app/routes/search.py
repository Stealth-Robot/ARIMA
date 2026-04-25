from collections import Counter

from flask import Blueprint, request, render_template, session
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong, album_genres, MiscArtist, SongMiscArtist

search_bp = Blueprint('search', __name__)


def _occurrences(fields, term):
    """Count total occurrences of term across all fields using SQLite string math."""
    term_len = len(term)
    parts = []
    for f in fields:
        lower_f = func.lower(func.coalesce(f, ''))
        parts.append((func.length(lower_f) - func.length(func.replace(lower_f, term, ''))) / term_len)
    return sum(parts)


def _get_filters():
    """Return (country_ids, genre_ids, hide_osts) from user settings or session."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return (list(current_user.settings.country_ids or []),
                list(current_user.settings.genre_ids or []),
                getattr(current_user.settings, 'hide_osts', False))
    return (list(session.get('country_ids') or []),
            list(session.get('genre_ids') or []),
            session.get('hide_osts', False))


@search_bp.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return render_template('fragments/search_results.html',
                               artists=[], albums=[], songs=[], query=q)

    like = f'%{q}%'
    terms = q.lower().split()
    term_counts = Counter(terms)
    country_ids, genre_ids, hide_osts = _get_filters()

    # Pre-compute OST album IDs to exclude from results
    ost_album_ids = None
    if hide_osts:
        from app.models.lookups import Genre
        ost_genre = Genre.query.filter_by(genre='OST').first()
        if ost_genre:
            ost_album_ids = {row[0] for row in db.session.query(album_genres.c.album_id).filter(
                album_genres.c.genre_id == ost_genre.id
            ).all()}

    # --- Artists ---
    artist_query = Artist.query.filter(Artist.name.ilike(like))
    if country_ids:
        artist_query = artist_query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        artist_ids_with_genre = {row[0] for row in db.session.query(ArtistSong.artist_id).join(
            AlbumSong, ArtistSong.song_id == AlbumSong.song_id
        ).join(
            album_genres, AlbumSong.album_id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id.in_(genre_ids)).distinct().all()}
        artist_query = artist_query.filter(Artist.id.in_(artist_ids_with_genre))
    artists = artist_query.order_by(func.lower(Artist.name)).all()

    # --- Albums ---
    album_query = db.session.query(Album, Artist).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        album_query = album_query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        album_query = album_query.join(
            album_genres, Album.id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id.in_(genre_ids))
    if ost_album_ids:
        album_query = album_query.filter(~Album.id.in_(ost_album_ids))
    if len(terms) > 1:
        album_fields = [Album.name, Artist.name]
        for term, count in term_counts.items():
            if count == 1:
                t = f'%{term}%'
                album_query = album_query.filter(
                    db.or_(*(f.ilike(t) for f in album_fields))
                )
            else:
                album_query = album_query.filter(
                    _occurrences(album_fields, term) >= count
                )
    else:
        album_query = album_query.filter(Album.name.ilike(like))
    albums = album_query.order_by(func.lower(Album.name), func.lower(Artist.name)).distinct().all()

    # --- Songs ---
    # Step 1: find matching song IDs (search across ALL artists incl. featured)
    song_id_q = db.session.query(Song.id).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    )
    if len(terms) > 1:
        song_fields = [Song.name, Artist.name, Album.name]
        for term, count in term_counts.items():
            if count == 1:
                t = f'%{term}%'
                song_id_q = song_id_q.filter(
                    db.or_(*(f.ilike(t) for f in song_fields))
                )
            else:
                song_id_q = song_id_q.filter(
                    _occurrences(song_fields, term) >= count
                )
    else:
        song_id_q = song_id_q.filter(Song.name.ilike(like))
    if ost_album_ids:
        song_id_q = song_id_q.filter(~Album.id.in_(ost_album_ids))
    matched_song_ids = song_id_q.distinct()

    # Step 2: display rows — main artist only, with country/genre filters
    song_query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        Song.id.in_(matched_song_ids),
        ArtistSong.artist_is_main == True,
    )
    if country_ids:
        song_query = song_query.filter(Artist.country_id.in_(country_ids))
    if genre_ids:
        song_query = song_query.join(
            album_genres, Album.id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id.in_(genre_ids))
    if ost_album_ids:
        song_query = song_query.filter(~Album.id.in_(ost_album_ids))
    song_rows = song_query.order_by(func.lower(Song.name), func.lower(Artist.name)).all()

    # Step 3: deduplicate by song ID
    seen = set()
    song_map = {}
    song_order = []
    for song, album, artist in song_rows:
        if song.id not in seen:
            seen.add(song.id)
            song_map[song.id] = (song, album, artist)
            song_order.append(song.id)

    # Step 4: gather all artists per song (main first, then featured)
    song_artists = {}
    if song_map:
        artist_rows = db.session.query(
            ArtistSong.song_id, Artist.name, ArtistSong.artist_is_main
        ).join(
            Artist, ArtistSong.artist_id == Artist.id
        ).filter(
            ArtistSong.song_id.in_(song_map.keys())
        ).order_by(
            ArtistSong.artist_is_main.desc(),
            Artist.name,
        ).all()
        for song_id, artist_name, _ in artist_rows:
            song_artists.setdefault(song_id, []).append(artist_name)

    songs = []
    for sid in song_order:
        song, album, main_artist = song_map[sid]
        artists_str = ', '.join(song_artists.get(sid, [main_artist.name]))
        songs.append((song, album, main_artist, artists_str))

    # --- Misc songs (via song_misc_artist) ---
    misc_songs = []
    try:
        misc_song_q = db.session.query(Song).join(
            SongMiscArtist, Song.id == SongMiscArtist.song_id
        ).join(
            MiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id
        )
        if len(terms) > 1:
            misc_fields = [Song.name, MiscArtist.name]
            for term, count in term_counts.items():
                if count == 1:
                    t = f'%{term}%'
                    misc_song_q = misc_song_q.filter(
                        db.or_(*(f.ilike(t) for f in misc_fields))
                    )
                else:
                    misc_song_q = misc_song_q.filter(
                        _occurrences(misc_fields, term) >= count
                    )
        else:
            misc_song_q = misc_song_q.filter(
                db.or_(Song.name.ilike(like), MiscArtist.name.ilike(like))
            )
        misc_song_rows = misc_song_q.distinct().all()

        # Exclude songs already found via normal search
        misc_song_rows = [s for s in misc_song_rows if s.id not in seen]

        # Get misc artist names per song
        if misc_song_rows:
            misc_sids = [s.id for s in misc_song_rows]
            ma_rows = db.session.query(
                SongMiscArtist.song_id, MiscArtist.name, SongMiscArtist.artist_is_main
            ).join(MiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id).filter(
                SongMiscArtist.song_id.in_(misc_sids)
            ).order_by(SongMiscArtist.artist_is_main.desc(), MiscArtist.name).all()
            misc_artists_by_song = {}
            for sid, name, _ in ma_rows:
                misc_artists_by_song.setdefault(sid, []).append(name)

            # Get album info
            misc_album_rows = db.session.query(
                AlbumSong.song_id, Album
            ).join(Album, AlbumSong.album_id == Album.id).filter(
                AlbumSong.song_id.in_(misc_sids)
            ).all()
            misc_album_map = {}
            for sid, alb in misc_album_rows:
                if sid not in misc_album_map:
                    misc_album_map[sid] = alb

            for s in misc_song_rows:
                artists_str = ', '.join(misc_artists_by_song.get(s.id, ['Unknown']))
                alb = misc_album_map.get(s.id)
                album_name = alb.name if alb else ''
                misc_songs.append((s, album_name, artists_str))
    except Exception:
        pass

    return render_template('fragments/search_results.html',
                           artists=artists, albums=albums, songs=songs,
                           misc_songs=misc_songs, query=q)
