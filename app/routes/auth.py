from datetime import datetime, timezone

from flask import Blueprint, request, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, bcrypt
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home.home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.password and _check_password(user.password, password):
            _do_login(user)
            return redirect(url_for('home.home'))

        # Generic error — no indication of whether username or password was wrong
        return redirect(url_for('auth.login'))

    # GET — render login page (placeholder until #4)
    return 'Login page placeholder', 200


@auth_bp.route('/guest', methods=['POST'])
def guest_login():
    guest = db.session.get(User, 1)
    if guest:
        _do_login(guest)
    return redirect(url_for('home.home'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
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
