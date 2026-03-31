"""Submission service — atomic content creation."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.music import Artist, Album, Song, ArtistSong, AlbumSong, album_genres
from app.models.submission import Submission


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
        approved_by_id=0 if is_auto_approved else None,
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
            db.session.add(ArtistSong(
                artist_id=artist_id,
                song_id=song.id,
                artist_is_main=song_data.get('artist_is_main', True),
            ))

    db.session.commit()
    return submission
