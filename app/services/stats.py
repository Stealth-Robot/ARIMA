"""Stats calculation service — all computed live, viewer-relative."""

from app.extensions import db
from app.models.music import Rating, ArtistSong, Song
from app.models.user import User
from app.services.artist import get_songs_for_artist, get_top_level_artists, get_children

SCORED_GROUP_THRESHOLD = 0.80


def get_display_users():
    """Users shown in stats columns (exclude system/guest, sorted by sort_order)."""
    return User.query.filter(User.email.isnot(None)).order_by(User.sort_order).all()


def get_user_song_set(user, include_featured=False, include_remixes=False):
    """Get the set of all song IDs relevant to a user's settings."""
    query = Song.query
    if not include_remixes:
        query = query.filter(Song.is_remix == False)
    # Featured filtering: if not including featured, only count main artist songs
    # This is applied per-artist in the stats calculation, not globally
    return {s.id for s in query.all()}


def get_artist_stats(artist_id, users, include_featured=False, include_remixes=False):
    """Calculate per-artist stats for the Artist Stats page.

    Returns dict with:
        - song_ids: set of song IDs for this artist (with subunit songs)
        - song_count: total songs
        - per_user: {user_id: {rated_count, unrated_count, pct_rated}}
        - global_avg_pct: average % rated across users who rated at least one
    """
    song_ids = get_songs_for_artist(artist_id, include_subunit_songs=True)

    # Apply remix filter
    if not include_remixes:
        remix_ids = {s.id for s in Song.query.filter(Song.id.in_(song_ids), Song.is_remix == True).all()}
        song_ids -= remix_ids

    # Apply featured filter
    if not include_featured:
        # Only keep songs where artist_is_main=True for this artist or its subunits
        main_ids = {row.song_id for row in ArtistSong.query.filter(
            ArtistSong.artist_id == artist_id, ArtistSong.artist_is_main == True
        ).all()}
        subunits, _ = get_children(artist_id)
        for sub in subunits:
            sub_main = {row.song_id for row in ArtistSong.query.filter(
                ArtistSong.artist_id == sub.id, ArtistSong.artist_is_main == True
            ).all()}
            main_ids |= sub_main
        song_ids &= main_ids

    song_count = len(song_ids)
    if song_count == 0:
        return {
            'song_ids': set(),
            'song_count': 0,
            'per_user': {u.id: {'rated_count': 0, 'unrated_count': 0, 'pct_rated': 0.0} for u in users},
            'global_avg_pct': 0.0,
        }

    # Get ratings for these songs
    ratings = Rating.query.filter(Rating.song_id.in_(song_ids)).all()
    user_rated = {}  # {user_id: count of rated songs}
    for r in ratings:
        user_rated[r.user_id] = user_rated.get(r.user_id, 0) + 1

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

    return {
        'song_ids': song_ids,
        'song_count': song_count,
        'per_user': per_user,
        'global_avg_pct': global_avg_pct,
    }


def get_artist_score_stats(artist_id, users, include_featured=False, include_remixes=False):
    """Calculate average score stats for the Global Stats page.

    Returns dict with:
        - song_count: total songs
        - per_user: {user_id: avg_score} (None if user has no ratings)
        - global_avg: average score across users who rated at least one song
    """
    song_ids = get_songs_for_artist(artist_id, include_subunit_songs=True)

    if not include_remixes:
        remix_ids = {s.id for s in Song.query.filter(Song.id.in_(song_ids), Song.is_remix == True).all()}
        song_ids -= remix_ids

    if not include_featured:
        main_ids = {row.song_id for row in ArtistSong.query.filter(
            ArtistSong.artist_id == artist_id, ArtistSong.artist_is_main == True
        ).all()}
        subunits, _ = get_children(artist_id)
        for sub in subunits:
            sub_main = {row.song_id for row in ArtistSong.query.filter(
                ArtistSong.artist_id == sub.id, ArtistSong.artist_is_main == True
            ).all()}
            main_ids |= sub_main
        song_ids &= main_ids

    if not song_ids:
        return {
            'song_count': 0,
            'per_user': {u.id: None for u in users},
            'global_avg': None,
        }

    ratings = Rating.query.filter(Rating.song_id.in_(song_ids)).all()
    user_scores = {}  # {user_id: [scores]}
    for r in ratings:
        if r.user_id not in user_scores:
            user_scores[r.user_id] = []
        user_scores[r.user_id].append(r.rating)

    per_user = {}
    user_avgs = []
    for u in users:
        scores = user_scores.get(u.id, [])
        if scores:
            avg = round(sum(scores) / len(scores), 2)
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


def get_summary_stats(users, include_featured=False, include_remixes=False):
    """Calculate top-table summary stats for all users.

    Returns dict with:
        - total_songs: total songs in database
        - per_user: {user_id: {pct_rated, rated_count, rank, scored_group_count}}
        - global: {avg_pct, avg_rated_count, avg_scored_group_count}
    """
    # Total songs (respecting filters)
    query = Song.query
    if not include_remixes:
        query = query.filter(Song.is_remix == False)
    all_songs = {s.id for s in query.all()}
    total_songs = len(all_songs)

    # All ratings
    all_ratings = Rating.query.filter(Rating.song_id.in_(all_songs)).all() if all_songs else []
    user_total_rated = {}
    for r in all_ratings:
        user_total_rated[r.user_id] = user_total_rated.get(r.user_id, 0) + 1

    # Scored group count per user
    top_artists = get_top_level_artists()
    user_scored_groups = {u.id: 0 for u in users}

    for artist in top_artists:
        stats = get_artist_stats(artist.id, users, include_featured, include_remixes)
        for u in users:
            user_stats = stats['per_user'].get(u.id)
            if user_stats and stats['song_count'] > 0:
                ratio = user_stats['rated_count'] / stats['song_count']
                if ratio >= SCORED_GROUP_THRESHOLD:
                    user_scored_groups[u.id] += 1

    # Per-user summary
    per_user = {}
    rated_counts = []
    for u in users:
        rated = user_total_rated.get(u.id, 0)
        pct = round(rated / total_songs * 100, 1) if total_songs > 0 else 0.0
        per_user[u.id] = {
            'pct_rated': pct,
            'rated_count': rated,
            'rank': 0,  # filled below
            'scored_group_count': user_scored_groups[u.id],
        }
        if rated > 0:
            rated_counts.append((u.id, rated))

    # Rank by rated count (descending)
    rated_counts.sort(key=lambda x: x[1], reverse=True)
    for rank, (uid, _) in enumerate(rated_counts, 1):
        per_user[uid]['rank'] = rank

    # Global averages (exclude users with zero rated)
    active_users = [per_user[u.id] for u in users if per_user[u.id]['rated_count'] > 0]
    global_stats = {
        'avg_pct': round(sum(s['pct_rated'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
        'avg_rated_count': round(sum(s['rated_count'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
        'avg_scored_group_count': round(sum(s['scored_group_count'] for s in active_users) / len(active_users), 1) if active_users else 0.0,
    }

    return {
        'total_songs': total_songs,
        'per_user': per_user,
        'global': global_stats,
    }
