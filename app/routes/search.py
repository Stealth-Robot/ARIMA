from collections import Counter

from flask import Blueprint, request, render_template, session
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong, album_genres

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
    """Return (country_id, genre_id) from user settings or session."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return current_user.settings.country, current_user.settings.genre
    return session.get('country'), session.get('genre')


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
    country_id, genre_id = _get_filters()

    # --- Artists ---
    artist_query = Artist.query.filter(Artist.name.ilike(like))
    if country_id is not None:
        artist_query = artist_query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        artist_ids_with_genre = {row[0] for row in db.session.query(ArtistSong.artist_id).join(
            AlbumSong, ArtistSong.song_id == AlbumSong.song_id
        ).join(
            album_genres, AlbumSong.album_id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id == genre_id).distinct().all()}
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
    if country_id is not None:
        album_query = album_query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        album_query = album_query.join(
            album_genres, Album.id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id == genre_id)
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
    song_query = db.session.query(Song, Album, Artist).join(
        AlbumSong, Song.id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        ArtistSong.artist_is_main == True,
    )
    if country_id is not None:
        song_query = song_query.filter(Artist.country_id == country_id)
    if genre_id is not None:
        song_query = song_query.join(
            album_genres, Album.id == album_genres.c.album_id
        ).filter(album_genres.c.genre_id == genre_id)
    if len(terms) > 1:
        song_fields = [Song.name, Artist.name, Album.name]
        for term, count in term_counts.items():
            if count == 1:
                t = f'%{term}%'
                song_query = song_query.filter(
                    db.or_(*(f.ilike(t) for f in song_fields))
                )
            else:
                song_query = song_query.filter(
                    _occurrences(song_fields, term) >= count
                )
    else:
        song_query = song_query.filter(Song.name.ilike(like))
    songs = song_query.order_by(func.lower(Song.name), func.lower(Artist.name)).distinct().all()

    return render_template('fragments/search_results.html',
                           artists=artists, albums=albums, songs=songs,
                           query=q)
