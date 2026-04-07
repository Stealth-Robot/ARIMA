from app.extensions import db


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    type = db.Column(db.Text, nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submitted_at = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default='open')
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    resolved_at = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    entity_name = db.Column(db.Text)
    artist_id = db.Column(db.Integer)
    artist_name = db.Column(db.Text)
    album_id = db.Column(db.Integer)

    # Rating-specific fields (NULL for non-rating submissions)
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    old_rating = db.Column(db.Integer)
    new_rating = db.Column(db.Integer)
    old_note = db.Column(db.Text)
    new_note = db.Column(db.Text)

    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    target_user = db.relationship('User', foreign_keys=[target_user_id])

    __table_args__ = (
        db.CheckConstraint("type IN ('artist', 'album', 'song', 'rating', 'note')", name='submission_type_check'),
        db.CheckConstraint("status IN ('open', 'approved', 'rejected')", name='submission_status_check'),
        db.Index('ix_submission_status', 'status'),
        db.Index('ix_submission_type', 'type'),
        db.Index('ix_submission_submitted_by', 'submitted_by_id'),
        db.Index('ix_submission_entity', 'type', 'entity_id'),
    )
