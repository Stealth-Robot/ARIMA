"""Stats calculation service — SQL-aggregated, viewer-relative."""

import os
import math
import threading
import time
from collections import defaultdict

from app.extensions import db
from app.models.music import Rating, ArtistSong, Song, ArtistArtist, AlbumSong, Album, album_genres, Artist
from app.models.user import User

SCORED_GROUP_THRESHOLD = 0.80
SUBUNIT = 0

# Wall-clock time this module was imported — close enough to process start for uptime.
_PROCESS_START = time.time()

# Cap concurrent _BulkData builds. Each build transiently allocates ~60-70MB on
# top of its ~40MB retained result; with 11 worker threads, unbounded concurrent
# builds could stack into an OOM at the 500MB limit. 3 permits bounds the spike.
_BUILD_SEMAPHORE = threading.Semaphore(2)


def get_app_ops_stats():
    """In-process operational stats: DB file size, uptime, and row counts.

    Cheap to compute (one stat() call + a handful of COUNTs), so it's not cached.
    """
    db_path = db.engine.url.database
    db_size = os.path.getsize(db_path) if db_path and os.path.exists(db_path) else None

    return {
        'db_path': db_path,
        'db_size_bytes': db_size,
        'process_start': _PROCESS_START,
        'uptime_seconds': time.time() - _PROCESS_START,
        'counts': {
            'artists': db.session.query(Artist).count(),
            'albums': db.session.query(Album).count(),
            'songs': db.session.query(Song).count(),
            'ratings': db.session.query(Rating).count(),
            'users': db.session.query(User).count(),
        },
    }


def _is_mobile():
    """Check if the current request is from a mobile device."""
    from flask import request as _req
    ua = (_req.headers.get('User-Agent') or '').lower()
    return any(k in ua for k in ('iphone', 'android', 'mobile', 'ipod'))


def get_display_users(viewer=None):
    """Users shown in stats columns, respecting viewer's stats page user preferences."""
    from flask_login import current_user as _cu
    from app.models.user import StatsPageUser

    viewer = viewer or _cu
    default = User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all()

    if not viewer.is_authenticated or viewer.is_system_or_guest:
        return default

    # If mobile-only is on and we're not on mobile, skip prefs
    if viewer.settings and getattr(viewer.settings, 'stats_users_mobile_only', True):
        if not _is_mobile():
            return default

    prefs = StatsPageUser.query.filter_by(owner_id=viewer.id).all()
    if not prefs:
        return default

    pref_map = {p.target_user_id: p for p in prefs}
    user_map = {u.id: u for u in default}

    # Users with prefs: visible ones sorted by pref order
    result = []
    for p in sorted(prefs, key=lambda p: p.sort_order):
        if p.visible and p.target_user_id in user_map:
            result.append(user_map[p.target_user_id])

    # Append any new users not in prefs (visible by default)
    for u in default:
        if u.id not in pref_map:
            result.append(u)

    return result


