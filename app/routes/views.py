import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, session, request, abort
from flask_login import login_required, current_user

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.music import Song, Album, Artist, ArtistSong, AlbumSong, ArtistArtist, SongMiscArtist, MiscArtist
from app.models.not_duplicate import NotDuplicate
from app.models.not_variant import NotVariant
from app.models.not_collab import NotCollab
from app.services.dates import is_valid_release_date
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
    """Return {album_id: [{'id': .., 'name': ..}, ...]} for main artists."""
    if not album_ids:
        return {}
    rows = db.session.query(AlbumSong.album_id, Artist.id, Artist.name).join(
        ArtistSong, AlbumSong.song_id == ArtistSong.song_id
    ).join(
        Artist, ArtistSong.artist_id == Artist.id
    ).filter(
        AlbumSong.album_id.in_(album_ids),
        ArtistSong.artist_is_main == True,
    ).distinct().all()
    result = {}
    for album_id, artist_id, artist_name in rows:
        result.setdefault(album_id, []).append({'id': artist_id, 'name': artist_name})
    return result


@views_bp.route('/views')
@login_required
@role_required(EDITOR_OR_ADMIN)
def views_page():
    """Data integrity monitoring page — shows collapsed sections with counts."""
    misc_ids = _misc_artist_ids()
    counts = {
        'orphan_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(AlbumSong.song_id)),
            ~Song.id.in_(db.session.query(SongMiscArtist.song_id)),
            ~Song.id.in_(db.session.query(ArtistSong.song_id)),
        ).count(),
        'no_artist_songs': db.session.query(Song).filter(
            ~Song.id.in_(db.session.query(ArtistSong.song_id)),
            ~Song.id.in_(db.session.query(SongMiscArtist.song_id)),
        ).count(),
        'feat_only_songs': _feat_only_query().count(),
        'dupe_misc_artists': len(_dupe_misc_artists()),
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
            ~Artist.id.in_(db.session.query(ArtistSong.artist_id)),
            ~Artist.id.in_(db.session.query(ArtistArtist.artist_1)),
        ).count(),
        'undated_albums': db.session.query(Album).filter(
            db.or_(Album.release_date.is_(None), Album.release_date == ''),
            db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
        ).count(),
        'incomplete_date_albums': db.session.query(Album).filter(
            Album.release_date.like('%-01-01'),
            Album.date_confirmed == False,
            db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
        ).count(),
        'invalid_date_albums': len(_invalid_date_albums()),
        'potentially_disbanded': _potentially_disbanded_query().count(),
        'incomplete_tabs': db.session.query(Artist).filter(
            Artist.is_complete == False,
        ).count(),
        'no_maintainer_artists': _no_maintainer_artists_query().count(),
        'no_owner_incomplete': _no_owner_incomplete_query().count(),
        'variant_songs': len(_variant_songs()),
        'duplicate_songs': '…',
        'collab_candidates': _collab_candidate_query().count(),
    }
    from app.models.user import User
    assignable_users = User.query.filter(
        User.sort_order.isnot(None)
    ).order_by(User.sort_order).all()
    return render_template('views.html', counts=counts, assignable_users=assignable_users)


@views_bp.route('/views/orphan-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_orphan_songs():
    items = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(AlbumSong.song_id)),
        ~Song.id.in_(db.session.query(SongMiscArtist.song_id)),
        ~Song.id.in_(db.session.query(ArtistSong.song_id)),
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={s.id} — "{s.name}"'} for s in items
    ])


@views_bp.route('/views/no-artist-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_no_artist_songs():
    items = db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(ArtistSong.song_id)),
        ~Song.id.in_(db.session.query(SongMiscArtist.song_id)),
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={s.id} — "{s.name}"'} for s in items
    ])


def _feat_only_query():
    """Songs that have artist links (real and/or misc) but no main artist of any
    kind — i.e. feat-only songs that need a main assigned."""
    return db.session.query(Song).filter(
        db.or_(
            Song.id.in_(db.session.query(ArtistSong.song_id)),
            Song.id.in_(db.session.query(SongMiscArtist.song_id)),
        ),
        ~Song.id.in_(db.session.query(ArtistSong.song_id).filter(ArtistSong.artist_is_main == True)),
        ~Song.id.in_(db.session.query(SongMiscArtist.song_id).filter(SongMiscArtist.artist_is_main == True)),
    )


