from flask import Blueprint, request, render_template, redirect, url_for, abort, session
from flask_login import login_required, current_user

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.music import Artist, Album, Song, Rating, AlbumSong, ArtistSong, ArtistSubscription, album_genres
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.models.duplicate_display_override import DuplicateDisplayOverride
from app.models.user import User
from app.services.artist import get_filtered_navbar, get_children, is_subunit, get_soloist_parents, get_discography_songs

artists_bp = Blueprint('artists', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}


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
    return '/artists/' + quote(artist.name, safe="().-&+!?@*=' ")


@artists_bp.route('/artists/<int:artist_id>')
@login_required
def artist_detail(artist_id):
    """ID URL → redirect to slug URL (or render with HX-Replace-Url for HTMX)."""
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
        # For HTMX: render directly, replace the slug URL in the browser
        return _render_artist(artist, htmx=True, push_url=slug_url)

    return redirect(slug_url)


@artists_bp.route('/artists/<path:artist_slug>')
@login_required
def artist_detail_by_slug(artist_slug):
    """Slug URL — canonical display route. Also handles name lookups."""
    # Try exact name match first (avoids SQL LIKE wildcard issues with % etc.)
    # SQLite lower() only handles ASCII, so fall back to Python comparison for non-ASCII
    artist = Artist.query.filter(Artist.name == artist_slug).first()
    if not artist:
        artist = Artist.query.filter(db.func.lower(Artist.name) == artist_slug.lower()).first()
    if not artist:
        artist = Artist.query.filter_by(slug=artist_slug).first()
    if not artist:
        artist = Artist.query.filter(db.func.lower(Artist.slug) == artist_slug.lower()).first()
    if not artist:
        slug_lower = artist_slug.lower()
        artist = next((a for a in Artist.query.all() if a.name.lower() == slug_lower), None)
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
    # Fetch children early so parent _build_discography can reuse them
    subunits, soloists = get_children(artist.id)

    # Determine if OSTs should be hidden (respects anime page exception)
    ANIME_GENDER_ID = 3
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        _hide_osts = getattr(current_user.settings, 'hide_osts', False) and artist.gender_id != ANIME_GENDER_ID
    else:
        _hide_osts = session.get('hide_osts', False) and artist.gender_id != ANIME_GENDER_ID

    discography = _build_discography(artist, children=(subunits, soloists), hide_osts=_hide_osts)
    users = _get_display_users()

    # Compute last updated across artist, albums, and songs (single query)
    dates = [artist.last_updated] if artist.last_updated else []
    update_rows = db.session.execute(db.text(
        'SELECT last_updated FROM ('
        '  SELECT a.last_updated FROM album a'
        '  JOIN album_song als ON als.album_id = a.id'
        '  JOIN artist_song ars ON ars.song_id = als.song_id'
        '  WHERE ars.artist_id = :aid AND a.last_updated IS NOT NULL'
        '  UNION'
        '  SELECT s.last_updated FROM song s'
        '  JOIN artist_song ars ON ars.song_id = s.id'
        '  WHERE ars.artist_id = :aid AND s.last_updated IS NOT NULL'
        ')'
    ), {'aid': artist_id}).fetchall()
    dates.extend(r[0] for r in update_rows)
    last_updated = max(dates) if dates else None

    # Detect soloist parents (for display on the soloist's own page)
    soloist_parents = get_soloist_parents(artist_id)

    # Build child sections (filtered by active country filter)
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        active_country_ids = list(current_user.settings.country_ids or [])
    else:
        active_country_ids = list(session.get('country_ids') or [])

    children_sections = []
    soloist_ids = {s.id for s in soloists}
    for child in subunits + soloists:
        if active_country_ids and child.country_id not in active_country_ids:
            continue
        child_disco = _build_discography(child, hide_osts=_hide_osts)
        children_sections.append({
            'artist': child,
            'discography': child_disco,
            'is_soloist': child.id in soloist_ids,
        })

    # All artists list + all albums for edit mode (song artist picker, cross-artist move)
    all_artists = []
    all_albums_by_artist = []
    all_songs_by_artist = []
    artist_parent_map = {}
    genres = []
    album_types = []
    countries = []
    genders = []
    if session.get('edit_mode') and current_user.is_editor_or_admin:
        all_artists = Artist.query.order_by(func.lower(Artist.name)).all()
        genres = Genre.query.order_by(Genre.id).all()
        album_types = AlbumType.query.order_by(AlbumType.id).all()
        countries = Country.query.order_by(Country.id).all()
        genders = GroupGender.query.order_by(GroupGender.id).all()
        # Build child→parent name map for grouping subunits under parents
        parent_rows = db.session.execute(db.text(
            'SELECT c.name, p.name FROM artist_artist aa '
            'JOIN artist c ON c.id = aa.artist_2 '
            'JOIN artist p ON p.id = aa.artist_1'
        )).fetchall()
        artist_parent_map = {r[0]: r[1] for r in parent_rows}
        all_albums_by_artist = db.session.execute(db.text(
            'SELECT DISTINCT a.id, a.name, ar.name AS artist_name, ar.id AS artist_id '
            'FROM album a '
            'JOIN album_song als ON als.album_id = a.id '
            'JOIN artist_song ars ON ars.song_id = als.song_id AND ars.artist_is_main = 1 '
            'JOIN artist ar ON ar.id = ars.artist_id '
            'UNION '
            'SELECT DISTINCT a.id, a.name, ar.name AS artist_name, ar.id AS artist_id '
            'FROM album a '
            'JOIN artist ar ON ar.id = a.artist_id '
            'WHERE a.artist_id IS NOT NULL '
            'ORDER BY 3, 2'
        )).fetchall()
        # All songs for merge popover (deduplicated by song id)
        _song_rows = db.session.execute(db.text(
            'SELECT s.id, s.name, ar.name, ar.id, al.name '
            'FROM song s '
            'JOIN artist_song ars ON ars.song_id = s.id AND ars.artist_is_main = 1 '
            'JOIN artist ar ON ar.id = ars.artist_id '
            'JOIN album_song als ON als.song_id = s.id '
            'JOIN album al ON al.id = als.album_id '
            'ORDER BY ar.name, s.name'
        )).fetchall()
        _seen_song_ids = set()
        all_songs_by_artist = []
        for r in _song_rows:
            if r[0] not in _seen_song_ids:
                _seen_song_ids.add(r[0])
                all_songs_by_artist.append(r)

    # Users eligible to be Owner / Maintainer — raters+ (same pool as stats)
    assignable_users = User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all()

    is_subscribed = bool(ArtistSubscription.query.filter_by(
        user_id=current_user.id, artist_id=artist_id).first()) if current_user.can_rate else False

    if htmx:
        resp = make_response(render_template(
            'fragments/artist_discography.html',
            artist=artist, discography=discography, users=users,
            gender_css=GENDER_CSS, children=children_sections,
            soloist_parents=soloist_parents, all_artists=all_artists,
            all_albums_by_artist=all_albums_by_artist,
            all_songs_by_artist=all_songs_by_artist,
            artist_parent_map=artist_parent_map,
            assignable_users=assignable_users,
            is_subscribed=is_subscribed,
            last_updated=last_updated,
            genres=genres, album_types=album_types,
            countries=countries, genders=genders))
        if push_url:
            resp.headers['HX-Push-Url'] = push_url
        return resp

    navbar = _get_filtered_navbar()
    # Ensure current artist always appears in navbar regardless of filters
    if artist.id not in {a.id for a in navbar}:
        navbar.append(artist)
        misc = [a for a in navbar if a.name == 'Misc. Artists']
        rest = sorted([a for a in navbar if a.name != 'Misc. Artists'], key=lambda a: a.name.lower())
        navbar = misc + rest
    return render_template('artists.html',
                           navbar_artists=navbar, artist=artist,
                           discography=discography, users=users,
                           gender_css=GENDER_CSS, children=children_sections,
                           soloist_parents=soloist_parents, all_artists=all_artists,
                           all_albums_by_artist=all_albums_by_artist,
                           all_songs_by_artist=all_songs_by_artist,
                           artist_parent_map=artist_parent_map,
                           assignable_users=assignable_users,
                           is_subscribed=is_subscribed,
                           last_updated=last_updated,
                           genres=genres, album_types=album_types,
                           countries=countries, genders=genders)


