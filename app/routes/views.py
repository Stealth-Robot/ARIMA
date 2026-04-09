from datetime import datetime

from flask import Blueprint, render_template, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models.music import Song, Album, Artist, ArtistSong, AlbumSong, ArtistArtist
from app.decorators import role_required, EDITOR_OR_ADMIN

views_bp = Blueprint('views', __name__)


def _misc_artist_ids():
    """Return the set of Misc. Artists + all its subunit IDs."""
    misc = Artist.query.filter_by(name='Misc. Artists').first()
    if not misc:
        return set()
    ids = {misc.id}
    ids |= {r.artist_2 for r in ArtistArtist.query.filter_by(artist_1=misc.id).all()}
    return ids


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
    misc_ids = _misc_artist_ids()
    counts = {
        'orphan_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(AlbumSong.song_id))
        ).count(),
        'no_artist_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(ArtistSong.song_id))
        ).count(),
        'orphan_albums': db.session.query(Album).filter(
            ~Album.id.in_(db.session.query(AlbumSong.album_id)),
            Album.artist_id.is_(None),
        ).count(),
        'empty_albums': db.session.query(Album).filter(
            ~Album.id.in_(db.session.query(AlbumSong.album_id)),
            Album.artist_id.isnot(None),
            ~Album.artist_id.in_(misc_ids),
        ).count(),
        'empty_artists': db.session.query(Artist).filter(
            ~Artist.id.in_(db.session.query(ArtistSong.artist_id))
        ).count(),
        'undated_albums': db.session.query(Album).filter(
            db.or_(Album.release_date.is_(None), Album.release_date == ''),
            db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
        ).count(),
        'incomplete_date_albums': db.session.query(Album).filter(
            Album.release_date.like('%-01-01'),
            db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
        ).count(),
        'potentially_disbanded': _potentially_disbanded_query().count(),
        'incomplete_tabs': db.session.query(Artist).filter(
            Artist.is_complete == False,
        ).count(),
        'duplicate_songs': '…',
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


