import json

from flask import Blueprint, request, render_template, redirect, url_for, abort, session
from flask_login import login_required, current_user

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.music import Artist, Album, Song, Rating, AlbumSong, ArtistSong, ArtistSubscription, album_genres, song_genres, SongMiscArtist, MiscArtist
from app.models.lookups import Country, Genre, AlbumType, GroupGender
from app.models.duplicate_display_override import DuplicateDisplayOverride
from app.models.user import User
from app.services.artist import get_filtered_navbar, get_children, is_subunit, get_soloist_parents, get_related_artists, get_discography_songs, soloist_parent_map, amp_join, get_parent

artists_bp = Blueprint('artists', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}


@artists_bp.route('/artists', strict_slashes=False)
@login_required
def artists_list():
    """Redirect to the last visited artist, or the first in the navbar.

    Only honor last_artist_id if that artist is still in the user's filtered
    navbar — otherwise a stale id from a prior filter (e.g. aespa while filtered
    to Japanese) would keep redirecting to an artist the user can't see.
    """
    navbar = get_filtered_navbar()
    last_id = session.get('last_artist_id')
    if last_id and any(a.id == last_id for a in navbar):
        return redirect(url_for('artists.artist_detail', artist_id=last_id))
    if navbar:
        return redirect(url_for('artists.artist_detail', artist_id=navbar[0].id))
    return redirect(url_for('misc.misc_page'))


def _slug_url(artist):
    """Build the slug-alias URL from the artist's unique slug."""
    from urllib.parse import quote
    return '/artists/' + quote(artist.slug or '', safe="() .-")


@artists_bp.route('/artists/<int:artist_id>')
@login_required
def artist_detail(artist_id):
    """Canonical id URL — renders directly. Never redirects to the slug."""
    artist = db.session.get(Artist, artist_id)
    if not artist:
        abort(404)

    # Subunits: resolve to parent (the subunit has no standalone page)
    if is_subunit(artist_id):
        from app.services.artist import get_parent
        parent = get_parent(artist_id)
        if parent:
            parent_artist = db.session.get(Artist, parent.id)
            if parent_artist:
                artist = parent_artist

    if request.headers.get('HX-Request'):
        return _render_artist(artist, htmx=True,
                              push_url=url_for('artists.artist_detail', artist_id=artist.id))
    return _render_artist(artist, htmx=False)


@artists_bp.route('/artists/<path:artist_slug>')
@login_required
def artist_detail_by_slug(artist_slug):
    """Slug-alias URL — renders directly. Never redirects to the id."""
    # Resolve by slug only (case-insensitive). Name is not a URL key.
    artist = Artist.query.filter_by(slug=artist_slug).first()
    if not artist:
        artist = Artist.query.filter(db.func.lower(Artist.slug) == artist_slug.lower()).first()
    if not artist:
        abort(404)

    # Subunits: resolve to parent (the subunit has no standalone page)
    if is_subunit(artist.id):
        from app.services.artist import get_parent
        parent = get_parent(artist.id)
        if parent:
            parent_artist = db.session.get(Artist, parent.id)
            if parent_artist:
                artist = parent_artist

    if request.headers.get('HX-Request'):
        return _render_artist(artist, htmx=True, push_url=_slug_url(artist))
    return _render_artist(artist, htmx=False)


