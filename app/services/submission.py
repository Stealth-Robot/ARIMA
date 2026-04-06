"""Submission service — create, approve, reject submissions with cascade logic."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.submission import Submission
from app.models.music import Artist, Album, Song, Rating, ArtistSong, AlbumSong, ArtistArtist, album_genres
from app.services.audit import log_change


def _resolve_submission_context(submission_type, entity_id):
    """Resolve entity name, parent artist, and parent album at submission creation time."""
    entity_name = None
    art_id = None
    art_name = None
    alb_id = None

    if submission_type == 'artist':
        entity = db.session.get(Artist, entity_id)
        if entity:
            entity_name = entity.name
            art_id = entity.id
            art_name = entity.name
    elif submission_type == 'album':
        entity = db.session.get(Album, entity_id)
        if entity:
            entity_name = entity.name
            alb_id = entity.id
            if entity.artist_id:
                artist = db.session.get(Artist, entity.artist_id)
                if artist:
                    art_id = artist.id
                    art_name = artist.name
    elif submission_type in ('song', 'rating'):
        entity = db.session.get(Song, entity_id)
        if entity:
            entity_name = entity.name
            # Store first album this song belongs to
            album_link = AlbumSong.query.filter_by(song_id=entity_id).first()
            if album_link:
                alb_id = album_link.album_id
            link = ArtistSong.query.filter_by(song_id=entity_id, artist_is_main=True).first()
            if link:
                artist = db.session.get(Artist, link.artist_id)
                if artist:
                    art_id = artist.id
                    art_name = artist.name

    return entity_name, art_id, art_name, alb_id


def create_submission(submission_type, entity_id, submitted_by_id,
                      target_user_id=None, old_rating=None, new_rating=None,
                      old_note=None, new_note=None):
    """Create a new submission. Call before db.session.commit()."""
    entity_name, art_id, art_name, alb_id = _resolve_submission_context(submission_type, entity_id)
    sub = Submission(
        type=submission_type,
        entity_id=entity_id,
        submitted_by_id=submitted_by_id,
        submitted_at=datetime.now(timezone.utc).isoformat(),
        entity_name=entity_name,
        artist_id=art_id,
        artist_name=art_name,
        album_id=alb_id,
        target_user_id=target_user_id,
        old_rating=old_rating,
        new_rating=new_rating,
        old_note=old_note,
        new_note=new_note,
    )
    db.session.add(sub)
    return sub


def _mark_approved(submission, reviewer):
    """Mark a submission as approved without committing."""
    submission.status = 'approved'
    submission.resolved_by_id = reviewer.id
    submission.resolved_at = datetime.now(timezone.utc).isoformat()


def approve_submission(submission, reviewer):
    """Mark a submission as approved and commit. No changelog entry."""
    _mark_approved(submission, reviewer)
    db.session.commit()


def reject_rating_submission(submission, reviewer, reason):
    """Reject a proxy rating submission — revert to old values."""
    song = db.session.get(Song, submission.entity_id)

    # Revert the rating
    rating = db.session.get(Rating, (submission.entity_id, submission.target_user_id))
    if submission.old_rating is None and submission.old_note is None:
        # No prior rating existed — delete the row
        if rating:
            db.session.delete(rating)
    elif rating:
        rating.rating = submission.old_rating
        rating.note = submission.old_note
    else:
        # Rating row was deleted since submission was created — recreate
        db.session.add(Rating(
            song_id=submission.entity_id,
            user_id=submission.target_user_id,
            rating=submission.old_rating,
            note=submission.old_note,
        ))

    submission.status = 'rejected'
    submission.resolved_by_id = reviewer.id
    submission.resolved_at = datetime.now(timezone.utc).isoformat()
    submission.rejection_reason = reason

    # Changelog
    target_user = submission.target_user
    target_name = target_user.username if target_user else f'user {submission.target_user_id}'
    song_name = song.name if song else f'song {submission.entity_id}'

    rating_changed = submission.old_rating != submission.new_rating

    if rating_changed:
        old_r = submission.old_rating if submission.old_rating is not None else 'none'
        new_r = submission.new_rating if submission.new_rating is not None else 'none'
        desc = f'Rejected proxy rating for {target_name} on "{song_name}" — reverted from {new_r} to {old_r} (reason: {reason})'
    else:
        desc = f'Rejected proxy note for {target_name} on "{song_name}" — reverted note (reason: {reason})'

    log_change(reviewer, desc, song=song, change_type='rating')
    db.session.commit()


# --- Cascade preview / deletion ---

def get_artist_cascade_preview(artist_id):
    """Return cascade data for rejecting an artist submission.

    Uses song-centric logic: only songs exclusive to this artist are deleted.
    Shared songs survive. Albums that become empty are deleted; albums with
    remaining songs from other artists are reassigned.

    Uses two aggregate SQL queries instead of per-song lookups.
    """
    artist = db.session.get(Artist, artist_id)
    if not artist:
        return None

    # One query: all songs linked to this artist with other-artist count and rating count
    song_rows = db.session.execute(db.text("""
        SELECT s.id, s.name, s.submitted_by_id, u.username,
               (SELECT COUNT(*) FROM artist_song WHERE song_id = s.id AND artist_id != :aid) AS other_artists,
               (SELECT COUNT(*) FROM rating WHERE song_id = s.id) AS rating_count
        FROM artist_song AS asl
        JOIN song s ON s.id = asl.song_id
        LEFT JOIN user u ON u.id = s.submitted_by_id
        WHERE asl.artist_id = :aid
    """), {'aid': artist_id}).fetchall()

    songs_to_delete = []
    songs_to_keep = []
    total_ratings = 0

    for row in song_rows:
        info = {
            'id': row[0],
            'name': row[1],
            'rating_count': row[5],
            'submitted_by': row[3] or 'Unknown',
            'submitted_by_id': row[2],
        }
        if row[4] > 0:
            songs_to_keep.append(info)
        else:
            songs_to_delete.append(info)
            total_ratings += row[5]

    # One query: albums owned by this artist with song count and surviving-song count
    delete_song_ids = {s['id'] for s in songs_to_delete}
    album_rows = db.session.execute(db.text("""
        SELECT a.id, a.name, a.submitted_by_id, u.username,
               (SELECT COUNT(*) FROM album_song WHERE album_id = a.id) AS song_count
        FROM album a
        LEFT JOIN user u ON u.id = a.submitted_by_id
        WHERE a.artist_id = :aid
    """), {'aid': artist_id}).fetchall()

    albums_to_delete = []
    albums_to_reassign = []

    for row in album_rows:
        album_id = row[0]
        song_count = row[4]
        # Check how many songs in this album would survive
        album_song_ids = {r.song_id for r in AlbumSong.query.filter_by(album_id=album_id).all()}
        remaining = album_song_ids - delete_song_ids
        info = {
            'id': album_id,
            'name': row[1],
            'song_count': song_count,
            'submitted_by': row[3] or 'Unknown',
            'submitted_by_id': row[2],
        }
        if remaining:
            albums_to_reassign.append(info)
        else:
            albums_to_delete.append(info)

    return {
        'artist': artist,
        'songs_to_delete': songs_to_delete,
        'songs_to_keep': songs_to_keep,
        'albums_to_delete': albums_to_delete,
        'albums_to_reassign': albums_to_reassign,
        'total_songs_deleted': len(songs_to_delete),
        'total_ratings': total_ratings,
    }


def get_album_cascade_preview(album_id):
    """Return cascade data for rejecting an album submission.

    Uses one aggregate SQL query instead of per-song lookups.
    """
    album = db.session.get(Album, album_id)
    if not album:
        return None

    # One query: all songs in this album with other-album count and rating count
    rows = db.session.execute(db.text("""
        SELECT s.id, s.name, s.submitted_by_id, u.username,
               (SELECT COUNT(*) FROM album_song WHERE song_id = s.id AND album_id != :alid) AS other_albums,
               (SELECT COUNT(*) FROM rating WHERE song_id = s.id) AS rating_count
        FROM album_song AS als
        JOIN song s ON s.id = als.song_id
        LEFT JOIN user u ON u.id = s.submitted_by_id
        WHERE als.album_id = :alid
    """), {'alid': album_id}).fetchall()

    song_details = []
    total_ratings = 0
    songs_to_delete = 0

    for row in rows:
        will_delete = row[4] == 0
        rc = row[5]
        total_ratings += rc
        if will_delete:
            songs_to_delete += 1
        song_details.append({
            'id': row[0],
            'name': row[1],
            'will_delete': will_delete,
            'rating_count': rc,
            'submitted_by': row[3] or 'Unknown',
            'submitted_by_id': row[2],
        })

    return {
        'album': album,
        'songs': song_details,
        'total_songs': len(song_details),
        'songs_deleted': songs_to_delete,
        'total_ratings': total_ratings,
    }


def get_song_cascade_preview(song_id):
    """Return cascade data for rejecting a song submission."""
    song = db.session.get(Song, song_id)
    if not song:
        return None

    rating_count = Rating.query.filter_by(song_id=song_id).count()
    album_links = AlbumSong.query.filter_by(song_id=song_id).all()
    albums = []
    for link in album_links:
        album = db.session.get(Album, link.album_id)
        if album:
            albums.append({'id': album.id, 'name': album.name})

    return {
        'song': song,
        'albums': albums,
        'total_ratings': rating_count,
    }


def _close_orphaned_submissions(entity_type, entity_id, reviewer):
    """Close any open submissions referencing a deleted entity."""
    now = datetime.now(timezone.utc).isoformat()
    orphans = Submission.query.filter_by(
        type=entity_type, entity_id=entity_id, status='open'
    ).all()
    for s in orphans:
        s.status = 'rejected'
        s.resolved_by_id = reviewer.id
        s.resolved_at = now
        s.rejection_reason = 'Parent entity was rejected'


def reject_artist_submission(submission, reviewer, reason):
    """Reject an artist submission — song-centric cascade.

    Removes the artist's song links. Songs with no other artists are deleted.
    Albums that become empty are deleted. Albums that still have songs from
    other artists are reassigned to one of those artists.
    """
    artist = db.session.get(Artist, submission.entity_id)
    if not artist:
        submission.status = 'rejected'
        submission.resolved_by_id = reviewer.id
        submission.resolved_at = datetime.now(timezone.utc).isoformat()
        submission.rejection_reason = reason
        db.session.commit()
        return

    artist_name = artist.name
    artist_id = artist.id

    # Collect stats for changelog
    song_ids = {row.song_id for row in ArtistSong.query.filter_by(artist_id=artist_id).all()}
    deleted_songs = 0
    deleted_albums = 0
    deleted_ratings = 0

    # Remove this artist's song links; only delete songs with no other artists
    for song_id in song_ids:
        ArtistSong.query.filter_by(artist_id=artist_id, song_id=song_id).delete()
        other_artists = ArtistSong.query.filter_by(song_id=song_id).count()
        if other_artists > 0:
            continue  # shared song — leave it

        rc = Rating.query.filter_by(song_id=song_id).count()
        deleted_ratings += rc
        Rating.query.filter_by(song_id=song_id).delete()
        album_song_rows = AlbumSong.query.filter_by(song_id=song_id).all()
        AlbumSong.query.filter_by(song_id=song_id).delete()
        db.session.query(Song).filter_by(id=song_id).delete()
        deleted_songs += 1
        _close_orphaned_submissions('song', song_id, reviewer)
        _close_orphaned_submissions('rating', song_id, reviewer)

        # Clean up albums that are now empty
        for row in album_song_rows:
            remaining = AlbumSong.query.filter_by(album_id=row.album_id).count()
            if remaining == 0:
                db.session.execute(album_genres.delete().where(album_genres.c.album_id == row.album_id))
                db.session.query(Album).filter_by(id=row.album_id).delete()
                deleted_albums += 1
                _close_orphaned_submissions('album', row.album_id, reviewer)

    # Reassign albums still owned by this artist to another artist
    for album in Album.query.filter_by(artist_id=artist_id).all():
        # Find another main artist from the album's remaining songs
        new_artist_row = db.session.query(ArtistSong.artist_id).join(
            AlbumSong, ArtistSong.song_id == AlbumSong.song_id
        ).filter(
            AlbumSong.album_id == album.id,
            ArtistSong.artist_is_main == True,
        ).first()
        if new_artist_row:
            album.artist_id = new_artist_row[0]
        else:
            album.artist_id = None

    # Delete artist relationships
    ArtistArtist.query.filter(
        db.or_(ArtistArtist.artist_1 == artist_id, ArtistArtist.artist_2 == artist_id)
    ).delete(synchronize_session=False)

    # Delete the artist
    db.session.delete(artist)

    # Mark this submission as rejected
    submission.status = 'rejected'
    submission.resolved_by_id = reviewer.id
    submission.resolved_at = datetime.now(timezone.utc).isoformat()
    submission.rejection_reason = reason

    log_change(reviewer,
               f'Rejected artist "{artist_name}" — deleted {deleted_albums} albums, {deleted_songs} songs, {deleted_ratings} ratings (reason: {reason})',
               change_type='artist')
    db.session.commit()


def _delete_album_cascade(album_id, reviewer=None):
    """Delete an album and its exclusive songs/ratings. Does NOT commit.

    Returns set of song IDs that were fully deleted (for dedup in caller).

    Note: checks other *albums* not other *artists* to decide song deletion.
    This is intentional — album rejection means "this album shouldn't exist"
    so songs are kept only if they live on another album. Artist rejection
    (reject_artist_submission) uses the inverse: songs kept if another artist
    claims them. Different semantic operations, different cascade rules.
    """
    song_rows = AlbumSong.query.filter_by(album_id=album_id).all()
    deleted_song_ids = set()

    for r in song_rows:
        sid = r.song_id
        AlbumSong.query.filter_by(album_id=album_id, song_id=sid).delete()
        other_albums = AlbumSong.query.filter_by(song_id=sid).count()
        if other_albums > 0:
            continue
        ArtistSong.query.filter_by(song_id=sid).delete()
        Rating.query.filter_by(song_id=sid).delete()
        db.session.query(Song).filter_by(id=sid).delete()
        deleted_song_ids.add(sid)
        if reviewer:
            _close_orphaned_submissions('song', sid, reviewer)
            _close_orphaned_submissions('rating', sid, reviewer)

    db.session.execute(album_genres.delete().where(album_genres.c.album_id == album_id))
    db.session.query(Album).filter_by(id=album_id).delete()
    return deleted_song_ids


def reject_album_submission(submission, reviewer, reason):
    """Reject an album submission — cascade delete the album."""
    album = db.session.get(Album, submission.entity_id)
    if not album:
        submission.status = 'rejected'
        submission.resolved_by_id = reviewer.id
        submission.resolved_at = datetime.now(timezone.utc).isoformat()
        submission.rejection_reason = reason
        db.session.commit()
        return

    album_name = album.name
    artist_name = album.artist.name if album.artist else None
    total_songs = AlbumSong.query.filter_by(album_id=album.id).count()
    song_ids = [r.song_id for r in AlbumSong.query.filter_by(album_id=album.id).all()]

    # Identify which songs will be deleted (exclusive to this album) vs unlinked
    exclusive_song_ids = []
    for sid in song_ids:
        other_albums = AlbumSong.query.filter(
            AlbumSong.song_id == sid, AlbumSong.album_id != album.id
        ).count()
        if other_albums == 0:
            exclusive_song_ids.append(sid)
            _close_orphaned_submissions('song', sid, reviewer)

    rating_count = Rating.query.filter(Rating.song_id.in_(exclusive_song_ids)).count() if exclusive_song_ids else 0

    deleted_song_ids = _delete_album_cascade(album.id, reviewer=reviewer)
    songs_deleted = len(deleted_song_ids)
    songs_unlinked = total_songs - songs_deleted

    submission.status = 'rejected'
    submission.resolved_by_id = reviewer.id
    submission.resolved_at = datetime.now(timezone.utc).isoformat()
    submission.rejection_reason = reason

    parts = []
    if songs_deleted:
        parts.append(f'{songs_deleted} songs deleted')
    if songs_unlinked:
        parts.append(f'{songs_unlinked} songs unlinked')
    if rating_count:
        parts.append(f'{rating_count} ratings')
    context = f' ({artist_name})' if artist_name else ''
    log_change(reviewer,
               f'Rejected album "{album_name}"{context} — {", ".join(parts)} (reason: {reason})',
               change_type='album')
    db.session.commit()


def reject_song_submission(submission, reviewer, reason):
    """Reject a song submission — delete the song and its links."""
    song = db.session.get(Song, submission.entity_id)
    if not song:
        submission.status = 'rejected'
        submission.resolved_by_id = reviewer.id
        submission.resolved_at = datetime.now(timezone.utc).isoformat()
        submission.rejection_reason = reason
        db.session.commit()
        return

    song_name = song.name
    rating_count = Rating.query.filter_by(song_id=song.id).count()

    # Capture album IDs before deleting links
    affected_album_ids = [r.album_id for r in AlbumSong.query.filter_by(song_id=song.id).all()]

    AlbumSong.query.filter_by(song_id=song.id).delete()
    ArtistSong.query.filter_by(song_id=song.id).delete()
    Rating.query.filter_by(song_id=song.id).delete()
    _close_orphaned_submissions('rating', song.id, reviewer)
    db.session.delete(song)

    # Clean up albums that are now empty
    for aid in affected_album_ids:
        remaining = AlbumSong.query.filter_by(album_id=aid).count()
        if remaining == 0:
            db.session.execute(album_genres.delete().where(album_genres.c.album_id == aid))
            db.session.query(Album).filter_by(id=aid).delete()
            _close_orphaned_submissions('album', aid, reviewer)

    submission.status = 'rejected'
    submission.resolved_by_id = reviewer.id
    submission.resolved_at = datetime.now(timezone.utc).isoformat()
    submission.rejection_reason = reason

    log_change(reviewer,
               f'Rejected song "{song_name}" — deleted {rating_count} ratings (reason: {reason})',
               change_type='song')
    db.session.commit()
