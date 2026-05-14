from app.extensions import db


class NotCollab(db.Model):
    """Songs explicitly dismissed from the collab candidates view."""
    __tablename__ = 'not_collab'
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)
