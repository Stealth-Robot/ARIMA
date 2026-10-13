from app.extensions import db


class NotRemix(db.Model):
    """Songs explicitly dismissed from the unmarked remixes view."""
    __tablename__ = 'not_remix'
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)
