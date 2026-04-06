from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, request, render_template, redirect, url_for, abort, flash, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models.update import Update
from app.models.lookups import UpdateType
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
    all_types = UpdateType.query.order_by(UpdateType.id).all()
    include = request.args.getlist('include')

    query = Update.query
    if include:
        type_ids = [t.id for t in all_types if t.type in include]
        if type_ids:
            query = query.filter(Update.type_id.in_(type_ids))
        else:
            query = query.filter(db.literal(False))

    updates = query.order_by(Update.date.desc()).all()
    latest_date = Update.query.order_by(Update.date.desc()).first()
    latest_et = _utc_to_et(latest_date.date) if latest_date else ''
    saved_form = session.pop('_csrf_form_data', {})
    return render_template('updates.html', updates=updates, saved_form=saved_form,
                           all_types=all_types, include=include, latest_et=latest_et)


@updates_bp.route('/updates/timeline')
@login_required
def updates_timeline():
    all_types = UpdateType.query.order_by(UpdateType.id).all()
    include = request.args.getlist('include')

    query = Update.query
    if include:
        type_ids = [t.id for t in all_types if t.type in include]
        if type_ids:
            query = query.filter(Update.type_id.in_(type_ids))
        else:
            query = query.filter(db.literal(False))

    updates = query.order_by(Update.date.desc()).all()

    # Stats for the banner
    from collections import Counter
    type_counts = Counter(u.type.type if u.type else 'Other' for u in updates)
    total = len(updates)

    return render_template('updates_timeline.html', updates=updates,
                           all_types=all_types, include=include,
                           total=total, type_counts=type_counts)


@updates_bp.route('/updates/add', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_update():
    commit_id = request.form.get('commit_id', '').strip()
    description = request.form.get('description', '').strip()
    date = request.form.get('date', '').strip()
    type_id = request.form.get('type_id', type=int)

    if not commit_id or not description or not date:
        flash('All fields are required.', 'error')
        return redirect(url_for('updates.updates_page'))

    if Update.query.filter_by(commit_id=commit_id).first():
        flash('An update with that commit ID already exists.', 'error')
        return redirect(url_for('updates.updates_page'))

    date_utc = _et_to_utc(date)
    if not date_utc:
        flash('Invalid date — use YYYY-MM-DD HH:MM format.', 'error')
        return redirect(url_for('updates.updates_page'))
    db.session.add(Update(commit_id=commit_id, description=description, date=date_utc, type_id=type_id))
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
    commit_id = request.form.get('commit_id', '').strip()
    date = request.form.get('date', '').strip()
    type_id = request.form.get('type_id', type=int)
    if description:
        update.description = description
    if commit_id:
        update.commit_id = commit_id
    if date:
        date_utc = _et_to_utc(date)
        if date_utc:
            update.date = date_utc
    if type_id is not None:
        update.type_id = type_id
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


@updates_bp.route('/updates/check-commit')
@login_required
@role_required(ADMIN)
def check_commit():
    commit_id = request.args.get('commit_id', '').strip()
    exists = Update.query.filter_by(commit_id=commit_id).first() is not None if commit_id else False
    return {'exists': exists}
