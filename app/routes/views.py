from datetime import datetime

from flask import Blueprint, render_template, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Song, Album, Artist, ArtistSong, AlbumSong
from app.decorators import role_required, EDITOR_OR_ADMIN

views_bp = Blueprint('views', __name__)


def _album_artists(album_ids):
    """Return {album_id: [artist_name, ...]} for main artists."""
    if not album_ids:
        return {}
    rows = db.session.query(AlbumSong.album_id, Artist.name).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        AlbumSong.album_id.in_(album_ids),
        ArtistSong.artist_is_main == True,
    ).distinct().all()
    result = {}
    for album_id, artist_name in rows:
        result.setdefault(album_id, []).append(artist_name)
    return result


@views_bp.route('/views')
@login_required
@role_required(EDITOR_OR_ADMIN)
def views_page():
    """Data integrity monitoring page — shows collapsed sections with counts."""
    counts = {
        'orphan_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(AlbumSong.song_id))
        ).count(),
        'no_artist_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(ArtistSong.song_id))
        ).count(),
        'empty_albums': db.session.query(Album).filter(
            ~Album.id.in_(db.session.query(AlbumSong.album_id)),
            Album.artist_id.is_(None)
        ).count(),
        'empty_artists': db.session.query(Artist).filter(
            ~Artist.id.in_(db.session.query(ArtistSong.artist_id))
        ).count(),
        'undated_albums': db.session.query(Album).filter(
            db.or_(Album.release_date.is_(None), Album.release_date == '')
        ).count(),
        'incomplete_date_albums': db.session.query(Album).filter(
            Album.release_date.like('%-01-01'),
        ).count(),
        'potentially_disbanded': _potentially_disbanded_query().count(),
        'incomplete_tabs': db.session.query(Artist).filter(
            Artist.is_complete == False,
        ).count(),
    }
    return render_template('views.html', counts=counts)


@views_bp.route('/views/orphan-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_orphan_songs():
    items = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(AlbumSong.song_id))
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={s.id} — "{s.name}"'} for s in items
    ])


@views_bp.route('/views/no-artist-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_no_artist_songs():
    items = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(ArtistSong.song_id))
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={s.id} — "{s.name}"'} for s in items
    ])


@views_bp.route('/views/empty-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_empty_albums():
    items = db.session.query(Album).filter(
        ~Album.id.in_(db.session.query(AlbumSong.album_id)),
        Album.artist_id.is_(None)
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={a.id} — "{a.name}"'} for a in items
    ])


@views_bp.route('/views/empty-artists')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_empty_artists():
    items = db.session.query(Artist).filter(
        ~Artist.id.in_(db.session.query(ArtistSong.artist_id))
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={a.id} — "{a.name}"'} for a in items
    ])


@views_bp.route('/views/undated-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_undated_albums():
    albums = db.session.query(Album).filter(
        db.or_(Album.release_date.is_(None), Album.release_date == '')
    ).order_by(Album.name).all()
    album_artists = _album_artists([a.id for a in albums])
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    return render_template('fragments/view_album_dates.html',
                           albums=albums, album_artists=album_artists,
                           edit_mode=edit_mode, id_prefix='undated')


@views_bp.route('/views/incomplete-date-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_incomplete_date_albums():
    albums = db.session.query(Album).filter(
        Album.release_date.like('%-01-01'),
    ).order_by(Album.release_date.desc(), Album.name).all()
    album_artists = _album_artists([a.id for a in albums])
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    return render_template('fragments/view_album_dates.html',
                           albums=albums, album_artists=album_artists,
                           edit_mode=edit_mode, id_prefix='incomplete',
                           show_year=True)


def _potentially_disbanded_query():
    """Artists with no songs on albums released in the last 5 years, not already marked disbanded."""
    cutoff = f'{datetime.now().year - 5}-01-01'
    recent_artist_ids = db.session.query(ArtistSong.artist_id).join(
        AlbumSong, ArtistSong.song_id == AlbumSong.song_id
    ).join(
        Album, AlbumSong.album_id == Album.id
    ).filter(
        Album.release_date >= cutoff,
        ArtistSong.artist_is_main == True,
    ).distinct()
    return db.session.query(Artist).filter(
        ~Artist.id.in_(recent_artist_ids),
        Artist.is_disbanded == False,
    )


@views_bp.route('/views/potentially-disbanded')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_potentially_disbanded():
    artists = _potentially_disbanded_query().order_by(Artist.name).all()
    return render_template('fragments/view_potentially_disbanded.html', artists=artists)


@views_bp.route('/views/incomplete-tabs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_incomplete_tabs():
    artists = db.session.query(Artist).filter(
        Artist.is_complete == False,
    ).order_by(Artist.name).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'<a href="/artists/{a.slug}" style="color: var(--link);">{a.name}</a>', 'safe': True}
        for a in artists
    ])
