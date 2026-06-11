from app.extensions import db


class ProxyChange(db.Model):
    """A rating or note changed on behalf of another user, awaiting their approval."""
    __tablename__ = 'proxy_change'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    type = db.Column(db.Text, nullable=False)
    # No FK: history rows must survive song deletion (display falls back to song_name)
    song_id = db.Column(db.Integer, nullable=False)
    song_name = db.Column(db.Text)
    artist_name = db.Column(db.Text)
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    proposed_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    proposed_at = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default='open')
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    resolved_at = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    old_rating = db.Column(db.Integer)
    new_rating = db.Column(db.Integer)
    old_note = db.Column(db.Text)
    new_note = db.Column(db.Text)

    target_user = db.relationship('User', foreign_keys=[target_user_id])
    proposed_by = db.relationship('User', foreign_keys=[proposed_by_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])

    __table_args__ = (
        db.CheckConstraint("type IN ('rating', 'note')", name='proxy_change_type_check'),
        db.CheckConstraint("status IN ('open', 'approved', 'rejected')", name='proxy_change_status_check'),
        db.Index('ix_proxy_change_status', 'status'),
        db.Index('ix_proxy_change_target', 'target_user_id'),
        db.Index('ix_proxy_change_proposed_by', 'proposed_by_id'),
    )
