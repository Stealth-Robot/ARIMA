import os
import shutil

from flask import Blueprint, request, render_template, redirect, url_for, current_app
from flask_login import login_required

from sqlalchemy import func

from app.extensions import db
from app.models.lookups import Genre, Country
from app.decorators import role_required, ADMIN
from app.cache import clear_filter_cache

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@login_required
@role_required(ADMIN)
def admin_page():
    from app.services.billing import get_billing_cycles
    genres = Genre.query.order_by(func.lower(Genre.genre)).all()
    countries = Country.query.order_by(func.lower(Country.country)).all()
    return render_template('admin.html', genres=genres, countries=countries,
                           billing_cycles=get_billing_cycles())


@admin_bp.route('/admin/billing-costs', methods=['POST'])
@login_required
@role_required(ADMIN)
def save_billing_costs():
    """Save the manually-entered real cost for each billing cycle."""
    from app.models.billing_cost import BillingCost
    for key, raw in request.form.items():
        if not key.startswith('cost_'):
            continue
        cycle_start = key[len('cost_'):]
        raw = raw.strip()
        existing = db.session.get(BillingCost, cycle_start)
        if raw == '':
            if existing:
                db.session.delete(existing)
            continue
        try:
            amount = float(raw)
        except ValueError:
            continue
        if existing:
            existing.amount = amount
        else:
            db.session.add(BillingCost(cycle_start=cycle_start, amount=amount))
    db.session.commit()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/add-genre', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_genre():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('admin.admin_page'))

    if Genre.query.filter(db.func.lower(Genre.genre) == name.lower()).first():
        return redirect(url_for('admin.admin_page'))

    max_id = db.session.query(db.func.max(Genre.id)).scalar() or -1
    db.session.add(Genre(id=max_id + 1, genre=name))
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/add-country', methods=['POST'])
@login_required
@role_required(ADMIN)
def add_country():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('admin.admin_page'))

    if Country.query.filter(db.func.lower(Country.country) == name.lower()).first():
        return redirect(url_for('admin.admin_page'))

    max_id = db.session.query(db.func.max(Country.id)).scalar() or -1
    db.session.add(Country(id=max_id + 1, country=name))
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/rename-genre', methods=['POST'])
@login_required
@role_required(ADMIN)
def rename_genre():
    genre_id = request.form.get('id', '').strip()
    name = request.form.get('name', '').strip()
    if not genre_id or not name:
        return redirect(url_for('admin.admin_page'))

    genre = db.session.get(Genre, int(genre_id))
    if genre is None:
        return redirect(url_for('admin.admin_page'))

    # 'OST' is special-cased by name in filtering logic across the app; renaming it
    # would silently break those lookups, so it cannot be renamed.
    if genre.genre == 'OST':
        return redirect(url_for('admin.admin_page'))

    if name.lower() != genre.genre.lower() and Genre.query.filter(
        db.func.lower(Genre.genre) == name.lower(), Genre.id != genre.id
    ).first():
        return redirect(url_for('admin.admin_page'))

    genre.genre = name
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/rename-country', methods=['POST'])
@login_required
@role_required(ADMIN)
def rename_country():
    country_id = request.form.get('id', '').strip()
    name = request.form.get('name', '').strip()
    if not country_id or not name:
        return redirect(url_for('admin.admin_page'))

    country = db.session.get(Country, int(country_id))
    if country is None:
        return redirect(url_for('admin.admin_page'))

    if name.lower() != country.country.lower() and Country.query.filter(
        db.func.lower(Country.country) == name.lower(), Country.id != country.id
    ).first():
        return redirect(url_for('admin.admin_page'))

    country.country = name
    db.session.commit()
    clear_filter_cache()
    return redirect(url_for('admin.admin_page'))


@admin_bp.route('/admin/replace-database', methods=['GET', 'POST'])
@login_required
@role_required(ADMIN)
def replace_database():
    """Replace the SQLite database file with an uploaded one."""
    if request.method == 'GET':
        return render_template('replace_database.html')

    from app.routes.edit import _verify_password
    if not _verify_password():
        return 'Incorrect password', 403

    uploaded = request.files.get('database')
    if not uploaded or not uploaded.filename.endswith('.db'):
        return 'No valid .db file uploaded', 400

    header = uploaded.read(16)
    uploaded.seek(0)
    if header[:16] != b'SQLite format 3\x00':
        return 'File is not a valid SQLite database', 400

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    if not db_path.startswith('/'):
        db_path = os.path.join(current_app.instance_path, db_path)

    db.session.remove()
    db.engine.dispose()

    if os.path.exists(db_path):
        shutil.copy2(db_path, db_path + '.bak')

    uploaded.save(db_path)

    for ext in ('-wal', '-shm'):
        wal_path = db_path + ext
        if os.path.exists(wal_path):
            os.remove(wal_path)

    return redirect(url_for('home.home'))
