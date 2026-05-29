from app.extensions import db


class SongOfDay(db.Model):
    __tablename__ = 'song_of_day'
    date = db.Column(db.Text, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        nullable=False, index=True)

    song = db.relationship('Song')
