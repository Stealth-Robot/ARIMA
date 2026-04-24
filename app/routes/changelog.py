from flask import Blueprint, request, render_template, abort, session
from flask_login import login_required
from markupsafe import Markup, escape
from sqlalchemy import distinct, func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.changelog import Changelog
from app.models.lookups import ChangelogType
from app.models.user import User
from app.decorators import role_required, ADMIN, EDITOR_OR_ADMIN

changelog_bp = Blueprint('changelog', __name__)

PAGE_SIZE = 100


@changelog_bp.route('/changelog')
@login_required
def changelog():
    """Changelog page with HTMX search, user filter, and cursor pagination."""
    search = request.args.get('q', '').strip()
    user_ids = [v for v in request.args.getlist('user_id') if v.strip()]
    include = request.args.getlist('include')
    before = request.args.get('before', type=int)

    _type_order = {'Album': 0, 'Artist': 1, 'Link': 2, 'Rating': 3, 'Song': 4, 'Legacy': 99}
    all_types = sorted(ChangelogType.query.all(), key=lambda t: _type_order.get(t.type, 50))
    all_type_names = [t.type for t in all_types]

    query = Changelog.query.options(
        joinedload(Changelog.user), joinedload(Changelog.change_type),
    ).order_by(Changelog.date.desc(), Changelog.id.desc())

    if search:
        query = query.filter(Changelog.description.ilike(f'%{search}%'))
    if user_ids:
        query = query.filter(Changelog.user_id.in_([int(v) for v in user_ids]))
    if include:
        include_ids = [ct.id for ct in all_types if ct.type in include]
        if include_ids:
            query = query.filter(Changelog.change_type_id.in_(include_ids))

    if before:
        query = query.filter(Changelog.id < before)

    entries = query.limit(PAGE_SIZE + 1).all()
    has_more = len(entries) > PAGE_SIZE
    entries = entries[:PAGE_SIZE]
    last_id = entries[-1].id if entries else None

    # Use pre-rendered HTML, fall back to escaped plain text for old rows
    for e in entries:
        e._linked_desc = Markup(e.description_html) if e.description_html else escape(e.description)

    # "Load More" HTMX request — return rows + OOB load-more button
    if before and request.headers.get('HX-Request'):
        return render_template('fragments/changelog_entries.html',
                               entries=entries, has_more=has_more, last_id=last_id)

    # Compute shown/hidden types for summary
    if include:
        shown = [t for t in all_type_names if t in include]
    else:
        shown = list(all_type_names)
    hidden = [t for t in all_type_names if t not in shown]

    # Get distinct users who have changelog entries
    all_user_ids = [r[0] for r in Changelog.query.with_entities(distinct(Changelog.user_id)).all() if r[0]]
    users = User.query.filter(User.id.in_(all_user_ids)).order_by(func.lower(User.username)).all()

    # Compute shown/hidden users for summary
    selected_ids = {int(v) for v in user_ids}
    if selected_ids:
        shown_users = [u.username for u in users if u.id in selected_ids]
    else:
        shown_users = [u.username for u in users]
    hidden_users = [u.username for u in users if u.username not in shown_users]

    if request.headers.get('HX-Request'):
        return render_template('fragments/changelog_list.html', entries=entries,
                               shown=shown, hidden=hidden,
                               shown_users=shown_users, hidden_users=hidden_users,
                               has_more=has_more, last_id=last_id)

    return render_template('changelog.html', entries=entries, search=search, user_ids=user_ids,
                           users=users, all_types=all_types, include=include,
                           shown=shown, hidden=hidden,
                           shown_users=shown_users, hidden_users=hidden_users,
                           has_more=has_more, last_id=last_id)


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
