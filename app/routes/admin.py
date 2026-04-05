from flask import Blueprint, request, render_template, redirect, url_for
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
