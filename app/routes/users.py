from datetime import datetime, timezone

from flask import Blueprint, request, render_template, redirect, url_for, Response
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
    ).order_by(User.sort_order.asc().nullslast()).all()

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


@users_bp.route('/admin/users/<int:user_id>/move-up', methods=['POST'])
@login_required
@role_required(ADMIN)
def move_up(user_id):
    """Move a user one position up in sort order."""
    _swap_sort_order(user_id, direction='up')
    r = Response('', 204)
    r.headers['HX-Refresh'] = 'true'
    return r


@users_bp.route('/admin/users/<int:user_id>/move-down', methods=['POST'])
@login_required
@role_required(ADMIN)
def move_down(user_id):
    """Move a user one position down in sort order."""
    _swap_sort_order(user_id, direction='down')
    r = Response('', 204)
    r.headers['HX-Refresh'] = 'true'
    return r


def _swap_sort_order(user_id, direction):
    """Swap sort_order between user and their neighbour."""
    users = User.query.filter(
        User.email.isnot(None)
    ).order_by(User.sort_order.asc().nullslast()).all()

    idx = next((i for i, u in enumerate(users) if u.id == user_id), None)
    if idx is None:
        return

    if direction == 'up' and idx > 0:
        neighbour = users[idx - 1]
    elif direction == 'down' and idx < len(users) - 1:
        neighbour = users[idx + 1]
    else:
        return

    target = users[idx]
    original_target = target.sort_order
    original_neighbour = neighbour.sort_order
    target.sort_order = -1
    db.session.flush()
    neighbour.sort_order = original_target
    db.session.flush()
    target.sort_order = original_neighbour
    db.session.commit()