class _BulkData:
    """Pre-loaded stats via SQL aggregation (~5 queries, but returns aggregated rows)."""

    def __init__(self, include_featured, include_remixes, include_covers=True, artist_ids=None, genre_ids=None, hide_osts=False, keep_remix_ids=None):
        scoped = artist_ids is not None
        keep_remix_ids = set(keep_remix_ids or ())

        # 0. If genre filter is active, find song IDs that belong to albums with any selected genre
        if genre_ids:
            self._genre_song_ids = {row[0] for row in db.session.query(AlbumSong.song_id).join(
                album_genres, AlbumSong.album_id == album_genres.c.album_id
            ).filter(album_genres.c.genre_id.in_(genre_ids)).all()}
        else:
            self._genre_song_ids = None

        # 0b. If hiding OSTs, find OST song IDs and anime artist IDs
        if hide_osts:
            from app.models.lookups import Genre
            ost_genre = Genre.query.filter_by(genre='OST').first()
            if ost_genre:
                self._ost_song_ids = {row[0] for row in db.session.query(AlbumSong.song_id).join(
                    album_genres, AlbumSong.album_id == album_genres.c.album_id
                ).filter(album_genres.c.genre_id == ost_genre.id).all()}
            else:
                self._ost_song_ids = set()
            self._anime_artist_ids = {row[0] for row in db.session.query(Artist.id).filter(Artist.gender_id == 3).all()}
        else:
            self._ost_song_ids = None
            self._anime_artist_ids = set()

        # 1. Artist-song mappings (still needed for song_id resolution)
        as_q = db.session.query(ArtistSong.artist_id, ArtistSong.song_id, ArtistSong.artist_is_main)
        if scoped:
            as_q = as_q.filter(ArtistSong.artist_id.in_(artist_ids))
        self.artist_songs = defaultdict(set)
        self.artist_main_songs = defaultdict(set)
        for artist_id, song_id, is_main in as_q.all():
            self.artist_songs[artist_id].add(song_id)
            if is_main:
                self.artist_main_songs[artist_id].add(song_id)

        # 2. Subunit relationships
        rels_q = db.session.query(ArtistArtist.artist_1, ArtistArtist.artist_2).filter(
            ArtistArtist.relationship == SUBUNIT)
        if scoped:
            rels_q = rels_q.filter(
                db.or_(ArtistArtist.artist_1.in_(artist_ids), ArtistArtist.artist_2.in_(artist_ids)))
        self.subunit_ids = set()
        self.children = defaultdict(list)
        for artist_1, artist_2 in rels_q.all():
            self.subunit_ids.add(artist_2)
            self.children[artist_1].append(artist_2)

        # 3. Remix song IDs
        if not include_remixes:
            all_song_ids = set()
            for song_ids in self.artist_songs.values():
                all_song_ids |= song_ids
            if scoped and all_song_ids:
                self.remix_ids = {row[0] for row in db.session.query(Song.id).filter(Song.is_remix == True, Song.id.in_(all_song_ids)).all()}
            elif scoped:
                self.remix_ids = set()
            else:
                self.remix_ids = {row[0] for row in db.session.query(Song.id).filter(Song.is_remix == True).all()}
            # Keep remixes the viewer has rated visible (opt-in 'show rated remixes')
            if keep_remix_ids:
                self.remix_ids -= keep_remix_ids
        else:
            self.remix_ids = set()

        # 3b. Cover song IDs
        if not include_covers:
            all_song_ids = set()
            for song_ids in self.artist_songs.values():
                all_song_ids |= song_ids
            if scoped and all_song_ids:
                self.cover_ids = {row[0] for row in db.session.query(Song.id).filter(Song.is_cover == True, Song.id.in_(all_song_ids)).all()}
            elif scoped:
                self.cover_ids = set()
            else:
                self.cover_ids = {row[0] for row in db.session.query(Song.id).filter(Song.is_cover == True).all()}
        else:
            self.cover_ids = set()

        # 4. SQL-aggregated ratings: per song_id per user_id → count and sum
        #    Returns (song_id, user_id, rating_count, rating_sum)
        if scoped:
            all_song_ids_flat = set()
            for song_ids in self.artist_songs.values():
                all_song_ids_flat |= song_ids
            if all_song_ids_flat:
                agg_rows = db.session.query(
                    Rating.song_id,
                    Rating.user_id,
                    db.func.count(Rating.rating),
                    db.func.sum(Rating.rating),
                ).filter(
                    Rating.song_id.in_(all_song_ids_flat),
                    Rating.rating.isnot(None),
                ).group_by(Rating.song_id, Rating.user_id).all()
            else:
                agg_rows = []
        else:
            agg_rows = db.session.query(
                Rating.song_id,
                Rating.user_id,
                db.func.count(Rating.rating),
                db.func.sum(Rating.rating),
            ).filter(
                Rating.rating.isnot(None),
            ).group_by(Rating.song_id, Rating.user_id).all()

        # Build lookup: song_id → {user_id: (count, sum)}. Tuples instead of dicts
        # (and no parallel rated_by set — keys are the raters) cut this map's heap
        # from ~33MB to ~11MB per cached entry.
        self.song_user_stats = defaultdict(dict)
        for song_id, user_id, cnt, total in agg_rows:
            self.song_user_stats[song_id][user_id] = (cnt, total)

        # 5. All main song IDs (for featured filter)
        if not include_featured:
            self.all_main_song_ids = set()
            for song_ids in self.artist_main_songs.values():
                self.all_main_song_ids |= song_ids
        else:
            self.all_main_song_ids = None

        # 6. All song IDs (for total count)
        if scoped:
            self.all_song_ids = set()
            for song_ids in self.artist_songs.values():
                self.all_song_ids |= song_ids
            if not include_remixes:
                self.all_song_ids -= self.remix_ids
            if not include_covers:
                self.all_song_ids -= self.cover_ids
            if not include_featured and self.all_main_song_ids is not None:
                self.all_song_ids &= self.all_main_song_ids
        else:
            all_songs_query = Song.query
            if not include_remixes:
                if keep_remix_ids:
                    all_songs_query = all_songs_query.filter(
                        db.or_(Song.is_remix == False, Song.id.in_(keep_remix_ids)))
                else:
                    all_songs_query = all_songs_query.filter(Song.is_remix == False)
            if not include_covers:
                all_songs_query = all_songs_query.filter(Song.is_cover == False)
            all_songs_query = all_songs_query.with_entities(Song.id)
            self.all_song_ids = {row[0] for row in all_songs_query.all()}
            if not include_featured and self.all_main_song_ids is not None:
                self.all_song_ids &= self.all_main_song_ids
        if self._genre_song_ids is not None:
            self.all_song_ids &= self._genre_song_ids

        # Exclude OST songs from total — but keep ones that belong to anime artists
        if self._ost_song_ids:
            anime_ost_songs = set()
            for aid in self._anime_artist_ids:
                anime_ost_songs |= (self.artist_songs.get(aid, set()) & self._ost_song_ids)
            self.all_song_ids -= (self._ost_song_ids - anime_ost_songs)

        self.include_featured = include_featured
        self.include_remixes = include_remixes
        self.include_covers = include_covers

    def get_song_ids(self, artist_id):
        """Get filtered song IDs for an artist (including subunit songs)."""
        song_ids = set(self.artist_songs.get(artist_id, set()))
        for child_id in self.children.get(artist_id, []):
            song_ids |= self.artist_songs.get(child_id, set())

        if not self.include_remixes:
            song_ids -= self.remix_ids

        if not self.include_covers:
            song_ids -= self.cover_ids

        if not self.include_featured:
            main_ids = set(self.artist_main_songs.get(artist_id, set()))
            for child_id in self.children.get(artist_id, []):
                main_ids |= self.artist_main_songs.get(child_id, set())
            song_ids &= main_ids

        if self._genre_song_ids is not None:
            song_ids &= self._genre_song_ids

        # Exclude OST songs for non-anime artists
        if self._ost_song_ids:
            all_ids = {artist_id} | set(self.children.get(artist_id, []))
            if not (all_ids & self._anime_artist_ids):
                song_ids -= self._ost_song_ids

        return song_ids

    def has_subunits(self, artist_id):
        return bool(self.children.get(artist_id))