@views_bp.route('/views/orphan-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_orphan_albums():
    from markupsafe import Markup
    items = db.session.query(Album).filter(
        ~Album.id.in_(db.session.query(AlbumSong.album_id)),
        Album.artist_id.is_(None),
    ).all()
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    result = []
    for a in items:
        name_esc = Markup.escape(a.name)
        label = f'"{name_esc}"'
        if edit_mode:
            label += (f' <span style="cursor:pointer; color:var(--delete-button, #EF4444); margin-left:6px;" title="Delete album"'
                      f' onclick="deleteOrphanAlbum({a.id}, this)">&#10005;</span>')
        result.append({'label': f'id={a.id} — {label}', 'safe': True})
    return render_template('fragments/view_list.html', items=result)


@views_bp.route('/views/empty-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_empty_albums():
    from markupsafe import Markup
    from flask import url_for
    misc_ids = _misc_artist_ids()
    items = db.session.query(Album).filter(
        ~Album.id.in_(db.session.query(AlbumSong.album_id)),
        Album.artist_id.isnot(None),
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
    ).all()
    result = []
    for a in items:
        name_esc = Markup.escape(a.name)
        label = f'<a href="{url_for("artists.artist_detail", artist_id=a.artist_id)}" style="color: var(--link, #2563EB); text-decoration: none;">"{name_esc}"</a>'
        result.append({'label': f'id={a.id} — {label}', 'safe': True})
    return render_template('fragments/view_list.html', items=result)


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
    misc_ids = _misc_artist_ids()
    albums = db.session.query(Album).filter(
        db.or_(Album.release_date.is_(None), Album.release_date == ''),
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
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
    misc_ids = _misc_artist_ids()
    albums = db.session.query(Album).filter(
        Album.release_date.like('%-01-01'),
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
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


_DUPLICATE_IGNORE = {'intro'}


def _duplicate_song_ids():
    """Return set of song IDs flagged as potential duplicates by either strategy."""
    ignore_filter = ~db.func.lower(Song.name).in_(_DUPLICATE_IGNORE)

    # Strategy 1: same name + same main artist
    by_artist = db.session.query(
        db.func.lower(Song.name).label('lower_name'),
        ArtistSong.artist_id.label('artist_id'),
    ).join(
        ArtistSong, db.and_(ArtistSong.song_id == Song.id, ArtistSong.artist_is_main == True)
    ).filter(ignore_filter).group_by(
        db.func.lower(Song.name), ArtistSong.artist_id
    ).having(db.func.count() > 1).subquery()

    ids_1 = {r[0] for r in db.session.query(Song.id).join(
        ArtistSong, db.and_(ArtistSong.song_id == Song.id, ArtistSong.artist_is_main == True)
    ).filter(
        db.tuple_(db.func.lower(Song.name), ArtistSong.artist_id).in_(
            db.session.query(by_artist.c.lower_name, by_artist.c.artist_id)
        )
    ).all()}

    # Strategy 2: same name + albums released within 3 days of each other
    # Step A: find song names that appear on more than one distinct song (cheap)
    repeated_names = db.session.query(
        db.func.lower(Song.name).label('lower_name')
    ).filter(ignore_filter).group_by(
        db.func.lower(Song.name)
    ).having(db.func.count(db.distinct(Song.id)) > 1).subquery()

    # Step B: fetch (song_id, lower_name, julianday) only for repeated names
    candidates = db.session.query(
        Song.id, db.func.lower(Song.name).label('lower_name'),
        db.func.julianday(Album.release_date).label('jd'),
    ).join(
        AlbumSong, AlbumSong.song_id == Song.id
    ).join(
        Album, Album.id == AlbumSong.album_id
    ).filter(
        db.func.lower(Song.name).in_(db.session.query(repeated_names.c.lower_name)),
        Album.release_date.isnot(None), Album.release_date != '',
    ).all()

    # Step C: group by name, compare dates in Python (small set)
    from collections import defaultdict
    by_name = defaultdict(list)
    for song_id, lower_name, jd in candidates:
        if jd is not None:
            by_name[lower_name].append((song_id, jd))

    ids_2 = set()
    for entries in by_name.values():
        entries.sort(key=lambda x: x[1])
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if entries[j][1] - entries[i][1] > 3:
                    break
                if entries[i][0] != entries[j][0]:
                    ids_2.add(entries[i][0])
                    ids_2.add(entries[j][0])

    return ids_1 | ids_2


@views_bp.route('/views/potential-duplicates')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_potential_duplicates():
    song_ids = _duplicate_song_ids()
    if not song_ids:
        return render_template('fragments/view_duplicates.html', groups=[])

    rows = db.session.query(
        Song.id, Song.name, Song.is_remix,
        Artist.name.label('artist_name'), Artist.slug.label('artist_slug'),
        Album.name.label('album_name'),
    ).join(
        ArtistSong, db.and_(ArtistSong.song_id == Song.id, ArtistSong.artist_is_main == True)
    ).join(
        Artist, Artist.id == ArtistSong.artist_id
    ).outerjoin(
        AlbumSong, AlbumSong.song_id == Song.id
    ).outerjoin(
        Album, Album.id == AlbumSong.album_id
    ).filter(
        Song.id.in_(song_ids)
    ).order_by(db.func.lower(Song.name), Artist.name, Song.id).all()

    # Group by lowercase song name
    groups = {}
    for song_id, song_name, is_remix, artist_name, artist_slug, album_name in rows:
        key = song_name.lower()
        if key not in groups:
            groups[key] = {'name': song_name, 'songs': []}
        existing = next((s for s in groups[key]['songs'] if s['id'] == song_id), None)
        if existing:
            if album_name and album_name not in existing['albums']:
                existing['albums'].append(album_name)
        else:
            groups[key]['songs'].append({
                'id': song_id,
                'name': song_name,
                'is_remix': is_remix,
                'artist_name': artist_name,
                'artist_slug': artist_slug,
                'albums': [album_name] if album_name else [],
            })

    sorted_groups = sorted(groups.values(), key=lambda g: g['name'].lower())
    return render_template('fragments/view_duplicates.html', groups=sorted_groups)


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
