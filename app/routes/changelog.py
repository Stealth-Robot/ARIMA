from flask import Blueprint, request, render_template, abort, session
from flask_login import login_required
from sqlalchemy import distinct

from app.extensions import db
from app.models.changelog import Changelog
from app.models.lookups import ChangelogType
from app.models.user import User
from app.decorators import role_required, ADMIN, EDITOR_OR_ADMIN

changelog_bp = Blueprint('changelog', __name__)


@changelog_bp.route('/changelog')
@login_required
def changelog():
    """Changelog page with HTMX search and user filter."""
    search = request.args.get('q', '').strip()
    user_id = request.args.get('user_id', '').strip()
    change_type = request.args.get('type', '').strip()

    query = Changelog.query.order_by(Changelog.date.desc(), Changelog.id.desc())

    if search:
        query = query.filter(Changelog.description.ilike(f'%{search}%'))
    if user_id:
        query = query.filter(Changelog.user_id == int(user_id))
    if change_type:
        ct = ChangelogType.query.filter_by(type=change_type).first()
        if ct:
            query = query.filter(Changelog.change_type_id == ct.id)

    entries = query.all()

    if request.headers.get('HX-Request'):
        return render_template('fragments/changelog_list.html', entries=entries)

    # Get distinct users who have changelog entries
    user_ids = [r[0] for r in Changelog.query.with_entities(distinct(Changelog.user_id)).all() if r[0]]
    users = User.query.filter(User.id.in_(user_ids)).order_by(User.username).all()

    return render_template('changelog.html', entries=entries, search=search, user_id=user_id, users=users, change_type=change_type)


@changelog_bp.route('/changelog/<int:entry_id>', methods=['DELETE'])
@login_required
@role_required(ADMIN)
def delete_entry(entry_id):
    if not session.get('edit_mode'):
        abort(403)
    entry = db.session.get(Changelog, entry_id)
    if entry is None:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    return ''
