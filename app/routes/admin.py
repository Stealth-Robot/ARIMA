import os
import shutil

from flask import Blueprint, request, render_template, redirect, url_for, current_app
from flask_login import login_required

from app.extensions import db
from app.models.lookups import Genre, Country
from app.decorators import role_required, ADMIN
from app.cache import clear_filter_cache
from app.services.artist import sync_misc_artist_stubs

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@login_required
@role_required(ADMIN)
def admin_page():
    genres = Genre.query.order_by(Genre.genre).all()
    countries = Country.query.order_by(Country.country).all()
    return render_template('admin.html', genres=genres, countries=countries)


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
    db.session.flush()

    sync_misc_artist_stubs()
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
    db.session.flush()

    sync_misc_artist_stubs()
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