def _render_artist(artist, htmx=False, push_url=None):
    """Build and render the artist detail page."""
    from flask import make_response

    session['last_artist_id'] = artist.id
    artist_id = artist.id
    # Per-page, non-persistent bypass of all viewing filters (?nofilter=1)
    bypass_filters = request.args.get('nofilter') == '1'
    # Fetch children early so parent _build_discography can reuse them
    subunits, soloists = get_children(artist.id)

    # Determine if OSTs should be hidden (respects anime page exception)
    ANIME_GENDER_ID = 3
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        _hide_osts = getattr(current_user.settings, 'hide_osts', False) and artist.gender_id != ANIME_GENDER_ID
    else:
        _hide_osts = session.get('hide_osts', False) and artist.gender_id != ANIME_GENDER_ID
    if bypass_filters:
        _hide_osts = False

    discography = _build_discography(artist, children=(subunits, soloists), hide_osts=_hide_osts,
                                     bypass_filters=bypass_filters)
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

    # Related groups (symmetric links, shown on both artists' pages)
    related_artists = get_related_artists(artist_id)

    # Build child sections (filtered by active country filter)
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        active_country_ids = list(current_user.settings.country_ids or [])
    else:
        active_country_ids = list(session.get('country_ids') or [])
    if bypass_filters:
        active_country_ids = []

    children_sections = []
    soloist_ids = {s.id for s in soloists}
    for child in subunits + soloists:
        if active_country_ids and child.country_id not in active_country_ids:
            continue
        child_disco = _build_discography(child, hide_osts=_hide_osts, bypass_filters=bypass_filters)
        children_sections.append({
            'artist': child,
            'discography': child_disco,
            'is_soloist': child.id in soloist_ids,
        })

    # Edit mode data (lightweight — heavy album/song lists are now lazy-loaded via search endpoints)
    all_artists = []
    all_soloist_parents = {}
    artist_parent_map = {}
    edit_genres = []
    edit_album_types = []
    edit_countries = []
    edit_genders = []
    # Editors edit through green-button/click modals at every viewport width, so these
    # globals (lookup tables + the hidden merge-credential form) are always emitted for
    # editors regardless of any edit-mode flag.
    emit_edit_globals = current_user.is_authenticated and current_user.is_editor_or_admin
    if emit_edit_globals:
        all_artists = Artist.query.order_by(func.lower(Artist.name)).all()
        all_soloist_parents = soloist_parent_map([a.id for a in all_artists])
        edit_genres = Genre.query.order_by(Genre.id).all()
        edit_album_types = AlbumType.query.order_by(AlbumType.id).all()
        edit_countries = Country.query.order_by(Country.id).all()
        edit_genders = GroupGender.query.order_by(GroupGender.id).all()
        parent_rows = db.session.execute(db.text(
            'SELECT c.name, p.name FROM artist_artist aa '
            'JOIN artist c ON c.id = aa.artist_2 '
            'JOIN artist p ON p.id = aa.artist_1 '
            'WHERE aa.relationship IN (0, 1)'
        )).fetchall()
        artist_parent_map = {r[0]: r[1] for r in parent_rows}

    # Users eligible to be Owner / Maintainer — raters+ (same pool as stats)
    assignable_users = User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all()

    is_subscribed = bool(ArtistSubscription.query.filter_by(
        user_id=current_user.id, artist_id=artist_id).first()) if current_user.can_rate else False

    from app.routes.misc import get_rated_filter
    rated_filter = 'all' if bypass_filters else get_rated_filter()

    if htmx:
        resp = make_response(render_template(
            'fragments/artist_discography.html',
            artist=artist, discography=discography, users=users,
            gender_css=GENDER_CSS, children=children_sections,
            soloist_parents=soloist_parents, related_artists=related_artists,
            all_artists=all_artists,
            all_soloist_parents=all_soloist_parents,
            artist_parent_map=artist_parent_map,
            assignable_users=assignable_users,
            is_subscribed=is_subscribed,
            last_updated=last_updated,
            edit_genres=edit_genres, edit_album_types=edit_album_types,
            edit_countries=edit_countries, edit_genders=edit_genders,
            emit_edit_globals=emit_edit_globals,
            rated_filter=rated_filter, bypass_filters=bypass_filters))
        if push_url:
            resp.headers['HX-Push-Url'] = push_url
        return resp

    og_song = _build_og_song(request.args.get('song'))
    og_album_count = sum(1 for d in discography if d['album'])
    og_song_count = sum(len(d['songs']) for d in discography)

    navbar = _get_filtered_navbar()
    # Ensure current artist always appears in navbar regardless of filters
    if artist.id not in {a.id for a in navbar} and artist.name != 'Misc. Artists':
        navbar.append(artist)
        navbar = sorted(navbar, key=lambda a: a.name.lower())
    return render_template('artists.html',
                           navbar_artists=navbar, artist=artist,
                           discography=discography, users=users,
                           gender_css=GENDER_CSS, children=children_sections,
                           soloist_parents=soloist_parents, related_artists=related_artists,
                           all_artists=all_artists,
                           all_soloist_parents=all_soloist_parents,
                           artist_parent_map=artist_parent_map,
                           assignable_users=assignable_users,
                           is_subscribed=is_subscribed,
                           last_updated=last_updated,
                           edit_genres=edit_genres, edit_album_types=edit_album_types,
                           edit_countries=edit_countries, edit_genders=edit_genders,
                           emit_edit_globals=emit_edit_globals,
                           rated_filter=rated_filter,
                           bypass_filters=bypass_filters,
                           og_song=og_song,
                           og_album_count=og_album_count,
                           og_song_count=og_song_count)


