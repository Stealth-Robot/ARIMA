from functools import wraps

from flask import redirect, url_for
from flask_login import current_user

# Explicit role ID sets — never use < or > comparisons on role_id.
ADMIN = {0}
EDITOR_OR_ADMIN = {0, 1}
USER_OR_ABOVE = {0, 1, 2}
ALL_ROLES = {0, 1, 2, 3}


def role_required(allowed_role_ids):
    """Allow only users whose role_id is in the given set.

    MUST be stacked below @login_required — this decorator only checks role,
    not authentication.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if current_user.role_id not in allowed_role_ids:
                return redirect(url_for('home.home'))
            return f(*args, **kwargs)
        return decorated
    return decorator