def _get_display_users():
    """Get users to show in rating columns, respecting viewer's stats page preferences."""
    from app.services.stats import get_display_users
    return get_display_users()


def _get_filtered_navbar():
    return get_filtered_navbar()


@artists_bp.route('/artist/<int:artist_id>/subscribe', methods=['POST'])
@login_required
def toggle_subscribe(artist_id):
    import json
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)
    sub = ArtistSubscription.query.filter_by(
        user_id=current_user.id, artist_id=artist_id).first()
    if sub:
        db.session.delete(sub)
        subscribed = False
    else:
        db.session.add(ArtistSubscription(user_id=current_user.id, artist_id=artist_id))
        subscribed = True
    db.session.commit()
    return json.dumps({'subscribed': subscribed}), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/artist/<int:artist_id>/unrated-count')
@login_required
def unrated_count(artist_id):
    """Return the number of unrated songs for this artist, respecting user filters."""
    import json
    from sqlalchemy.orm import selectinload as _sel
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        abort(404)

    ANIME_GENDER_ID = 3

    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        settings = current_user.settings
        genre_ids = list(settings.genre_ids or [])
        include_remixes = settings.include_remixes
        include_featured = settings.include_featured
        hide_osts = getattr(settings, 'hide_osts', False)
    else:
        genre_ids = list(session.get('genre_ids') or [])
        include_remixes = False
        include_featured = False
        hide_osts = session.get('hide_osts', False)

    song_ids = {r.song_id for r in ArtistSong.query.filter_by(artist_id=artist.id).all()}
    if not song_ids:
        return json.dumps({'unrated': 0, 'total': 0}), 200, {'Content-Type': 'application/json'}

    songs = Song.query.filter(Song.id.in_(song_ids)).all()

    main_song_ids = None
    if not include_featured:
        children_sub, children_sol = get_children(artist.id)
        all_artist_ids = [artist.id] + [c.id for c in children_sub + children_sol]
        main_song_ids = {r.song_id for r in
                         ArtistSong.query.filter(
                             ArtistSong.artist_id.in_(all_artist_ids),
                             ArtistSong.artist_is_main == True).all()}

    album_song_rows = (db.session.query(AlbumSong.song_id, Album)
                       .join(Album, Album.id == AlbumSong.album_id)
                       .options(_sel(Album.genres))
                       .filter(AlbumSong.song_id.in_(song_ids))
                       .all())
    albums_by_song = {}
    for sid, album in album_song_rows:
        albums_by_song.setdefault(sid, []).append(album)

    rated_ids = {r.song_id for r in Rating.query.filter(
        Rating.user_id == current_user.id,
        Rating.song_id.in_(song_ids)).all()}

    total = 0
    unrated = 0
    for song in songs:
        if not include_remixes and song.is_remix:
            continue
        if not include_featured and main_song_ids is not None and song.id not in main_song_ids:
            continue
        song_albums = albums_by_song.get(song.id, [])
        if not song_albums:
            continue
        if hide_osts and artist.gender_id != ANIME_GENDER_ID:
            if all(any(g.genre == 'OST' for g in a.genres) for a in song_albums):
                continue
        if genre_ids:
            genre_set = set(genre_ids)
            if not any(any(g.id in genre_set for g in a.genres) for a in song_albums):
                continue
        total += 1
        if song.id not in rated_ids:
            unrated += 1

    return json.dumps({'unrated': unrated, 'total': total}), 200, {'Content-Type': 'application/json'}