def _artist_completion_stats(artist_id, users, bulk):
    """Calculate per-artist rating completion stats (Artist Stats page)."""
    song_ids = bulk.get_song_ids(artist_id)
    song_count = len(song_ids)

    if song_count == 0:
        return {
            'song_ids': set(),
            'song_count': 0,
            'per_user': {u.id: {'rated_count': 0, 'unrated_count': 0, 'pct_rated': 0.0} for u in users},
            'global_avg_pct': 0.0,
            'global_avg_unrated': 0,
        }

    # Count ratings per user from pre-aggregated data
    user_rated = defaultdict(int)
    for sid in song_ids:
        for uid in bulk.song_user_stats.get(sid, {}):
            user_rated[uid] += 1

    per_user = {}
    pcts_for_global = []
    for u in users:
        rated = user_rated.get(u.id, 0)
        pct = (rated / song_count * 100) if song_count > 0 else 0.0
        per_user[u.id] = {
            'rated_count': rated,
            'unrated_count': song_count - rated,
            'pct_rated': round(pct, 1),
        }
        if rated > 0:
            pcts_for_global.append(pct)

    global_avg_pct = round(sum(pcts_for_global) / len(pcts_for_global), 1) if pcts_for_global else 0.0
    unrated_counts = [per_user[u.id]['unrated_count'] for u in users]
    global_avg_unrated = math.ceil(sum(unrated_counts) / len(unrated_counts)) if unrated_counts else 0

    return {
        'song_ids': song_ids,
        'song_count': song_count,
        'per_user': per_user,
        'global_avg_pct': global_avg_pct,
        'global_avg_unrated': global_avg_unrated,
    }


def _artist_score_stats(artist_id, users, bulk):
    """Calculate average score stats (Global Stats page)."""
    song_ids = bulk.get_song_ids(artist_id)

    if not song_ids:
        return {
            'song_count': 0,
            'per_user': {u.id: None for u in users},
            'global_avg': None,
        }

    # Collect scores per user from pre-aggregated data
    user_sum = defaultdict(float)
    user_count = defaultdict(int)
    for sid in song_ids:
        for uid, (cnt, total) in bulk.song_user_stats.get(sid, {}).items():
            user_sum[uid] += total
            user_count[uid] += cnt

    per_user = {}
    user_avgs = []
    for u in users:
        cnt = user_count.get(u.id, 0)
        if cnt > 0:
            avg = round(user_sum[u.id] / cnt, 2)
            per_user[u.id] = avg
            user_avgs.append(avg)
        else:
            per_user[u.id] = None

    global_avg = round(sum(user_avgs) / len(user_avgs), 2) if user_avgs else None

    return {
        'song_count': len(song_ids),
        'per_user': per_user,
        'global_avg': global_avg,
    }


