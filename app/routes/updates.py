from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, request, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.update import Update
from app.decorators import role_required, ADMIN

updates_bp = Blueprint('updates', __name__)

ET = ZoneInfo('America/New_York')
UTC = ZoneInfo('UTC')


def _et_to_utc(date_str):
    """Convert 'YYYY-MM-DD HH:MM' in Eastern to UTC ISO string. Returns None if invalid."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
    except ValueError:
        return None
    dt_et = dt.replace(tzinfo=ET)
    dt_utc = dt_et.astimezone(UTC)
    return dt_utc.strftime('%Y-%m-%d %H:%M:%S')


def _utc_to_et(utc_str):
    """Convert UTC datetime string to Eastern 'YYYY-MM-DD HH:MM'."""
    # Handle both 'YYYY-MM-DD HH:MM:SS' and 'YYYY-MM-DD HH:MM'
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            dt = datetime.strptime(utc_str, fmt)
            break
        except ValueError:
            continue
    else:
        return utc_str
    dt_utc = dt.replace(tzinfo=UTC)
    dt_et = dt_utc.astimezone(ET)
    return dt_et.strftime('%Y-%m-%d %H:%M')


@updates_bp.route('/updates')
@login_required
def updates_page():
    updates = Update.query.order_by(Update.date.desc()).all()
    # Convert UTC dates to Eastern for display
    display_updates = []
    for u in updates:
        display_updates.append({
            'id': u.id,
            'commit_id': u.commit_id,
            'description': u.description,
            'date_et': _utc_to_et(u.date),
        })
    return render_template('updates.html', updates=display_updates)


@updates_bp.route('/updates/add', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_update():
    commit_id = request.form.get('commit_id', '').strip()
    description = request.form.get('description', '').strip()
    date = request.form.get('date', '').strip()

    if not commit_id or not description or not date:
        return redirect(url_for('updates.updates_page'))

    if Update.query.filter_by(commit_id=commit_id).first():
        return redirect(url_for('updates.updates_page'))

    date_utc = _et_to_utc(date)
    if not date_utc:
        return redirect(url_for('updates.updates_page'))
    db.session.add(Update(commit_id=commit_id, description=description, date=date_utc))
    db.session.commit()
    return redirect(url_for('updates.updates_page'))


@updates_bp.route('/updates/<int:update_id>/edit', methods=['POST'])
@login_required
@role_required(ADMIN)
def edit_update(update_id):
    update = db.session.get(Update, update_id)
    if not update:
        abort(404)
    description = request.form.get('description', '').strip()
    if description:
        update.description = description
        db.session.commit()
    return redirect(url_for('updates.updates_page'))


@updates_bp.route('/updates/<int:update_id>/delete', methods=['POST'])
@login_required
@role_required(ADMIN)
def delete_update(update_id):
    update = db.session.get(Update, update_id)
    if not update:
        abort(404)
    db.session.delete(update)
    db.session.commit()
    return redirect(url_for('updates.updates_page'))


@updates_bp.route('/updates/latest-id')
@login_required
def latest_update_id():
    latest = Update.query.order_by(Update.id.desc()).first()
    return {'id': latest.id if latest else 0}
