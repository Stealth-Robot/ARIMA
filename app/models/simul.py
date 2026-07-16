from app.extensions import db


class SimulStatusType(db.Model):
    """The status legend, as data so labels/colors can be edited in-app."""
    __tablename__ = 'simul_status_type'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Text, nullable=False, unique=True)
    label = db.Column(db.Text, nullable=False)
    color_hex = db.Column(db.Text, nullable=False)
    # 'planning' | 'watch' | 'both' — which buckets the status is offered in
    applies_to = db.Column(db.Text, nullable=False, default='both')
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class SimulShow(db.Model):
    """A title tracked for group simulwatching."""
    __tablename__ = 'simul_show'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    # 'tv' | 'movie' | 'upcoming_seasonal' | 'upcoming_movie' | 'uncategorized'
    category = db.Column(db.Text, nullable=False, default='uncategorized')
    # 'planning' | 'ongoing' | 'paused' | 'completed' | 'dropped'
    bucket = db.Column(db.Text, nullable=False, default='planning')
    year = db.Column(db.Integer)  # NULL for planning
    youtube_url = db.Column(db.Text)
    years_running = db.Column(db.Text)
    notes = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.Text)
    last_updated = db.Column(db.Text)

    statuses = db.relationship('SimulStatus', back_populates='show',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_simul_show_bucket_year', 'bucket', 'year'),
    )


class SimulStatus(db.Model):
    """One participant's status on one show. Participant is either an ARIMA user
    (user_id) or a historical member with no account (member_name)."""
    __tablename__ = 'simul_status'
    id = db.Column(db.Integer, primary_key=True)
    show_id = db.Column(db.Integer, db.ForeignKey('simul_show.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    member_name = db.Column(db.Text)
    status_type_id = db.Column(db.Integer, db.ForeignKey('simul_status_type.id'),
                               nullable=False)
    note = db.Column(db.Text)

    show = db.relationship('SimulShow', back_populates='statuses')
    user = db.relationship('User')
    status_type = db.relationship('SimulStatusType')

    __table_args__ = (
        db.UniqueConstraint('show_id', 'user_id', name='uq_simul_status_user'),
        db.UniqueConstraint('show_id', 'member_name', name='uq_simul_status_member'),
    )
