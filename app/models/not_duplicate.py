from app.extensions import db


class NotDuplicate(db.Model):
    """Pair of songs explicitly marked as not duplicates."""
    __tablename__ = 'not_duplicate'
    song_id_1 = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)
    song_id_2 = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'), primary_key=True)

    __table_args__ = (
        db.CheckConstraint('song_id_1 < song_id_2', name='not_dup_order'),
    )