@views_bp.route('/views/feat-only')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_feat_only():
    songs = _feat_only_query().order_by(func.lower(Song.name)).all()
    song_ids = [s.id for s in songs]
    artist_map = {}
    link_slug = {}
    if song_ids:
        rows = db.session.query(
            ArtistSong.song_id, Artist.id, Artist.name, Artist.slug
        ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
            ArtistSong.song_id.in_(song_ids),
            ArtistSong.artist_is_main == False,
        ).order_by(func.lower(Artist.name)).all()
        for sid, aid, aname, aslug in rows:
            artist_map.setdefault(sid, []).append({'id': aid, 'name': aname, 'kind': 'real'})
            link_slug.setdefault(sid, aslug)  # link song via a featured real artist
        misc_rows = db.session.query(
            SongMiscArtist.song_id, MiscArtist.id, MiscArtist.name
        ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
            SongMiscArtist.song_id.in_(song_ids),
            SongMiscArtist.artist_is_main == False,
        ).order_by(func.lower(MiscArtist.name)).all()
        misc_song_ids = set()
        for sid, mid, mname in misc_rows:
            artist_map.setdefault(sid, []).append({'id': mid, 'name': mname, 'kind': 'misc'})
            misc_song_ids.add(sid)
        # Fallback for misc-only songs: link via the album's artist
        missing = [sid for sid in song_ids if sid not in link_slug]
        if missing:
            alb_rows = db.session.query(AlbumSong.song_id, Artist.slug).join(
                Album, Album.id == AlbumSong.album_id
            ).join(Artist, Artist.id == Album.artist_id).filter(
                AlbumSong.song_id.in_(missing)
            ).all()
            for sid, aslug in alb_rows:
                link_slug.setdefault(sid, aslug)
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    items = []
    for s in songs:
        slug = link_slug.get(s.id)
        if slug:
            link = f'/artists/{slug}#song-{s.id}'        # real/album artist page
        elif s.id in misc_song_ids:
            link = f'/misc#song-{s.id}'                   # misc page (auto-expands)
        else:
            link = None
        items.append({'id': s.id, 'name': s.name, 'link': link,
                      'artists': artist_map.get(s.id, [])})
    return render_template('fragments/view_feat_only.html', items=items, edit_mode=edit_mode)


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
            label += (f' <button class="ml-1 px-2 py-1 rounded text-xs bg-delete text-button-text border-0 cursor-pointer"'
                      f' onclick="deleteOrphanAlbum({a.id}, this)">Delete</button>')
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
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    result = []
    for a in items:
        name_esc = Markup.escape(a.name)
        label = f'<a href="{url_for("artists.artist_detail", artist_id=a.artist_id)}" style="color: var(--link, #2563EB); text-decoration: none;">"{name_esc}"</a>'
        if edit_mode:
            label += (f' <button class="ml-1 px-2 py-1 rounded text-xs bg-delete text-button-text border-0 cursor-pointer"'
                      f' onclick="deleteEmptyAlbum({a.id}, this)">Delete</button>')
        result.append({'label': f'id={a.id} — {label}', 'safe': True})
    return render_template('fragments/view_list.html', items=result)


@views_bp.route('/views/empty-artists')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_empty_artists():
    items = db.session.query(Artist).filter(
        ~Artist.id.in_(db.session.query(ArtistSong.artist_id)),
        ~Artist.id.in_(db.session.query(ArtistArtist.artist_1)),
    ).all()
    return render_template('fragments/view_list.html', items=[
        {'label': f'id={a.id} — "{a.name}"'} for a in items
    ])