def _collab_labels_from_song_artists(all_song_artists, artist):
    """Derive collab labels from already-loaded song_artists data (no extra queries)."""
    ANIME_GENDER_ID = 3
    is_anime_page = artist.gender_id == ANIME_GENDER_ID
    song_data = {}
    for sid, artists_list in all_song_artists.items():
        for a in artists_list:
            if a['artist_id'] == artist.id:
                continue
            d = song_data.setdefault(sid, {'main': [], 'feat': [], 'by': [], 'for': []})
            is_other_anime = a['gender_id'] == ANIME_GENDER_ID
            if is_anime_page and not is_other_anime and a['is_main']:
                d['by'].append(a['name'])
            elif not is_anime_page and is_other_anime:
                d['for'].append(a['name'])
            elif a['is_main']:
                d['main'].append(a['name'])
            else:
                d['feat'].append(a['name'])
    labels = {}
    for sid, d in song_data.items():
        parts = []
        if d['main']:
            parts.append('(with ' + ', '.join(d['main']) + ')')
        if d['by']:
            parts.append('(by ' + ', '.join(d['by']) + ')')
        if d['for']:
            parts.append('(for ' + ', '.join(d['for']) + ')')
        if d['feat']:
            parts.append('(feat. ' + ', '.join(d['feat']) + ')')
        if parts:
            labels[sid] = ' '.join(parts)
    return labels


