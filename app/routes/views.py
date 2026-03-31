from flask import Blueprint, render_template
from flask_login import login_required

from app.extensions import db
from app.models.music import Song, Album, Artist, ArtistSong, AlbumSong
from app.decorators import role_required, EDITOR_OR_ADMIN

views_bp = Blueprint('views', __name__)


@views_bp.route('/views')
@login_required
@role_required(EDITOR_OR_ADMIN)
def views_page():
    """Data integrity monitoring page."""
    # Orphaned songs: no AlbumSong entry
    orphan_songs = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(AlbumSong.song_id))
    ).all()

    # Songs without artist link
    no_artist_songs = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(ArtistSong.song_id))
    ).all()

    # Albums with no songs
    empty_albums = db.session.query(Album).filter(
        ~Album.id.in_(db.session.query(AlbumSong.album_id))
    ).all()

    # Artists with no songs
    empty_artists = db.session.query(Artist).filter(
        ~Artist.id.in_(db.session.query(ArtistSong.artist_id))
    ).all()

    return render_template('views.html',
                           orphan_songs=orphan_songs,
                           no_artist_songs=no_artist_songs,
                           empty_albums=empty_albums,
                           empty_artists=empty_artists)