def _overall_score_stats(users, bulk, artists=None):
    """Average score across ALL displayed songs, per user (Global Stats top row)."""
    from app.services.artist import get_top_level_artists
    top_artists = list(artists) if artists is not None else get_top_level_artists(bulk)

    song_ids = set()
    for a in top_artists:
        song_ids |= bulk.get_song_ids(a.id)

    user_sum = defaultdict(float)
    user_count = defaultdict(int)
    for sid in song_ids:
        for uid, (cnt, total) in bulk.song_user_stats.get(sid, {}).items():
            user_sum[uid] += total
            user_count[uid] += cnt

    per_user = {}
    user_avgs = []
    for u in users:
        cnt = user_count.get(u.id, 0)
        if cnt > 0:
            avg = round(user_sum[u.id] / cnt, 2)
            per_user[u.id] = avg
            user_avgs.append(avg)
        else:
            per_user[u.id] = None

    global_avg = round(sum(user_avgs) / len(user_avgs), 2) if user_avgs else None

    return {
        'song_count': len(song_ids),
        'per_user': per_user,
        'global_avg': global_avg,
    }


# --- Public API (used by routes) ---

def load_bulk_data(include_featured=False, include_remixes=False, include_covers=True, artist_ids=None, genre_ids=None, hide_osts=False, keep_remix_ids=None):
    """Load data needed for stats pages. If artist_ids given, scope to those artists only."""
    with _BUILD_SEMAPHORE:
        return _BulkData(include_featured, include_remixes, include_covers=include_covers, artist_ids=artist_ids, genre_ids=genre_ids, hide_osts=hide_osts, keep_remix_ids=keep_remix_ids)


def get_artist_stats(artist_id, users, bulk):
    """Per-artist completion stats using pre-loaded data."""
    return _artist_completion_stats(artist_id, users, bulk)


def get_artist_score_stats(artist_id, users, bulk):
    """Per-artist score stats using pre-loaded data."""
    return _artist_score_stats(artist_id, users, bulk)


def get_overall_score_stats(users, bulk, artists=None):
    """Each user's average score across all displayed songs."""
    return _overall_score_stats(users, bulk, artists=artists)


def get_summary_stats(users, bulk, artists=None):
    """Top-table summary stats for all users.

    When ``artists`` is given (e.g. after applying the country filter), the
    summary is scoped to those top-level artists' filtered songs so it stays in
    sync with the per-artist table below. Otherwise it covers every artist.
    """
    from app.services.artist import get_top_level_artists
    top_artists = list(artists) if artists is not None else get_top_level_artists(bulk)

    if artists is not None:
        relevant_song_ids = set()
        for artist in top_artists:
            relevant_song_ids |= bulk.get_song_ids(artist.id)
    else:
        relevant_song_ids = bulk.all_song_ids
    total_songs = len(relevant_song_ids)

    # Count ratings per user across all relevant songs
    user_total_rated = defaultdict(int)
    for sid in relevant_song_ids:
        for uid in bulk.song_user_stats.get(sid, {}):
            user_total_rated[uid] += 1

    user_scored_groups_80 = {u.id: 0 for u in users}
    user_scored_groups_any = {u.id: 0 for u in users}

    for artist in top_artists:
        stats = _artist_completion_stats(artist.id, users, bulk)
        for u in users:
            user_stats = stats['per_user'].get(u.id)
            if user_stats and stats['song_count'] > 0:
                if user_stats['rated_count'] > 0:
                    user_scored_groups_any[u.id] += 1
                ratio = user_stats['rated_count'] / stats['song_count']
                if ratio >= SCORED_GROUP_THRESHOLD:
                    user_scored_groups_80[u.id] += 1

    per_user = {}
    rated_counts = []
    for u in users:
        rated = user_total_rated.get(u.id, 0)
        pct = round(rated / total_songs * 100, 1) if total_songs > 0 else 0.0
        per_user[u.id] = {
            'pct_rated': pct,
            'rated_count': rated,
            'rank': 0,
            'scored_group_count_80': user_scored_groups_80[u.id],
            'scored_group_count_any': user_scored_groups_any[u.id],
        }
        if rated > 0:
            rated_counts.append((u.id, rated))

    rated_counts.sort(key=lambda x: x[1], reverse=True)
    for rank, (uid, _) in enumerate(rated_counts, 1):
        per_user[uid]['rank'] = rank

    active_users = [per_user[u.id] for u in users if per_user[u.id]['rated_count'] > 0]
    global_stats = {
        'avg_pct': round(sum(s['pct_rated'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
        'avg_rated_count': round(sum(s['rated_count'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
        'avg_scored_group_count_any': round(sum(s['scored_group_count_any'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
        'avg_scored_group_count_80': round(sum(s['scored_group_count_80'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
    }

    return {
        'total_songs': total_songs,
        'per_user': per_user,
        'global': global_stats,
    }
