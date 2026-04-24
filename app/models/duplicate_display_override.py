from app.extensions import db


class DuplicateDisplayOverride(db.Model):
    """Override which album a duplicate song is displayed under on an artist page."""
    __tablename__ = 'duplicate_display_override'
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'), primary_key=True)
    preferred_album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'), nullable=False)
