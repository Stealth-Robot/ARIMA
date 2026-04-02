from flask import Blueprint, request, render_template, redirect, url_for, abort, session
from flask_login import login_required, current_user

from sqlalchemy.orm import selectinload, joinedload

from app.extensions import db
from app.models.music import Artist, Album, Song, Rating, AlbumSong, ArtistSong, album_genres
from app.models.user import User
from app.services.artist import get_filtered_navbar, get_children, is_subunit, get_soloist_parent, get_discography_songs

artists_bp = Blueprint('artists', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed'}


@artists_bp.route('/artists', strict_slashes=False)
@login_required
def artists_list():
    """Redirect to Misc. Artists by default."""
    return redirect(url_for('artists.artist_detail', artist_slug='misc-artists'))


@artists_bp.route('/artists/<int:artist_id>')
@login_required
def artist_detail_by_id(artist_id):
    """Backwards-compat redirect: numeric ID → slug URL (301)."""
    artist = db.session.get(Artist, artist_id)
    if not artist:
        abort(404)
    slug = artist.slug or str(artist.id)
    return redirect(url_for('artists.artist_detail', artist_slug=slug), 301)


@artists_bp.route('/artists/<artist_slug>')
@login_required
def artist_detail(artist_slug):
    """Show artist discography. Returns fragment for HTMX or full page."""
    artist = Artist.query.filter_by(slug=artist_slug).first()
    if not artist:
        abort(404)

    artist_id = artist.id

    # Subunits redirect to parent
    if is_subunit(artist_id):
        from app.services.artist import get_parent
        parent = get_parent(artist_id)
        if parent:
            parent_artist = db.session.get(Artist, parent.id)
            if parent_artist:
                parent_slug = parent_artist.slug or str(parent_artist.id)
                if not request.headers.get('HX-Request'):
                    return redirect(url_for('artists.artist_detail', artist_slug=parent_slug))
                artist = parent_artist
                artist_id = parent_artist.id

    discography = _build_discography(artist)
    users = _get_display_users()

    # Detect soloist parent (for display on the soloist's own page)
    soloist_parent = get_soloist_parent(artist_id)

    # Build child sections (subunits + soloists)
    children_sections = []
    subunits, soloists = get_children(artist.id)
    soloist_ids = {s.id for s in soloists}
    for child in subunits + soloists:
        child_disco = _build_discography(child)
        if child_disco:
            children_sections.append({
                'artist': child,
                'discography': child_disco,
                'is_soloist': child.id in soloist_ids,
            })

    # All artists list for edit mode (song artist picker)
    all_artists = []
    if session.get('edit_mode') and current_user.is_editor_or_admin:
        all_artists = Artist.query.order_by(Artist.name).all()

    if request.headers.get('HX-Request'):
        return render_template('fragments/artist_discography.html',
                               artist=artist, discography=discography, users=users,
                               gender_css=GENDER_CSS, children=children_sections,
                               soloist_parent=soloist_parent, all_artists=all_artists)

    navbar = _get_filtered_navbar()
    # Ensure current artist always appears in navbar regardless of filters
    if artist.id not in {a.id for a in navbar}:
        navbar.append(artist)
        navbar.sort(key=lambda a: a.name.lower())
    return render_template('artists.html',
                           navbar_artists=navbar, artist=artist,
                           discography=discography, users=users,
                           gender_css=GENDER_CSS, children=children_sections,
                           soloist_parent=soloist_parent, all_artists=all_artists)


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
    artist_ids = {row.artist_id for row in rows}
    artists_by_id = {a.id: a for a in Artist.query.filter(Artist.id.in_(artist_ids)).all()}
    labels = {}
    for row in rows:
        other_artist = artists_by_id.get(row.artist_id)
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
    # Eager-load genres and submission to avoid lazy loads per album
    albums = db.session.query(Album).options(
        selectinload(Album.genres),
        joinedload(Album.submission),
    ).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).filter(
        AlbumSong.song_id.in_(song_ids)
    ).distinct().order_by(*order).all()

    # Apply genre filter at album level
    if genre_id is not None:
        albums = [a for a in albums if any(g.id == genre_id for g in a.genres)]

    # Pre-compute main song IDs for featured filter (once, not per-album)
    main_song_ids = None
    if not include_featured:
        subunits, soloists = get_children(artist.id)
        all_artist_ids = [artist.id] + [c.id for c in subunits + soloists]
        main_song_ids = {row.song_id for row in
                         ArtistSong.query.filter(
                             ArtistSong.artist_id.in_(all_artist_ids),
                             ArtistSong.artist_is_main == True
                         ).all()}

    # Bulk-load all album-song mappings for relevant songs in one query
    all_album_songs = db.session.query(AlbumSong.album_id, Song, AlbumSong.track_number).join(
        Song, Song.id == AlbumSong.song_id
    ).filter(
        Song.id.in_(song_ids)
    ).order_by(AlbumSong.album_id, AlbumSong.track_number).all()

    songs_by_album = {}
    for album_id, song, track_num in all_album_songs:
        songs_by_album.setdefault(album_id, []).append((song, track_num))

    # Bulk-load all ratings and collab labels for the entire song set
    all_ratings_map = _get_ratings_map(list(song_ids))
    all_collab_labels = _get_collab_labels(song_ids, artist.id)

    # Build album → songs structure (no per-album queries)
    discography = []
    for album in albums:
        album_songs = songs_by_album.get(album.id, [])

        # Filter remixes if setting is off
        if not include_remixes:
            album_songs = [(s, tn) for s, tn in album_songs if not s.is_remix]

        # Filter featured songs if setting is off
        if not include_featured:
            album_songs = [(s, tn) for s, tn in album_songs
                           if s.id in main_song_ids]

        if album_songs:
            song_obj_ids = [s.id for s, _ in album_songs]
            ratings_map = {sid: all_ratings_map.get(sid, {}) for sid in song_obj_ids}
            collab_labels = {sid: all_collab_labels[sid] for sid in song_obj_ids if sid in all_collab_labels}
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