def _build_discography(artist, children=None, hide_osts=False):
    """Build discography data for an artist (own songs only, not children)."""
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist.id).all()}

    # Get filter settings — edit mode bypasses remix/featured filters
    from flask import session
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        genre_ids = list(current_user.settings.genre_ids or [])
        include_remixes = True if edit_mode else current_user.settings.include_remixes
        include_featured = True if edit_mode else current_user.settings.include_featured
        album_sort_order = current_user.settings.album_sort_order or 'desc'
    else:
        genre_ids = list(session.get('genre_ids') or [])
        include_remixes = True if edit_mode else False
        include_featured = True if edit_mode else False
        album_sort_order = session.get('album_sort_order', 'desc')

    # Get all albums containing these songs (NULLs sort last)
    if album_sort_order == 'asc':
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.asc()
    else:
        order = db.case((Album.release_date.is_(None), 1), else_=0).asc(), Album.release_date.desc()

    albums = []
    if song_ids:
        albums = db.session.query(Album).options(
            selectinload(Album.genres),
        ).join(
            AlbumSong, Album.id == AlbumSong.album_id
        ).filter(
            AlbumSong.song_id.in_(song_ids)
        ).distinct().order_by(*order).all()

    # Include empty albums directly linked to this artist via artist_id
    seen_ids = {a.id for a in albums}
    direct_albums = db.session.query(Album).options(
        selectinload(Album.genres),
    ).filter(
        Album.artist_id == artist.id,
        ~Album.id.in_(seen_ids) if seen_ids else db.true()
    ).order_by(*order).all()
    albums.extend(direct_albums)

    if not albums:
        return []

    # Apply genre filter at album level (OR across selected genres)
    if genre_ids:
        genre_set = set(genre_ids)
        albums = [a for a in albums if any(g.id in genre_set for g in a.genres)]

    # Hide OST albums (unless on an anime artist page)
    if hide_osts and not edit_mode:
        albums = [a for a in albums if not any(g.genre == 'OST' for g in a.genres)]

    # Pre-compute main song IDs for featured filter (once, not per-album)
    main_song_ids = None
    if not include_featured:
        if children is None:
            subunits, soloists = get_children(artist.id)
        else:
            subunits, soloists = children
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

    album_id_set = {a.id for a in albums}
    songs_by_album = {}
    for album_id, song, track_num in all_album_songs:
        if album_id in album_id_set:
            songs_by_album.setdefault(album_id, []).append((song, track_num))

    # Deduplicate songs across albums: show each song only in its canonical album.
    # Canonical = oldest non-Single album; if all are Singles, oldest Single.
    # In edit mode, keep all songs but track which would be hidden.
    SINGLE_TYPE_ID = 2
    duplicate_song_album = set()  # (song_id, album_id) pairs that are non-canonical
    album_lookup = {a.id: a for a in albums}
    song_albums = {}
    for aid, song_list in songs_by_album.items():
        for song, _ in song_list:
            song_albums.setdefault(song.id, []).append(aid)

    # Determine canonical album for each duplicate song (auto + overrides)
    duplicate_sids = {sid for sid, aid_list in song_albums.items() if len(aid_list) >= 2}
    overrides = {}
    if duplicate_sids:
        override_rows = DuplicateDisplayOverride.query.filter(
            DuplicateDisplayOverride.song_id.in_(duplicate_sids),
            DuplicateDisplayOverride.artist_id == artist.id,
        ).all()
        overrides = {r.song_id: r.preferred_album_id for r in override_rows}

    for sid, aid_list in song_albums.items():
        if len(aid_list) < 2:
            continue
        # Use override if present, otherwise auto-detect canonical
        if sid in overrides and overrides[sid] in aid_list:
            canonical = overrides[sid]
        else:
            sorted_aids = sorted(aid_list, key=lambda a: (
                album_lookup[a].release_date is None,
                album_lookup[a].release_date or '',
            ))
            canonical = None
            for aid in sorted_aids:
                if album_lookup[aid].album_type_id != SINGLE_TYPE_ID:
                    canonical = aid
                    break
            if canonical is None:
                canonical = sorted_aids[0]
        for aid in aid_list:
            if aid != canonical:
                if edit_mode:
                    duplicate_song_album.add((sid, aid))
                else:
                    songs_by_album[aid] = [(s, tn) for s, tn in songs_by_album[aid] if s.id != sid]

    # Bulk-load all ratings and song-artist associations
    all_ratings_map = _get_ratings_map(list(song_ids))

    all_song_artists_rows = db.session.query(
        ArtistSong.song_id, ArtistSong.artist_id, ArtistSong.artist_is_main, Artist.name, Artist.gender_id
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(song_ids)
    ).all()
    all_song_artists = {}
    for sid, aid, is_main, aname, gid in all_song_artists_rows:
        all_song_artists.setdefault(sid, []).append({'artist_id': aid, 'name': aname, 'is_main': is_main, 'gender_id': gid})

    # Derive collab labels from the song_artists data (no extra queries)
    all_collab_labels = _collab_labels_from_song_artists(all_song_artists, artist)

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

        if album_songs or edit_mode:
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
                'duplicate_songs': {s.id for s, _ in album_songs if (s.id, album.id) in duplicate_song_album},
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
