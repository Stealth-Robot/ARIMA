from datetime import datetime, timezone

from flask import Blueprint, request, redirect, url_for, session, render_template
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, bcrypt
from app.models.user import User, UserSettings
from app.models.theme import Theme

auth_bp = Blueprint('auth', __name__)


def _classic_theme():
    """Return Classic theme colour values as a dict for the login page."""
    classic = db.session.get(Theme, 0)
    if not classic:
        return {}
    return {c.name: getattr(classic, c.name) for c in Theme.__table__.columns
            if c.name not in ('id', 'name', 'user_id')}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home.home'))

    theme = _classic_theme()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter(
            db.or_(User.username == username, User.email == username)
        ).first()

        if user and user.password and _check_password(user.password, password):
            _do_login(user)
            return redirect(url_for('home.home'))

        # Generic error — no indication of whether username or password was wrong
        return render_template('auth/login.html', theme=theme, error='Invalid username or password.')

    return render_template('auth/login.html', theme=theme)


@auth_bp.route('/guest', methods=['POST'])
def guest_login():
    guest = db.session.get(User, 1)
    if guest:
        _do_login(guest)
    return redirect(url_for('home.home'))


@auth_bp.route('/lookup-invite', methods=['POST'])
def lookup_invite():
    """Return the username for an invited (password-less) user by email."""
    email = request.form.get('email', '').strip().lower()
    if not email:
        return {'username': None}
    user = User.query.filter_by(email=email).first()
    if user and user.password is None:
        return {'username': user.username}
    return {'username': None}


@auth_bp.route('/create-account', methods=['POST'])
def create_account():
    email = request.form.get('email', '').strip().lower()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm = request.form.get('confirm_password', '')
    theme = _classic_theme()

    # Validate passwords match
    if password != confirm:
        return render_template('auth/login.html', theme=theme, mode='create',
                               create_email=email, create_username=username,
                               error='Passwords do not match.')

    if not password:
        return render_template('auth/login.html', theme=theme, mode='create',
                               create_email=email, create_username=username,
                               error='Password is required.')

    # Look up invited user by email
    user = User.query.filter_by(email=email).first()

    if user is None:
        return render_template('auth/login.html', theme=theme, mode='create',
                               create_email=email,
                               error='User Not Invited')

    if user.password is not None:
        return render_template('auth/login.html', theme=theme, mode='create',
                               create_email=email,
                               error='User Account Already Exists')

    # Check username uniqueness (if changed from the pre-populated value)
    if username != user.username:
        existing = User.query.filter_by(username=username).first()
        if existing:
            return render_template('auth/login.html', theme=theme, mode='create',
                                   create_email=email, create_username=username,
                                   error='Username already taken.')

    # All valid — create account in single transaction
    user.username = username
    user.password = _hash_password(password)
    user.created_at = datetime.now(timezone.utc).isoformat()

    # Create UserSettings and Theme if they don't already exist (reinvited users keep theirs)
    if not user.settings:
        db.session.add(UserSettings(user_id=user.id))
    if not Theme.query.filter_by(user_id=user.id).first():
        db.session.add(Theme(user_id=user.id))

    db.session.commit()

    _do_login(user)
    return redirect(url_for('home.home'))


@auth_bp.route('/logout')
@login_required
def logout():
    # Clear custom session keys before logout (filters, theme)
    for key in ['country', 'genre', 'theme']:
        session.pop(key, None)
    logout_user()
    return redirect(url_for('auth.login'))


def _do_login(user):
    """Log in a user and make the session permanent (30-day expiry)."""
    login_user(user, remember=True)
    session.permanent = True
    if not user.is_system_or_guest:
        user.last_seen = datetime.now(timezone.utc).isoformat()
        db.session.commit()


def _hash_password(raw_password):
    """Hash a password with pepper + bcrypt."""
    from flask import current_app
    pepper = current_app.config['PEPPER']
    return bcrypt.generate_password_hash(pepper + raw_password).decode('utf-8')


def _check_password(stored_hash, raw_password):
    """Verify a password against pepper + bcrypt hash."""
    from flask import current_app
    pepper = current_app.config['PEPPER']
    return bcrypt.check_password_hash(stored_hash, pepper + raw_password)
