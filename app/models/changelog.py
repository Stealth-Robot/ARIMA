from app.extensions import db


class Changelog(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id', ondelete='SET NULL'))
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='SET NULL'))
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='SET NULL'))
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='SET NULL'))
    description = db.Column(db.Text, nullable=False)
    justification = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    submission = db.relationship('Submission')
    artist = db.relationship('Artist')
    album = db.relationship('Album')
    song = db.relationship('Song')
