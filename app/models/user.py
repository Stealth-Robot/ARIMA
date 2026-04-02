from flask_login import UserMixin

from app.extensions import db


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.Text, nullable=False, unique=True)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, nullable=False, unique=True)
    email = db.Column(db.Text, unique=True)
    password = db.Column(db.Text)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    created_at = db.Column(db.Text, nullable=False)
    last_seen = db.Column(db.Text)
    sort_order = db.Column(db.Integer, unique=True)
    profile_image = db.Column(db.Text)
    home_page_image = db.Column(db.Text)
    last_updated = db.Column(db.Text)

    role = db.relationship('Role')
    settings = db.relationship('UserSettings', uselist=False, back_populates='user',
                               cascade='all, delete-orphan')
    ratings = db.relationship('Rating', back_populates='user',
                              cascade='all, delete-orphan')

    @property
    def is_admin(self):
        return self.role_id == 0

    @property
    def is_editor_or_admin(self):
        return self.role_id in (0, 1)

    @property
    def can_rate(self):
        return self.role_id in (0, 1, 2)

    @property
    def is_system_or_guest(self):
        return self.email is None


class UserSettings(db.Model):
    __tablename__ = 'user_settings'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    country = db.Column(db.Integer, db.ForeignKey('country.id'))
    genre = db.Column(db.Integer, db.ForeignKey('genre.id'))
    include_featured = db.Column(db.Boolean, nullable=False, default=False)
    include_remixes = db.Column(db.Boolean, nullable=False, default=False)
    theme = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=False, default=0)
    hide_duplicate_songs = db.Column(db.Boolean, nullable=False, default=False)
    album_sort_order = db.Column(db.String(4), nullable=False, default='desc')

    user = db.relationship('User', back_populates='settings')