def _get_display_users():
    """Get users to show in rating columns, respecting viewer's stats page preferences."""
    from app.services.stats import get_display_users
    return get_display_users()


def _build_og_song(song_param):
    if not song_param:
        return None
    try:
        song = db.session.get(Song, int(song_param))
    except (ValueError, TypeError):
        return None
    if not song:
        return None

    album = db.session.query(Album).join(
        AlbumSong, Album.id == AlbumSong.album_id
    ).filter(AlbumSong.song_id == song.id).order_by(Album.release_date).first()

    genre_names = []
    if album:
        genre_names = [g.genre for g in album.genres]
    if not genre_names:
        genre_names = [g.genre for g in song.genres]

    avg, count = db.session.query(
        func.avg(Rating.rating), func.count(Rating.rating)
    ).filter(Rating.song_id == song.id, Rating.rating.isnot(None)).first()
    rating_summary = None
    if count:
        rating_summary = 'avg %s/5 (%d rating%s)' % (
            round(avg, 1), count, '' if count == 1 else 's')

    return {
        'name': song.name,
        'album': album.name if album else None,
        'release_date': album.release_date if album else None,
        'genres': genre_names,
        'rating_summary': rating_summary,
    }


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
        include_covers = settings.include_covers
        hide_osts = getattr(settings, 'hide_osts', False)
    else:
        genre_ids = list(session.get('genre_ids') or [])
        include_remixes = False
        include_featured = False
        include_covers = True
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

    from app.services.preferences import rated_remix_override_ids
    keep_remix_ids = rated_remix_override_ids(include_remixes, song_ids)

    total = 0
    unrated = 0
    for song in songs:
        if not include_remixes and song.is_remix and song.id not in keep_remix_ids:
            continue
        if not include_covers and song.is_cover:
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


def _collab_labels_from_song_artists(all_song_artists, artist, all_song_misc_artists=None):
    """Derive collab labels from already-loaded song_artists data (no extra queries).

    If all_song_misc_artists is provided, misc artists are bucketed alongside real
    artists so they share the same (by …)/(with …)/(feat. …) groups. On anime pages
    a main misc artist is the primary singer ("by"), mirroring main real artists.

    The Solo rules only apply when a soloist's parent group is itself a main credit
    on the song: such soloists render as "(a & b Solo)" after the with-group, the
    page artist (if one of them) is included so the same label shows on every
    soloist's page, and the credited parent is dropped from the with-group (its
    credit is implied by the Solo credit). A soloist whose parent is not on the
    song is a normal artist (with/feat).
    """
    ANIME_GENDER_ID = 3
    is_anime_page = artist.gender_id == ANIME_GENDER_ID
    def _empty():
        return {'with': [], 'feat': [], 'by': [], 'for': [], 'solo': [],
                'solo_parent_ids': set()}
    song_data = {}
    for sid, artists_list in all_song_artists.items():
        d = song_data.setdefault(sid, _empty())
        main_ids = {a['artist_id'] for a in artists_list if a['is_main']}
        for a in artists_list:
            is_solo_credit = (a['is_main'] and a.get('is_soloist')
                              and main_ids & set(a.get('soloist_parent_ids') or ()))
            if a['artist_id'] == artist.id:
                if is_solo_credit:
                    d['solo'].append(a['name'])
                    d['solo_parent_ids'].update(a.get('soloist_parent_ids') or ())
                continue
            is_other_anime = a['gender_id'] == ANIME_GENDER_ID
            if is_anime_page and not is_other_anime and a['is_main']:
                d['by'].append(a['name'])
            elif not is_anime_page and is_other_anime:
                d['for'].append(a['name'])
            elif a['is_main']:
                if is_solo_credit:
                    d['solo'].append(a['name'])
                    d['solo_parent_ids'].update(a.get('soloist_parent_ids') or ())
                else:
                    d['with'].append((a['artist_id'], a['name']))
            else:
                d['feat'].append(a['name'])
    for sid, misc_list in (all_song_misc_artists or {}).items():
        for m in misc_list:
            d = song_data.setdefault(sid, _empty())
            if not m['is_main']:
                d['feat'].append(m['name'])
            elif is_anime_page:
                d['by'].append(m['name'])
            else:
                d['with'].append((None, m['name']))
    labels = {}
    for sid, d in song_data.items():
        solo_names = d['solo']
        with_names = [name for aid, name in d['with']
                      if not (solo_names and aid is not None and aid in d['solo_parent_ids'])]
        parts = []
        if with_names:
            parts.append('(with ' + amp_join(with_names) + ')')
        if solo_names:
            parts.append('(' + amp_join(solo_names) + ' Solo)')
        if d['by']:
            parts.append('(by ' + amp_join(d['by']) + ')')
        if d['for']:
            parts.append('(for ' + amp_join(d['for']) + ')')
        if d['feat']:
            parts.append('(feat. ' + amp_join(d['feat']) + ')')
        if parts:
            labels[sid] = ' '.join(parts)
    return labels


