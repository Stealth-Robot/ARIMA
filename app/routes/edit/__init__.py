from flask import Blueprint, session, abort, request, redirect, url_for
from flask_login import login_required, current_user

from app.cache import clear_stats_cache

edit_bp = Blueprint('edit', __name__, url_prefix='/edit')


def _get_filters():
    """Return (country_ids, genre_ids) from user settings or session."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return (list(current_user.settings.country_ids or []),
                list(current_user.settings.genre_ids or []))
    return (list(session.get('country_ids') or []),
            list(session.get('genre_ids') or []))


def _require_edit_mode():
    if not session.get('edit_mode'):
        abort(403)


def _verify_password():
    """Check current user's password from form data. Returns True or False."""
    password = request.form.get('password', '')
    if not password:
        return False
    from app.routes.auth import _check_password
    if not current_user.password or not _check_password(current_user.password, password):
        return False
    return True


@edit_bp.after_request
def _clear_stats_after_edit(response):
    """Clear stats cache after any successful edit operation."""
    if response.status_code < 400:
        clear_stats_cache()
    return response


@edit_bp.route('/artist/<int:artist_id>')
@login_required
def artist_redirect(artist_id):
    """Redirect /edit/artist/<id> to the artist detail page."""
    return redirect(url_for('artists.artist_detail', artist_id=artist_id))


# Import sub-modules to register their routes on edit_bp
from app.routes.edit import artist  # noqa: F401, E402
from app.routes.edit import album   # noqa: F401, E402
from app.routes.edit import song    # noqa: F401, E402
from app.routes.edit import auto_spotify  # noqa: F401, E402
