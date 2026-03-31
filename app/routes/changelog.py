from flask import Blueprint, request, render_template
from flask_login import login_required

from app.models.changelog import Changelog

changelog_bp = Blueprint('changelog', __name__)


@changelog_bp.route('/changelog')
@login_required
def changelog():
    """Changelog page with HTMX search."""
    search = request.args.get('q', '').strip()

    query = Changelog.query.order_by(Changelog.date.desc(), Changelog.id.desc())

    if search:
        query = query.filter(Changelog.description.ilike(f'%{search}%'))

    entries = query.all()

    if request.headers.get('HX-Request'):
        return render_template('fragments/changelog_list.html', entries=entries)
    return render_template('changelog.html', entries=entries, search=search)
