"""Proxy change service — create, approve, reject rating/note changes made on behalf of other users."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.proxy_change import ProxyChange
from app.models.music import Artist, Song, Rating, ArtistSong
from app.services.audit import log_change


def create_proxy_change(change_type, song_id, proposed_by_id, target_user_id,
                        old_rating=None, new_rating=None,
                        old_note=None, new_note=None):
    """Create a new proxy change. Call before db.session.commit()."""
    song_name = None
    artist_name = None
    song = db.session.get(Song, song_id)
    if song:
        song_name = song.name
        link = ArtistSong.query.filter_by(song_id=song_id, artist_is_main=True).first()
        if link:
            artist = db.session.get(Artist, link.artist_id)
            if artist:
                artist_name = artist.name

    change = ProxyChange(
        type=change_type,
        song_id=song_id,
        song_name=song_name,
        artist_name=artist_name,
        target_user_id=target_user_id,
        proposed_by_id=proposed_by_id,
        proposed_at=datetime.now(timezone.utc).isoformat(),
        old_rating=old_rating,
        new_rating=new_rating,
        old_note=old_note,
        new_note=new_note,
    )
    db.session.add(change)
    return change


def mark_approved(change, reviewer):
    """Mark a proxy change as approved without committing."""
    change.status = 'approved'
    change.resolved_by_id = reviewer.id
    change.resolved_at = datetime.now(timezone.utc).isoformat()


def reject_proxy_change(change, reviewer, reason):
    """Reject a proxy rating or note change — revert to old values."""
    song = db.session.get(Song, change.song_id)

    # Revert only the field this change owns — a combined score+note
    # change produces two rows that must resolve independently
    rating = db.session.get(Rating, (change.song_id, change.target_user_id))
    if change.type == 'note':
        if rating:
            rating.note = change.old_note
            if rating.rating is None and not rating.note:
                db.session.delete(rating)
    elif rating:
        rating.rating = change.old_rating
        if rating.rating is None and not rating.note:
            db.session.delete(rating)
    elif change.old_rating is not None:
        # Rating row was deleted since the change was created — recreate
        db.session.add(Rating(
            song_id=change.song_id,
            user_id=change.target_user_id,
            rating=change.old_rating,
            note=change.old_note,
        ))

    change.status = 'rejected'
    change.resolved_by_id = reviewer.id
    change.resolved_at = datetime.now(timezone.utc).isoformat()
    change.rejection_reason = reason

    # Changelog
    target_user = change.target_user
    target_name = target_user.username if target_user else f'user {change.target_user_id}'
    song_name = song.name if song else (change.song_name or f'song {change.song_id}')

    rating_changed = change.old_rating != change.new_rating

    if rating_changed:
        old_r = change.old_rating if change.old_rating is not None else 'none'
        new_r = change.new_rating if change.new_rating is not None else 'none'
        desc = f'Rejected proxy rating for {target_name} on "{song_name}" — reverted from {new_r} to {old_r} (reason: {reason})'
    else:
        desc = f'Rejected proxy note for {target_name} on "{song_name}" — reverted note (reason: {reason})'

    log_change(reviewer, desc, song=song, change_type='rating')
    db.session.commit()


def close_orphaned_proxy_changes(song_id, reviewer):
    """Close any open proxy changes referencing a deleted song."""
    now = datetime.now(timezone.utc).isoformat()
    orphans = ProxyChange.query.filter(
        ProxyChange.song_id == song_id,
        ProxyChange.status == 'open',
    ).all()
    for c in orphans:
        c.status = 'rejected'
        c.resolved_by_id = reviewer.id
        c.resolved_at = now
        c.rejection_reason = 'Song was deleted'
