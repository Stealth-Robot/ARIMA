from flask import Blueprint, request, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.update import Update
from app.decorators import role_required, ADMIN

updates_bp = Blueprint('updates', __name__)


@updates_bp.route('/updates')
@login_required
def updates_page():
    updates = Update.query.order_by(Update.date.desc()).all()
    return render_template('updates.html', updates=updates)


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

    db.session.add(Update(commit_id=commit_id, description=description, date=date))
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
