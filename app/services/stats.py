"""Stats calculation service — SQL-aggregated, viewer-relative."""

import math
from collections import defaultdict

from app.extensions import db
from app.models.music import Rating, ArtistSong, Song, ArtistArtist, AlbumSong, album_genres
from app.models.user import User

SCORED_GROUP_THRESHOLD = 0.80
SUBUNIT = 0


def get_display_users():
    """Users shown in stats columns (exclude system/guest, sorted by sort_order)."""
    return User.query.filter(User.sort_order.isnot(None)).order_by(User.sort_order).all()


class _BulkData:
    """Pre-loaded stats via SQL aggregation (~5 queries, but returns aggregated rows)."""

    def __init__(self, include_featured, include_remixes, artist_ids=None, genre_id=None):
        scoped = artist_ids is not None

        # 0. If genre filter is active, find song IDs that belong to albums with this genre
        if genre_id is not None:
            self._genre_song_ids = {row[0] for row in db.session.query(AlbumSong.song_id).join(
                album_genres, AlbumSong.album_id == album_genres.c.album_id
            ).filter(album_genres.c.genre_id == genre_id).all()}
        else:
            self._genre_song_ids = None

        # 1. Artist-song mappings (still needed for song_id resolution)
        if scoped:
            all_as = ArtistSong.query.filter(ArtistSong.artist_id.in_(artist_ids)).all()
        else:
            all_as = ArtistSong.query.all()
        self.artist_songs = defaultdict(set)
        self.artist_main_songs = defaultdict(set)
        for row in all_as:
            self.artist_songs[row.artist_id].add(row.song_id)
            if row.artist_is_main:
                self.artist_main_songs[row.artist_id].add(row.song_id)

        # 2. Subunit relationships
        if scoped:
            all_rels = ArtistArtist.query.filter(
                ArtistArtist.relationship == SUBUNIT,
                db.or_(ArtistArtist.artist_1.in_(artist_ids), ArtistArtist.artist_2.in_(artist_ids))
            ).all()
        else:
            all_rels = ArtistArtist.query.filter_by(relationship=SUBUNIT).all()
        self.subunit_ids = set()
        self.children = defaultdict(list)
        for rel in all_rels:
            self.subunit_ids.add(rel.artist_2)
            self.children[rel.artist_1].append(rel.artist_2)

        # 3. Remix song IDs
        if not include_remixes:
            all_song_ids = set()
            for song_ids in self.artist_songs.values():
                all_song_ids |= song_ids
            if scoped and all_song_ids:
                self.remix_ids = {s.id for s in Song.query.filter(Song.is_remix == True, Song.id.in_(all_song_ids)).all()}
            elif scoped:
                self.remix_ids = set()
            else:
                self.remix_ids = {s.id for s in Song.query.filter(Song.is_remix == True).all()}
        else:
            self.remix_ids = set()

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

        # Build lookup: song_id → {user_id: {'count': n, 'sum': s}}
        self.song_user_stats = defaultdict(dict)
        self.song_rated_by = defaultdict(set)
        for song_id, user_id, cnt, total in agg_rows:
            self.song_user_stats[song_id][user_id] = {'count': cnt, 'sum': total}
            self.song_rated_by[song_id].add(user_id)

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
            if not include_featured and self.all_main_song_ids is not None:
                self.all_song_ids &= self.all_main_song_ids
        else:
            all_songs_query = Song.query
            if not include_remixes:
                all_songs_query = all_songs_query.filter(Song.is_remix == False)
            self.all_song_ids = {s.id for s in all_songs_query.all()}
            if not include_featured and self.all_main_song_ids is not None:
                self.all_song_ids &= self.all_main_song_ids
        if self._genre_song_ids is not None:
            self.all_song_ids &= self._genre_song_ids

        self.include_featured = include_featured
        self.include_remixes = include_remixes

    def get_song_ids(self, artist_id):
        """Get filtered song IDs for an artist (including subunit songs)."""
        song_ids = set(self.artist_songs.get(artist_id, set()))
        for child_id in self.children.get(artist_id, []):
            song_ids |= self.artist_songs.get(child_id, set())

        if not self.include_remixes:
            song_ids -= self.remix_ids

        if not self.include_featured:
            main_ids = set(self.artist_main_songs.get(artist_id, set()))
            for child_id in self.children.get(artist_id, []):
                main_ids |= self.artist_main_songs.get(child_id, set())
            song_ids &= main_ids

        if self._genre_song_ids is not None:
            song_ids &= self._genre_song_ids

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
        for uid in bulk.song_rated_by.get(sid, set()):
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
        for uid, stats in bulk.song_user_stats.get(sid, {}).items():
            user_sum[uid] += stats['sum']
            user_count[uid] += stats['count']

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

def load_bulk_data(include_featured=False, include_remixes=False, artist_ids=None, genre_id=None):
    """Load data needed for stats pages. If artist_ids given, scope to those artists only."""
    return _BulkData(include_featured, include_remixes, artist_ids=artist_ids, genre_id=genre_id)


def get_artist_stats(artist_id, users, bulk):
    """Per-artist completion stats using pre-loaded data."""
    return _artist_completion_stats(artist_id, users, bulk)


def get_artist_score_stats(artist_id, users, bulk):
    """Per-artist score stats using pre-loaded data."""
    return _artist_score_stats(artist_id, users, bulk)


def get_summary_stats(users, bulk):
    """Top-table summary stats for all users."""
    total_songs = len(bulk.all_song_ids)

    # Count ratings per user across all relevant songs
    user_total_rated = defaultdict(int)
    for sid in bulk.all_song_ids:
        for uid in bulk.song_rated_by.get(sid, set()):
            user_total_rated[uid] += 1

    # Scored group counts per user
    from app.services.artist import get_top_level_artists
    top_artists = get_top_level_artists(bulk)

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
