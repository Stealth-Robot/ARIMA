from app.extensions import db


class NotVariant(db.Model):
    """Songs explicitly dismissed from the variant songs view."""
    __tablename__ = 'not_variant'
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)