def _build_discography(artist, children=None, hide_osts=False, bypass_filters=False):
    """Build discography data for an artist (own songs only, not children)."""
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist.id).all()}

    # Get filter settings. "Disable Filters" (bypass_filters / nofilter=1) reveals all
    # otherwise-hidden content so editors can reach those rows to edit them.
    from flask import session
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        genre_ids = list(current_user.settings.genre_ids or [])
        include_remixes = current_user.settings.include_remixes
        include_featured = current_user.settings.include_featured
        include_covers = current_user.settings.include_covers
        album_sort_order = current_user.settings.album_sort_order or 'desc'
    else:
        genre_ids = list(session.get('genre_ids') or [])
        include_remixes = False
        include_featured = False
        include_covers = True
        album_sort_order = session.get('album_sort_order', 'desc')
    if bypass_filters:
        genre_ids = []
        include_remixes = True
        include_featured = True
        include_covers = True

    from app.services.preferences import rated_remix_override_ids
    keep_remix_ids = rated_remix_override_ids(include_remixes, song_ids)

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
    if hide_osts and not bypass_filters:
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
    ).options(
        selectinload(Song.aliases)
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
                if bypass_filters:
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
    solo_parents = soloist_parent_map({row[1] for row in all_song_artists_rows})
    all_song_artists = {}
    for sid, aid, is_main, aname, gid in all_song_artists_rows:
        all_song_artists.setdefault(sid, []).append({'artist_id': aid, 'name': aname, 'is_main': is_main, 'gender_id': gid, 'is_soloist': aid in solo_parents, 'soloist_parent_ids': solo_parents.get(aid, [])})

    # Bulk-load misc artist associations for collab labels + manage popover
    all_song_misc_rows = db.session.query(
        SongMiscArtist.song_id, SongMiscArtist.misc_artist_id,
        SongMiscArtist.artist_is_main, MiscArtist.name
    ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
        SongMiscArtist.song_id.in_(song_ids)
    ).all()
    all_song_misc_artists = {}
    for sid, maid, is_main, mname in all_song_misc_rows:
        all_song_misc_artists.setdefault(sid, []).append({
            'misc_artist_id': maid, 'name': mname, 'is_main': is_main,
        })

    # Derive collab labels from both real and misc artist data
    all_collab_labels = _collab_labels_from_song_artists(
        all_song_artists, artist, all_song_misc_artists)

    # Build album → songs structure (no per-album queries)
    discography = []
    for album in albums:
        album_songs = songs_by_album.get(album.id, [])

        # Filter remixes if setting is off
        if not include_remixes:
            album_songs = [(s, tn) for s, tn in album_songs
                           if not s.is_remix or s.id in keep_remix_ids]

        # Filter covers if setting is off
        if not include_covers:
            album_songs = [(s, tn) for s, tn in album_songs if not s.is_cover]

        # Filter featured songs if setting is off
        if not include_featured:
            album_songs = [(s, tn) for s, tn in album_songs
                           if s.id in main_song_ids]

        if album_songs or bypass_filters:
            song_obj_ids = [s.id for s, _ in album_songs]
            ratings_map = {sid: all_ratings_map.get(sid, {}) for sid in song_obj_ids}
            collab_labels = {sid: all_collab_labels[sid] for sid in song_obj_ids if sid in all_collab_labels}

            song_artists = {sid: all_song_artists.get(sid, []) for sid in song_obj_ids}
            song_misc_artists = {sid: all_song_misc_artists.get(sid, []) for sid in song_obj_ids}

            discography.append({
                'album': album,
                'songs': album_songs,
                'ratings': ratings_map,
                'collab_labels': collab_labels,
                'song_artists': song_artists,
                'song_misc_artists': song_misc_artists,
                'duplicate_songs': {s.id for s, _ in album_songs if (s.id, album.id) in duplicate_song_album},
            })

    # Virtual "Misc" section: songs linked to this artist that didn't appear in any album above
    covered_sids = set()
    for entry in discography:
        for s, _ in entry['songs']:
            covered_sids.add(s.id)
    misc_sids = song_ids - covered_sids
    if misc_sids:
        misc_songs_objs = {s.id: s for s in Song.query.filter(Song.id.in_(misc_sids)).all()}
        if not include_remixes:
            misc_songs_objs = {sid: s for sid, s in misc_songs_objs.items()
                               if not s.is_remix or sid in keep_remix_ids}
        if not include_covers:
            misc_songs_objs = {sid: s for sid, s in misc_songs_objs.items() if not s.is_cover}
        if not include_featured:
            misc_songs_objs = {sid: s for sid, s in misc_songs_objs.items() if sid in main_song_ids}
        if genre_ids:
            sg_rows = db.session.execute(
                song_genres.select().where(song_genres.c.song_id.in_(misc_songs_objs.keys()))
            ).fetchall()
            sg_map = {}
            for sid, gid in sg_rows:
                sg_map.setdefault(sid, set()).add(gid)
            genre_set = set(genre_ids)
            misc_songs_objs = {sid: s for sid, s in misc_songs_objs.items()
                               if sg_map.get(sid, set()) & genre_set}
        if hide_osts and not bypass_filters:
            ost_sids = set()
            misc_album_rows = db.session.query(AlbumSong.song_id, Album).join(
                Album, Album.id == AlbumSong.album_id
            ).options(selectinload(Album.genres)).filter(
                AlbumSong.song_id.in_(misc_songs_objs.keys())
            ).all()
            misc_albums_by_song = {}
            for sid, alb in misc_album_rows:
                misc_albums_by_song.setdefault(sid, []).append(alb)
            for sid, albs in misc_albums_by_song.items():
                if all(any(g.genre == 'OST' for g in a.genres) for a in albs):
                    ost_sids.add(sid)
            misc_songs_objs = {sid: s for sid, s in misc_songs_objs.items() if sid not in ost_sids}
        if misc_songs_objs:
            misc_song_list = sorted(misc_songs_objs.values(), key=lambda s: (s.name or '').lower())
            misc_song_tuples = [(s, None) for s in misc_song_list]
            misc_obj_ids = [s.id for s in misc_song_list]
            discography.append({
                'album': None,
                'songs': misc_song_tuples,
                'ratings': {sid: all_ratings_map.get(sid, {}) for sid in misc_obj_ids},
                'collab_labels': {sid: all_collab_labels[sid] for sid in misc_obj_ids if sid in all_collab_labels},
                'song_artists': {sid: all_song_artists.get(sid, []) for sid in misc_obj_ids},
                'song_misc_artists': {sid: all_song_misc_artists.get(sid, []) for sid in misc_obj_ids},
                'duplicate_songs': set(),
                'is_misc_section': True,
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


@artists_bp.route('/song/<int:song_id>/info')
@login_required
def song_info(song_id):
    """Full song details for the mobile song-info popup."""
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)

    real = db.session.query(Artist.name, ArtistSong.artist_is_main).join(
        ArtistSong, ArtistSong.artist_id == Artist.id
    ).filter(ArtistSong.song_id == song_id).order_by(func.lower(Artist.name)).all()
    misc = db.session.query(MiscArtist.name, SongMiscArtist.artist_is_main).join(
        SongMiscArtist, SongMiscArtist.misc_artist_id == MiscArtist.id
    ).filter(SongMiscArtist.song_id == song_id).order_by(func.lower(MiscArtist.name)).all()

    main_artists = [r[0] for r in real if r[1]] + [m[0] for m in misc if m[1]]
    featured_artists = [r[0] for r in real if not r[1]] + [m[0] for m in misc if not m[1]]

    albums = [{
        'name': a.name,
        'year': a.release_date[:4] if a.release_date else '',
        'genres': [g.genre for g in a.genres],
    } for a in song.albums]

    return json.dumps({
        'name': song.name,
        'main_artists': main_artists,
        'featured_artists': featured_artists,
        'albums': albums,
        'genres': [g.genre for g in song.genres],
        'is_lead': song.is_lead,
        'is_promoted': song.is_promoted,
        'is_cover': song.is_cover,
        'is_remix': song.is_remix,
        'note': song.note or '',
        'spotify_url': song.spotify_url or '',
        'youtube_url': song.youtube_url or '',
        'aliases': [{'name': a.name, 'native_lang': a.native_lang} for a in song.aliases],
    }), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/album/<int:album_id>/songs')
@login_required
def album_songs(album_id):
    """Ordered songs in an album with their flags — for the mobile album-edit modal."""
    album = db.session.get(Album, album_id)
    if album is None:
        abort(404)
    rows = db.session.query(Song).join(
        AlbumSong, AlbumSong.song_id == Song.id
    ).filter(AlbumSong.album_id == album_id).order_by(AlbumSong.track_number).all()
    return json.dumps({
        'album_name': album.name,
        'release_date': album.release_date or '',
        'album_type': album.album_type.type if album.album_type else '',
        'album_type_id': album.album_type_id,
        'spotify_url': album.spotify_url or '',
        'genres': [g.genre for g in album.genres],
        'genre_ids': [g.id for g in album.genres],
        'alt_names': [{'name': n.name, 'native_lang': n.native_lang} for n in album.alt_names],
        'songs': [{
            'id': s.id,
            'name': s.name,
            'is_promoted': s.is_promoted,
            'is_remix': s.is_remix,
            'is_cover': s.is_cover,
            'is_lead': s.is_lead,
        } for s in rows],
    }), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/lookups/genres')
@login_required
def lookup_genres():
    rows = Genre.query.order_by(func.lower(Genre.genre)).all()
    return json.dumps([{'id': g.id, 'name': g.genre} for g in rows]), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/lookups/album-types')
@login_required
def lookup_album_types():
    rows = AlbumType.query.order_by(AlbumType.id).all()
    return json.dumps([{'id': t.id, 'name': t.type} for t in rows]), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/lookups/genders')
@login_required
def lookup_genders():
    rows = GroupGender.query.order_by(GroupGender.id).all()
    return json.dumps([{'id': g.id, 'name': g.gender} for g in rows]), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/lookups/countries')
@login_required
def lookup_countries():
    rows = Country.query.order_by(Country.country).all()
    return json.dumps([{'id': c.id, 'name': c.country} for c in rows]), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/lookups/users')
@login_required
def lookup_users():
    rows = User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all()
    return json.dumps([{'id': u.id, 'name': u.username} for u in rows]), 200, {'Content-Type': 'application/json'}


@artists_bp.route('/artist/<int:artist_id>/edit-info')
@login_required
def artist_edit_info(artist_id):
    """Artist fields for the mobile artist-edit modal."""
    a = db.session.get(Artist, artist_id)
    if a is None:
        abort(404)
    # Relationships this artist can be unlinked from (other-artist id is passed as
    # parent_id to /edit/artist/<id>/unlink). Covers subunit/soloist parents + related.
    links = []
    _sub_parent = get_parent(artist_id)
    if _sub_parent:
        links.append({'id': _sub_parent.id, 'name': _sub_parent.name, 'rel': 'subunit'})
    for sp in get_soloist_parents(artist_id):
        links.append({'id': sp.id, 'name': sp.name, 'rel': 'soloist'})
    for ra in get_related_artists(artist_id):
        links.append({'id': ra.id, 'name': ra.name, 'rel': 'related'})
    return json.dumps({
        'name': a.name,
        'spotify_url': a.spotify_url or '',
        'image_url': a.image_url or '',
        'gender_id': a.gender_id,
        'gender': a.gender.gender if a.gender else '',
        'country_id': a.country_id,
        'country': a.country.country if a.country else '',
        'owner_id': a.owner_id,
        'owner': a.owner.username if a.owner else '',
        'maintainer_id': a.maintainer_id,
        'maintainer': a.maintainer.username if a.maintainer else '',
        'is_disbanded': a.is_disbanded,
        'is_complete': a.is_complete,
        'is_tracked': a.is_tracked,
        'alt_names': [n.name for n in a.alt_names],
        'links': links,
    }), 200, {'Content-Type': 'application/json'}