@views_bp.route('/views/undated-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_undated_albums():
    misc_ids = _misc_artist_ids()
    albums = db.session.query(Album).options(
        selectinload(Album.genres),
    ).filter(
        db.or_(Album.release_date.is_(None), Album.release_date == ''),
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
    ).order_by(func.lower(Album.name)).all()
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
    albums = db.session.query(Album).options(
        selectinload(Album.genres),
    ).filter(
        Album.release_date.like('%-01-01'),
        Album.date_confirmed == False,
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
    ).order_by(Album.release_date.desc(), func.lower(Album.name)).all()
    album_artists = _album_artists([a.id for a in albums])
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    return render_template('fragments/view_album_dates.html',
                           albums=albums, album_artists=album_artists,
                           edit_mode=edit_mode, id_prefix='incomplete',
                           show_confirm=True)


def _invalid_date_albums():
    """Albums whose release_date is set but isn't a real YYYY-MM-DD calendar date
    (malformed strings or impossible dates like 2021-02-30)."""
    misc_ids = _misc_artist_ids()
    candidates = db.session.query(Album).filter(
        Album.release_date.isnot(None),
        Album.release_date != '',
        db.or_(Album.artist_id.is_(None), ~Album.artist_id.in_(misc_ids)),
    ).order_by(func.lower(Album.name)).all()
    return [a for a in candidates if not is_valid_release_date(a.release_date)]


@views_bp.route('/views/invalid-date-albums')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_invalid_date_albums():
    albums = _invalid_date_albums()
    album_artists = _album_artists([a.id for a in albums])
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    return render_template('fragments/view_invalid_dates.html',
                           albums=albums, album_artists=album_artists,
                           edit_mode=edit_mode)


def _dupe_misc_artists():
    """Misc artists whose name (case-insensitive) matches a real artist or
    another misc artist — likely duplicates that should be merged/relinked."""
    miscs = db.session.query(MiscArtist.id, MiscArtist.name).all()
    counts = dict(db.session.query(
        SongMiscArtist.misc_artist_id, func.count(SongMiscArtist.song_id)
    ).group_by(SongMiscArtist.misc_artist_id).all())
    real_by_name = {}
    for aid, aname, aslug in db.session.query(Artist.id, Artist.name, Artist.slug).all():
        real_by_name.setdefault((aname or '').strip().lower(), []).append(
            {'id': aid, 'name': aname, 'slug': aslug})
    misc_by_name = {}
    for mid, mname in miscs:
        misc_by_name.setdefault((mname or '').strip().lower(), []).append({'id': mid, 'name': mname})

    items = []
    for mid, mname in miscs:
        key = (mname or '').strip().lower()
        real_matches = real_by_name.get(key, [])
        other_misc = [m for m in misc_by_name.get(key, []) if m['id'] != mid]
        if not real_matches and not other_misc:
            continue
        items.append({
            'id': mid, 'name': mname, 'song_count': counts.get(mid, 0),
            'real_matches': real_matches,
            'misc_dupes': [{'name': m['name'], 'song_count': counts.get(m['id'], 0)} for m in other_misc],
        })
    items.sort(key=lambda x: (x['name'] or '').lower())
    return items


@views_bp.route('/views/dupe-misc-artists')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_dupe_misc_artists():
    return render_template('fragments/view_dupe_misc.html', items=_dupe_misc_artists())


def _potentially_disbanded_query():
    """Artists with no songs on albums released in the last 5 years, not already marked disbanded."""
    cutoff = f'{datetime.now(timezone.utc).year - 5}-01-01'
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
    artists = _potentially_disbanded_query().order_by(func.lower(Artist.name)).all()
    return render_template('fragments/view_potentially_disbanded.html', artists=artists)


_VARIANT_RE = re.compile(r'\b(TV|LIVE|instrumental)\b', re.IGNORECASE)


def _variant_songs():
    """Songs with TV, LIVE, or instrumental as whole words, excluding dismissed."""
    candidates = db.session.query(Song).filter(
        db.or_(
            Song.name.ilike('%TV%'),
            Song.name.ilike('%LIVE%'),
            Song.name.ilike('%instrumental%'),
        ),
        ~Song.id.in_(db.session.query(NotVariant.song_id)),
    ).order_by(func.lower(Song.name)).all()
    return [s for s in candidates if _VARIANT_RE.search(s.name)]


@views_bp.route('/views/variant-songs')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_variant_songs():
    songs = _variant_songs()
    edit_mode = session.get('edit_mode') and current_user.is_editor_or_admin
    items = []
    for s in songs:
        artist_names = ', '.join(a.name for a in s.artists) if s.artists else 'no artist'
        items.append({'id': s.id, 'name': s.name, 'artists': artist_names})
    return render_template('fragments/view_variants.html', items=items, edit_mode=edit_mode)


@views_bp.route('/views/dismiss-variant', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def dismiss_variant():
    song_id = request.form.get('song_id', type=int)
    if not song_id:
        abort(400)
    try:
        db.session.add(NotVariant(song_id=song_id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return '', 204


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
    ).order_by(db.func.lower(Song.name), db.func.lower(Artist.name), Song.id).all()

    # Group by lowercase song name
    groups = {}
    for song_id, song_name, is_remix, artist_name, artist_slug, album_name in rows:
        key = song_name.lower()
        if key not in groups:
            groups[key] = {'name': song_name, 'songs': [], 'pairs': []}
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

    # Load featured (non-main) artists for these songs
    all_song_ids = [s['id'] for g in groups.values() for s in g['songs']]
    feat_rows = db.session.query(
        ArtistSong.song_id, Artist.name
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(all_song_ids),
        ArtistSong.artist_is_main == False,
    ).all()
    misc_feat_rows = db.session.query(
        SongMiscArtist.song_id, MiscArtist.name
    ).join(MiscArtist, MiscArtist.id == SongMiscArtist.misc_artist_id).filter(
        SongMiscArtist.song_id.in_(all_song_ids),
        SongMiscArtist.artist_is_main == False,
    ).all()
    feat_map = {}
    for sid, aname in feat_rows:
        feat_map.setdefault(sid, []).append(aname)
    for sid, mname in misc_feat_rows:
        feat_map.setdefault(sid, []).append(mname)
    for g in groups.values():
        for s in g['songs']:
            s['featured_artists'] = feat_map.get(s['id'], [])

    # Load dismissed pairs
    dismissed = {(r.song_id_1, r.song_id_2) for r in NotDuplicate.query.all()}

    # Split into pairs (2 songs each), filtering dismissed
    pair_groups = []
    for group in groups.values():
        song_list = group['songs']
        for i in range(len(song_list)):
            for j in range(i + 1, len(song_list)):
                a, b = song_list[i], song_list[j]
                lo, hi = min(a['id'], b['id']), max(a['id'], b['id'])
                if (lo, hi) not in dismissed:
                    pair_groups.append({
                        'name': group['name'],
                        'songs': [a, b],
                        'id_lo': lo,
                        'id_hi': hi,
                    })

    pair_groups.sort(key=lambda g: g['name'].lower())
    return render_template('fragments/view_duplicates.html', groups=pair_groups)


@views_bp.route('/views/not-duplicate', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def mark_not_duplicate():
    """Mark a pair of songs as not duplicates."""
    song_id_1 = request.form.get('song_id_1', type=int)
    song_id_2 = request.form.get('song_id_2', type=int)
    if not song_id_1 or not song_id_2 or song_id_1 == song_id_2:
        abort(400)
    lo, hi = min(song_id_1, song_id_2), max(song_id_1, song_id_2)
    # Verify both songs still exist (they may have been merged/deleted)
    from app.models.music import Song
    if not db.session.get(Song, lo) or not db.session.get(Song, hi):
        return '', 204  # silently ignore stale pairs
    existing = NotDuplicate.query.get((lo, hi))
    if not existing:
        db.session.add(NotDuplicate(song_id_1=lo, song_id_2=hi))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return '', 204


@views_bp.route('/views/merge-duplicate', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def merge_duplicate():
    """Merge two duplicate songs from the views page (kept_id absorbs absorbed_id)."""
    kept_id = request.form.get('kept_id', type=int)
    absorbed_id = request.form.get('absorbed_id', type=int)
    if not kept_id or not absorbed_id or kept_id == absorbed_id:
        abort(400)
    kept = db.session.get(Song, kept_id)
    absorbed = db.session.get(Song, absorbed_id)
    if not kept or not absorbed:
        return 'Song not found', 404
    from app.routes.edit.song import perform_song_merge
    perform_song_merge(kept, absorbed)
    return '', 204


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


def _no_owner_incomplete_query():
    """Incomplete artists (tab not finished) with no owner assigned.
    Excludes the Misc. Artists bucket and its subunits."""
    misc_ids = _misc_artist_ids()
    q = db.session.query(Artist).filter(
        Artist.is_complete == False,
        Artist.owner_id.is_(None),
    )
    if misc_ids:
        q = q.filter(~Artist.id.in_(misc_ids))
    return q.order_by(Artist.name)


@views_bp.route('/views/no-owner-incomplete')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_no_owner_incomplete():
    artists = _no_owner_incomplete_query().all()
    ids = [a.id for a in artists]
    song_counts = {}
    if ids:
        rows = db.session.query(
            ArtistSong.artist_id, func.count(ArtistSong.song_id)
        ).filter(
            ArtistSong.artist_id.in_(ids),
            ArtistSong.artist_is_main == True,
        ).group_by(ArtistSong.artist_id).all()
        song_counts = {aid: c for aid, c in rows}
    items = [{'artist': a, 'song_count': song_counts.get(a.id, 0)} for a in artists]
    return render_template('fragments/view_no_owner.html', items=items)


def _no_maintainer_artists_query():
    """Artists with a real discography (at least one main-artist song) and no
    maintainer assigned. Excludes the Misc. Artists bucket and its subunits."""
    misc_ids = _misc_artist_ids()
    q = db.session.query(Artist).filter(
        Artist.maintainer_id.is_(None),
        Artist.id.in_(
            db.session.query(ArtistSong.artist_id).filter(ArtistSong.artist_is_main == True)
        ),
    )
    if misc_ids:
        q = q.filter(~Artist.id.in_(misc_ids))
    return q.order_by(Artist.name)


@views_bp.route('/views/no-maintainer-artists')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_no_maintainer_artists():
    artists = _no_maintainer_artists_query().all()
    ids = [a.id for a in artists]
    song_counts = {}
    if ids:
        rows = db.session.query(
            ArtistSong.artist_id, func.count(ArtistSong.song_id)
        ).filter(
            ArtistSong.artist_id.in_(ids),
            ArtistSong.artist_is_main == True,
        ).group_by(ArtistSong.artist_id).all()
        song_counts = {aid: c for aid, c in rows}
    items = [{'artist': a, 'song_count': song_counts.get(a.id, 0)} for a in artists]
    return render_template('fragments/view_no_maintainer.html', items=items)


_COLLAB_LIKE = [
    '%(with %', '%(feat%', '%(ft.%', '%(ft %',
    '%(w/ %', '%(w/%', '%(featuring %', '%(Feat:%',
    '% feat.%', '% feat %', '% ft.%', '% ft %',
    '%Feat. %', '%&Feat.%', '% featuring %',
    '% duet)%', '% duet %', '%(duet %',
    '% solo)%', '%(solo %',
]


def _collab_candidate_query():
    """Songs with feat/ft/with markers in title that don't already have misc artist links."""
    return db.session.query(Song).filter(
        ~Song.id.in_(db.session.query(SongMiscArtist.song_id)),
        ~Song.id.in_(db.session.query(NotCollab.song_id)),
        db.or_(*[Song.name.ilike(p) for p in _COLLAB_LIKE]),
    )


@views_bp.route('/views/collab-candidates')
@login_required
@role_required(EDITOR_OR_ADMIN)
def view_collab_candidates():
    from app.migrations import _extract_collab_names
    songs = _collab_candidate_query().order_by(Song.name).all()
    song_ids = [s.id for s in songs]
    if not song_ids:
        return render_template('fragments/view_collab_candidates.html', items=[])

    artist_rows = db.session.query(
        ArtistSong.song_id, Artist.name, Artist.slug,
    ).join(Artist, Artist.id == ArtistSong.artist_id).filter(
        ArtistSong.song_id.in_(song_ids),
        ArtistSong.artist_is_main == True,
    ).all()
    artist_map = {}
    for sid, aname, aslug in artist_rows:
        artist_map.setdefault(sid, []).append({'name': aname, 'slug': aslug})

    items = []
    for s in songs:
        artists = artist_map.get(s.id, [])
        extracted = _extract_collab_names(s.name)
        items.append({
            'song_id': s.id,
            'song_name': s.name,
            'artists': artists,
            'extracted_names': extracted,
        })

    return render_template('fragments/view_collab_candidates.html', items=items)


@views_bp.route('/views/dismiss-collab', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def dismiss_collab():
    song_id = request.form.get('song_id', type=int)
    if not song_id:
        abort(400)
    try:
        db.session.add(NotCollab(song_id=song_id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return '', 204
