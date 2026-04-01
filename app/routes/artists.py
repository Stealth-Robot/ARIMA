from flask import Blueprint, request, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Artist, Album, Song, Rating, AlbumSong, ArtistSong, album_genres
from app.models.user import User
from app.services.artist import get_filtered_navbar, get_children, is_subunit, get_discography_songs

artists_bp = Blueprint('artists', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed'}


@artists_bp.route('/artists')
@login_required
def artists_list():
    """Redirect to Misc. Artists by default."""
    misc = Artist.query.filter_by(name='Misc. Artists').first()
    if misc:
        return redirect(url_for('artists.artist_detail', artist_id=misc.id))
    navbar = _get_filtered_navbar()
    return render_template('artists.html', navbar_artists=navbar, gender_css=GENDER_CSS)


@artists_bp.route('/artists/<int:artist_id>')
@login_required
def artist_detail(artist_id):
    """Show artist discography. Returns fragment for HTMX or full page."""
    # Subunits redirect to parent
    if is_subunit(artist_id):
        from app.services.artist import get_parent
        parent = get_parent(artist_id)
        if parent:
            artist_id = parent.id

    artist = db.session.get(Artist, artist_id)
    if not artist:
        return 'Artist not found', 404

    discography = _build_discography(artist)
    users = _get_display_users()

    # Build child sections (subunits + soloists)
    children_sections = []
    subunits, soloists = get_children(artist.id)
    for child in subunits + soloists:
        child_disco = _build_discography(child)
        if child_disco:
            children_sections.append({
                'artist': child,
                'discography': child_disco,
            })

    if request.headers.get('HX-Request'):
        return render_template('fragments/artist_discography.html',
                               artist=artist, discography=discography, users=users,
                               gender_css=GENDER_CSS, children=children_sections)

    navbar = _get_filtered_navbar()
    return render_template('artists.html',
                           navbar_artists=navbar, artist=artist,
                           discography=discography, users=users,
                           gender_css=GENDER_CSS, children=children_sections)


def _get_display_users():
    """Get users to show in rating columns (sorted by sort_order, exclude system/guest)."""
    return User.query.filter(
        User.sort_order.isnot(None)
    ).order_by(User.sort_order).all()


def _get_filtered_navbar():
    return get_filtered_navbar()


def _get_collab_labels(song_ids, artist_id):
    """Return {song_id: 'feat. Artist1, Artist2'} for songs with multiple main artists.

    For each song in song_ids that has more than one ArtistSong row with artist_is_main=True,
    return a label listing the OTHER main artists (not artist_id).
    """
    if not song_ids:
        return {}
    rows = ArtistSong.query.filter(
        ArtistSong.song_id.in_(song_ids),
        ArtistSong.artist_is_main == True,
        ArtistSong.artist_id != artist_id,
    ).all()
    if not rows:
        return {}
    labels = {}
    for row in rows:
        other_artist = db.session.get(Artist, row.artist_id)
        if not other_artist:
            continue
        if row.song_id not in labels:
            labels[row.song_id] = []
        labels[row.song_id].append(other_artist.name)
    return {sid: 'feat. ' + ', '.join(names) for sid, names in labels.items()}


def _build_discography(artist):
    """Build discography data for an artist (own songs only, not children)."""
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist.id).all()}
    if not song_ids:
        return []

    # Get filter settings
    from flask import session
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        genre_id = current_user.settings.genre
        include_remixes = current_user.settings.include_remixes
        include_featured = current_user.settings.include_featured
        album_sort_order = current_user.settings.album_sort_order or 'desc'
    else:
        genre_id = session.get('genre')
        include_remixes = False
        include_featured = False
        album_sort_order = session.get('album_sort_order', 'desc')

    # Get all albums containing these songs (NULLs sort last)
    if album_sort_order == 'asc':
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.asc()
    else:
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.desc()
    albums = db.session.query(Album).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).filter(
        AlbumSong.song_id.in_(song_ids)
    ).distinct().order_by(*order).all()

    # Apply genre filter at album level
    if genre_id is not None:
        albums = [a for a in albums if any(g.id == genre_id for g in a.genres)]

    # Build album → songs structure
    discography = []
    for album in albums:
        album_songs = db.session.query(Song, AlbumSong.track_number).join(
            AlbumSong, Song.id == AlbumSong.song_id
        ).filter(
            AlbumSong.album_id == album.id,
            Song.id.in_(song_ids)
        ).order_by(AlbumSong.track_number).all()

        # Filter remixes if setting is off
        if not include_remixes:
            album_songs = [(s, tn) for s, tn in album_songs if not s.is_remix]

        # Filter featured songs if setting is off
        if not include_featured:
            # A song is "featured" for this artist if artist_is_main=False
            main_song_ids = {row.song_id for row in
                             ArtistSong.query.filter_by(artist_id=artist.id, artist_is_main=True).all()}
            # Also include subunit/soloist songs as "main" for browsing
            subunits, soloists = get_children(artist.id)
            for child in subunits + soloists:
                child_main = {row.song_id for row in
                              ArtistSong.query.filter_by(artist_id=child.id, artist_is_main=True).all()}
                main_song_ids |= child_main

            album_songs = [(s, tn) for s, tn in album_songs
                           if s.id in main_song_ids]

        if album_songs:
            # Get ratings for these songs
            song_objs = [s for s, _ in album_songs]
            ratings_map = _get_ratings_map([s.id for s in song_objs])
            collab_labels = _get_collab_labels({s.id for s in song_objs}, artist.id)
            is_pending = album.submission.status == 'pending' if album.submission else False

            discography.append({
                'album': album,
                'songs': album_songs,
                'ratings': ratings_map,
                'collab_labels': collab_labels,
                'is_pending': is_pending,
            })

    return discography


def _get_ratings_map(song_ids):
    """Return {song_id: {user_id: Rating}} for the given songs."""
    if not song_ids:
        return {}
    ratings = Rating.query.filter(Rating.song_id.in_(song_ids)).all()
    result = {}
    for r in ratings:
        if r.song_id not in result:
            result[r.song_id] = {}
        result[r.song_id][r.user_id] = r
    return result
