from flask import Blueprint, request, render_template
from flask_login import login_required

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong

search_bp = Blueprint('search', __name__)


@search_bp.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return render_template('fragments/search_results.html',
                               artists=[], albums=[], songs=[], query=q)

    like = f'%{q}%'
    terms = q.split()

    artists = Artist.query.filter(Artist.name.ilike(like)).all()

    album_query = db.session.query(Album, Artist).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        ArtistSong.artist_is_main == True,
    )
    if len(terms) > 1:
        for term in terms:
            t = f'%{term}%'
            album_query = album_query.filter(
                db.or_(Album.name.ilike(t), Artist.name.ilike(t))
            )
    else:
        album_query = album_query.filter(Album.name.ilike(like))
    albums = album_query.distinct().all()

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
    if len(terms) > 1:
        for term in terms:
            t = f'%{term}%'
            song_query = song_query.filter(
                db.or_(Song.name.ilike(t), Artist.name.ilike(t), Album.name.ilike(t))
            )
    else:
        song_query = song_query.filter(Song.name.ilike(like))
    songs = song_query.distinct().all()

    return render_template('fragments/search_results.html',
                           artists=artists, albums=albums, songs=songs,
                           query=q)
