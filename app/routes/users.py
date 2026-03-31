from datetime import datetime, timezone

from flask import Blueprint, request, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User, Role
from app.services.user import delete_user
from app.decorators import role_required, ADMIN

users_bp = Blueprint('users', __name__)

# Assignable roles — never include System (4)
ASSIGNABLE_ROLES = [0, 1, 2, 3]


@users_bp.route('/admin/users')
@login_required
@role_required(ADMIN)
def user_list():
    """Admin user management page."""
    users = User.query.filter(
        User.email.isnot(None)  # exclude System and Guest
    ).order_by(User.created_at).all()

    roles = Role.query.filter(Role.id.in_(ASSIGNABLE_ROLES)).order_by(Role.id).all()

    return render_template('users.html', users=users, roles=roles)


@users_bp.route('/admin/users/invite', methods=['POST'])
@login_required
@role_required(ADMIN)
def invite_user():
    """Create an invited user (no password yet)."""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    role_id = request.form.get('role_id', type=int, default=2)

    if not username or not email:
        return 'Username and email are required', 400

    if role_id not in ASSIGNABLE_ROLES:
        return 'Invalid role', 400

    # Check uniqueness
    if User.query.filter_by(username=username).first():
        return 'Username already taken', 400
    if User.query.filter_by(email=email).first():
        return 'Email already in use', 400

    # Determine next sort_order
    max_sort = db.session.query(db.func.max(User.sort_order)).scalar() or 0
    next_sort = max_sort + 1

    user = User(
        username=username,
        email=email,
        password=None,  # set during account creation
        role_id=role_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        sort_order=next_sort,
    )
    db.session.add(user)
    db.session.commit()

    # Email sending deferred (architecture.md §12) — invite row created
    return redirect(url_for('users.user_list'))


@users_bp.route('/admin/users/<int:user_id>/role', methods=['POST'])
@login_required
@role_required(ADMIN)
def change_role(user_id):
    """Change a user's role."""
    user = db.session.get(User, user_id)
    if not user or user.is_system_or_guest:
        return 'Cannot modify this account', 400

    role_id = request.form.get('role_id', type=int)
    if role_id not in ASSIGNABLE_ROLES:
        return 'Invalid role', 400

    user.role_id = role_id
    db.session.commit()

    return redirect(url_for('users.user_list'))


@users_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required(ADMIN)
def delete(user_id):
    """Delete a user."""
    user = db.session.get(User, user_id)
    if not user or user.is_system_or_guest:
        return 'Cannot delete this account', 400

    # Don't let admin delete themselves
    if user.id == current_user.id:
        return 'Cannot delete your own account', 400

    delete_user(user)
    return redirect(url_for('users.user_list'))
