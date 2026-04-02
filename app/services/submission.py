"""Submission service — atomic content creation, approval, rejection."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.music import Artist, Album, Song, Rating, ArtistSong, AlbumSong, album_genres
from app.models.submission import Submission
from app.models.changelog import Changelog


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_submission(user, artist_data, albums_data):
    """Create a full submission in one atomic transaction.

    Args:
        user: The submitting User object.
        artist_data: dict with keys: id (existing) or name, gender_id, country_id (new).
        albums_data: list of dicts, each with:
            - name, release_date, album_type_id
            - genre_ids: list of genre IDs
            - songs: list of dicts with name, is_promoted, is_remix, artist_is_main

    Returns the created Submission.
    """
    timestamp = _now()
    is_auto_approved = user.is_editor_or_admin

    submission = Submission(
        submitted_by_id=user.id,
        submitted_at=timestamp,
        status='approved' if is_auto_approved else 'pending',
        approved_by_id=0 if is_auto_approved else None,  # 0 = System: intentional, denotes auto-approval not manual review
        approved_at=timestamp if is_auto_approved else None,
    )
    db.session.add(submission)
    db.session.flush()

    # Artist: use existing or create new
    if artist_data.get('id'):
        artist_id = artist_data['id']
    else:
        artist = Artist(
            name=artist_data['name'],
            gender_id=artist_data['gender_id'],
            country_id=artist_data['country_id'],
            slug=artist_data.get('slug'),
            submitted_by_id=user.id,
            submission_id=submission.id,
        )
        db.session.add(artist)
        db.session.flush()
        artist_id = artist.id

    # Albums and songs
    for album_data in albums_data:
        album = Album(
            name=album_data['name'],
            release_date=album_data['release_date'],
            album_type_id=album_data['album_type_id'],
            submitted_by_id=user.id,
            submission_id=submission.id,
        )
        db.session.add(album)
        db.session.flush()

        # Album genres
        for genre_id in album_data.get('genre_ids', []):
            db.session.execute(album_genres.insert().values(
                album_id=album.id, genre_id=genre_id
            ))

        # Songs — MUST create AlbumSong in same transaction (orphan prevention)
        for track_num, song_data in enumerate(album_data.get('songs', []), 1):
            song = Song(
                name=song_data['name'],
                submitted_by_id=user.id,
                submission_id=submission.id,
                is_promoted=song_data.get('is_promoted', False),
                is_remix=song_data.get('is_remix', False),
            )
            db.session.add(song)
            db.session.flush()

            db.session.add(AlbumSong(
                album_id=album.id,
                song_id=song.id,
                track_number=track_num,
            ))

            # Artist-song links: support multiple artists per song
            song_artists = song_data.get('artists')
            if song_artists:
                seen_artist_ids = set()
                for sa in song_artists:
                    sa_artist_id = sa.get('artist_id')
                    if sa_artist_id is None:
                        sa_artist_id = artist_id
                    if sa_artist_id in seen_artist_ids:
                        continue
                    seen_artist_ids.add(sa_artist_id)
                    db.session.add(ArtistSong(
                        artist_id=sa_artist_id,
                        song_id=song.id,
                        artist_is_main=sa.get('is_main', True),
                    ))
            else:
                # Backwards compat: single artist_is_main flag
                db.session.add(ArtistSong(
                    artist_id=artist_id,
                    song_id=song.id,
                    artist_is_main=song_data.get('artist_is_main', True),
                ))

    db.session.commit()
    return submission


def approve_submission(submission_id, approver, rejected_song_ids=None):
    """Approve a submission, optionally rejecting individual songs.

    Args:
        submission_id: The Submission ID to approve.
        approver: The approving User object.
        rejected_song_ids: Optional set of song IDs to reject (delete).
    """
    timestamp = _now()
    sub = db.session.get(Submission, submission_id)
    if not sub or sub.status != 'pending':
        return None

    # Delete rejected songs + their ratings + changelog entries
    if rejected_song_ids:
        for song_id in rejected_song_ids:
            song = db.session.get(Song, song_id)
            if song and song.submission_id == submission_id:
                # Changelog entry for rejection
                db.session.add(Changelog(
                    date=timestamp,
                    user_id=approver.id,
                    approved_by_id=approver.id,
                    submission_id=submission_id,
                    song_id=song_id,
                    description=f"Song '{song.name}' rejected from submission #{submission_id}",
                ))
                # Delete ratings for this song
                Rating.query.filter_by(song_id=song_id).delete()
                # Delete pivot rows
                ArtistSong.query.filter_by(song_id=song_id).delete()
                AlbumSong.query.filter_by(song_id=song_id).delete()
                # Delete the song
                db.session.delete(song)

    sub.status = 'approved'
    sub.approved_by_id = approver.id
    sub.approved_at = timestamp

    db.session.commit()
    return sub


def reject_submission(submission_id, rejector, reason):
    """Fully reject a submission — delete all created entities.

    The Submission row itself is NEVER deleted (permanent audit record).
    Changelog entries survive via ON DELETE SET NULL.
    """
    timestamp = _now()
    sub = db.session.get(Submission, submission_id)
    if not sub or sub.status != 'pending':
        return None

    # Find all entities created by this submission
    artists = Artist.query.filter_by(submission_id=submission_id).all()
    albums = Album.query.filter_by(submission_id=submission_id).all()
    songs = Song.query.filter_by(submission_id=submission_id).all()

    # Delete songs (cascades to ratings via ON DELETE CASCADE, pivots too)
    for song in songs:
        Rating.query.filter_by(song_id=song.id).delete()
        ArtistSong.query.filter_by(song_id=song.id).delete()
        AlbumSong.query.filter_by(song_id=song.id).delete()
        db.session.delete(song)

    # Delete albums (cascade to album_genres, album_song already cleaned)
    for album in albums:
        db.session.execute(album_genres.delete().where(album_genres.c.album_id == album.id))
        db.session.delete(album)

    # Delete artists created by this submission
    for artist in artists:
        db.session.delete(artist)

    # Create rejection changelog entry
    db.session.add(Changelog(
        date=timestamp,
        user_id=rejector.id,
        submission_id=submission_id,
        description=f"Submission #{submission_id} rejected: {reason}",
    ))

    # Update submission (never delete)
    sub.status = 'rejected'
    sub.rejected_by_id = rejector.id
    sub.rejected_at = timestamp
    sub.rejected_reason = reason

    db.session.commit()
    return sub
