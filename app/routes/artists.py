from flask import Blueprint, request, render_template, redirect, url_for, abort, session
from flask_login import login_required, current_user

from sqlalchemy.orm import selectinload

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
    misc = Artist.query.filter_by(slug='misc. artists').first()
    if misc:
        return redirect(url_for('artists.artist_detail', artist_id=misc.id))
    return redirect(url_for('artists.artist_detail', artist_id=1))


def _slug_url(artist):
    """Build the canonical display URL using the artist's name."""
    from urllib.parse import quote
    return '/artists/' + quote(artist.name, safe="().-&+!?#@*='% ")


@artists_bp.route('/artists/<int:artist_id>')
@login_required
def artist_detail(artist_id):
    """ID URL → redirect to slug URL (or render with HX-Push-Url for HTMX)."""
    artist = db.session.get(Artist, artist_id)
    if not artist:
        abort(404)

    # Subunits: resolve to parent
    if is_subunit(artist_id):
        from app.services.artist import get_parent
        parent = get_parent(artist_id)
        if parent:
            parent_artist = db.session.get(Artist, parent.id)
            if parent_artist:
                artist = parent_artist

    slug_url = _slug_url(artist)

    if request.headers.get('HX-Request'):
        # For HTMX: render directly, push the slug URL to the browser
        return _render_artist(artist, htmx=True, push_url=slug_url)

    return redirect(slug_url)


@artists_bp.route('/artists/<path:artist_slug>')
@login_required
def artist_detail_by_slug(artist_slug):
    """Slug URL — canonical display route. Also handles name lookups."""
    # Try exact name match first (avoids SQL LIKE wildcard issues with % etc.)
    artist = Artist.query.filter(db.func.lower(Artist.name) == artist_slug.lower()).first()
    if not artist:
        artist = Artist.query.filter_by(slug=artist_slug).first()
    if not artist:
        artist = Artist.query.filter(db.func.lower(Artist.slug) == artist_slug.lower()).first()
    if not artist:
        abort(404)

    # Subunits: redirect to parent's slug URL
    if is_subunit(artist.id):
        from app.services.artist import get_parent
        parent = get_parent(artist.id)
        if parent:
            parent_artist = db.session.get(Artist, parent.id)
            if parent_artist:
                if request.headers.get('HX-Request'):
                    return _render_artist(parent_artist, htmx=True, push_url=_slug_url(parent_artist))
                return redirect(_slug_url(parent_artist))

    if request.headers.get('HX-Request'):
        return _render_artist(artist, htmx=True)

    return _render_artist(artist, htmx=False)


def _render_artist(artist, htmx=False, push_url=None):
    """Build and render the artist detail page."""
    from flask import make_response

    artist_id = artist.id
    discography = _build_discography(artist)
    users = _get_display_users()

    # Compute last updated across artist, albums, and songs
    dates = [artist.last_updated] if artist.last_updated else []
    album_dates = db.session.query(Album.last_updated).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).filter(
        ArtistSong.artist_id == artist_id,
        Album.last_updated.isnot(None),
    ).distinct().all()
    dates.extend(r[0] for r in album_dates)
    song_dates = db.session.query(Song.last_updated).join(
        ArtistSong, Song.id == ArtistSong.song_id
    ).filter(
        ArtistSong.artist_id == artist_id,
        Song.last_updated.isnot(None),
    ).distinct().all()
    dates.extend(r[0] for r in song_dates)
    last_updated = max(dates) if dates else None

    # Detect soloist parent (for display on the soloist's own page)
    soloist_parent = get_soloist_parent(artist_id)

    # Build child sections (subunits + soloists)
    children_sections = []
    subunits, soloists = get_children(artist.id)
    soloist_ids = {s.id for s in soloists}
    for child in subunits + soloists:
        child_disco = _build_discography(child)
        children_sections.append({
            'artist': child,
            'discography': child_disco,
            'is_soloist': child.id in soloist_ids,
        })

    # All artists list for edit mode (song artist picker)
    all_artists = []
    if session.get('edit_mode') and current_user.is_editor_or_admin:
        all_artists = Artist.query.order_by(Artist.name).all()

    if htmx:
        resp = make_response(render_template(
            'fragments/artist_discography.html',
            artist=artist, discography=discography, users=users,
            gender_css=GENDER_CSS, children=children_sections,
            soloist_parent=soloist_parent, all_artists=all_artists,
            last_updated=last_updated))
        if push_url:
            resp.headers['HX-Push-Url'] = push_url
        return resp

    navbar = _get_filtered_navbar()
    # Ensure current artist always appears in navbar regardless of filters
    if artist.id not in {a.id for a in navbar}:
        navbar.append(artist)
        navbar.sort(key=lambda a: a.name.lower())
    return render_template('artists.html',
                           navbar_artists=navbar, artist=artist,
                           discography=discography, users=users,
                           gender_css=GENDER_CSS, children=children_sections,
                           soloist_parent=soloist_parent, all_artists=all_artists,
                           last_updated=last_updated)


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

    # Get filter settings — edit mode bypasses remix/featured filters
    from flask import session
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        genre_id = current_user.settings.genre
        include_remixes = True if edit_mode else current_user.settings.include_remixes
        include_featured = True if edit_mode else current_user.settings.include_featured
        album_sort_order = current_user.settings.album_sort_order or 'desc'
    else:
        genre_id = session.get('genre')
        include_remixes = True if edit_mode else False
        include_featured = True if edit_mode else False
        album_sort_order = session.get('album_sort_order', 'desc')

    # Get all albums containing these songs (NULLs sort last)
    if album_sort_order == 'asc':
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.asc()
    else:
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.desc()
    albums = db.session.query(Album).options(
        selectinload(Album.genres),
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

    # Bulk-load all ratings, collab labels, and song-artist associations
    all_ratings_map = _get_ratings_map(list(song_ids))
    all_collab_labels = _get_collab_labels(song_ids, artist.id)

    # Bulk-load all artist associations for songs (for edit mode artist picker)
    all_song_artists_rows = db.session.query(
        ArtistSong.song_id, ArtistSong.artist_id, ArtistSong.artist_is_main, Artist.name
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(song_ids)
    ).all()
    all_song_artists = {}
    for sid, aid, is_main, aname in all_song_artists_rows:
        all_song_artists.setdefault(sid, []).append({'artist_id': aid, 'name': aname, 'is_main': is_main})

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

            song_artists = {sid: all_song_artists.get(sid, []) for sid in song_obj_ids}

            discography.append({
                'album': album,
                'songs': album_songs,
                'ratings': ratings_map,
                'collab_labels': collab_labels,
                'song_artists': song_artists,
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
