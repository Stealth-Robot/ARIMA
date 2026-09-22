from datetime import datetime

from app.extensions import db


def _label(iso):
    """'2026-09-08' -> 'Sep 08'; pass through anything unparseable."""
    try:
        return datetime.strptime(iso, '%Y-%m-%d').strftime('%b %d')
    except (ValueError, TypeError):
        return iso or ''


def _time_24(raw):
    """Any accepted time text to 24-hour 'HH:MM' for a time input; '' if unparseable.
    Legacy free text like '6pm' or '6:30 PM' is accepted so older rows still prefill."""
    value = (raw or '').strip()
    if not value:
        return ''
    for fmt in ('%H:%M', '%I:%M%p', '%I:%M %p', '%I%p', '%I %p'):
        try:
            return datetime.strptime(value.upper(), fmt).strftime('%H:%M')
        except ValueError:
            continue
    return ''


def _time_label(raw):
    """Display form: 12-hour with a suffix. '18:30' -> '6:30pm'.

    The suffix is derived from the 24-hour value rather than assumed, so a morning time
    would read 'am' instead of silently claiming to be an evening one.
    """
    hhmm = _time_24(raw)
    if not hhmm:
        return (raw or '').strip()
    hour, minute = hhmm.split(':')
    suffix = 'pm' if int(hour) >= 12 else 'am'
    return f'{int(hour) % 12 or 12}:{minute}{suffix}'


class SoccerSeason(db.Model):
    """One playing season — the unit the whole grid is scoped to."""
    __tablename__ = 'soccer_season'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    # Legacy span columns. Seasons are now name-only and their span is derived from their
    # days (range_label); these stay NOT NULL because SQLite cannot drop the constraint.
    start_date = db.Column(db.Text, nullable=False, default='')
    end_date = db.Column(db.Text, nullable=False, default='')
    kickoff = db.Column(db.Text, nullable=False, default='6pm')
    created_at = db.Column(db.Text)

    games = db.relationship('SoccerGame', back_populates='season',
                            cascade='all, delete-orphan')
    players = db.relationship('SoccerPlayer', back_populates='season',
                              cascade='all, delete-orphan')

    @property
    def range_label(self):
        """A season is created with only a name, so its span comes from its days."""
        dates = sorted(g.date for g in self.games)
        if not dates:
            return 'no days yet'
        if dates[0] == dates[-1]:
            return _label(dates[0])
        return f'{_label(dates[0])} ~ {_label(dates[-1])}'


class SoccerGame(db.Model):
    """One dated fixture — a column of the grid."""
    __tablename__ = 'soccer_game'
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('soccer_season.id', ondelete='CASCADE'),
                          nullable=False)
    date = db.Column(db.Text, nullable=False)         # 'YYYY-MM-DD'
    kickoff = db.Column(db.Text)                      # NULL => the season's kickoff

    season = db.relationship('SoccerSeason', back_populates='games')

    @property
    def date_label(self):
        return _label(self.date)

    @property
    def kickoff_label(self):
        return _time_label(self.kickoff or (self.season.kickoff if self.season else ''))

    @property
    def kickoff_input(self):
        """This day's own time as 24-hour 'HH:MM' — the only format a time input accepts.
        Blank when the day inherits the season's kickoff."""
        return _time_24(self.kickoff)

    __table_args__ = (
        # Deliberately not unique: a day can hold more than one fixture.
        db.Index('ix_soccer_game_season_date', 'season_id', 'date'),
    )


class SoccerPlayer(db.Model):
    """One squad member — a row of the grid, in a fixed counted category."""
    __tablename__ = 'soccer_player'
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('soccer_season.id', ondelete='CASCADE'),
                          nullable=False)
    name = db.Column(db.Text, nullable=False)
    # 'keeper' | 'guys' | 'girls' — each carries its own hardcoded count threshold
    category = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    season = db.relationship('SoccerSeason', back_populates='players')

    __table_args__ = (
        db.CheckConstraint("category IN ('keeper', 'guys', 'girls')",
                           name='soccer_player_category_check'),
        db.Index('ix_soccer_player_season', 'season_id', 'sort_order'),
    )


class SoccerAvailability(db.Model):
    """One player's answer for one game. No row at all means unset."""
    __tablename__ = 'soccer_availability'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('soccer_game.id', ondelete='CASCADE'),
                        nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('soccer_player.id', ondelete='CASCADE'),
                          nullable=False)
    available = db.Column(db.Integer, nullable=False)  # 1 = available, 0 = unavailable

    __table_args__ = (
        # Also the enforcer of the tri-state: at most one row per cell.
        db.Index('ux_soccer_availability', 'game_id', 'player_id', unique=True),
    )
