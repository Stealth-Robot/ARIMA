from datetime import datetime, timezone

import markdown as md
from flask import Blueprint, request, render_template
from flask_login import login_required, current_user

from app.extensions import db
from app.models.rules import Rules
from app.decorators import role_required, EDITOR_OR_ADMIN

rules_bp = Blueprint('rules', __name__)


def _render(content):
    return md.markdown(content, extensions=['nl2br', 'sane_lists'])


@rules_bp.route('/rules')
@login_required
def rules():
    """Display rules page."""
    rule = db.session.get(Rules, 1)
    rendered = _render(rule.content) if rule and rule.content else ''
    return render_template('rules.html', rule=rule, rendered=rendered)


@rules_bp.route('/rules/display')
@login_required
def rules_display():
    """Return display fragment (HTMX) — used by Cancel button."""
    rule = db.session.get(Rules, 1)
    rendered = _render(rule.content) if rule and rule.content else ''
    return render_template('fragments/rules_display.html', rule=rule, rendered=rendered)


@rules_bp.route('/rules/edit')
@login_required
@role_required(EDITOR_OR_ADMIN)
def rules_edit():
    """Return edit form fragment (HTMX)."""
    rule = db.session.get(Rules, 1)
    return render_template('fragments/rules_edit_form.html', rule=rule)


@rules_bp.route('/rules', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def rules_save():
    """Save rules content. Returns display fragment (HTMX)."""
    content = request.form.get('content', '').strip()
    rule = db.session.get(Rules, 1)
    if rule:
        rule.content = content
        rule.last_edited_by = current_user.id
        rule.last_edited_at = datetime.now(timezone.utc).isoformat()
        db.session.commit()
    rendered = _render(rule.content) if rule and rule.content else ''
    return render_template('fragments/rules_display.html', rule=rule, rendered=rendered)
