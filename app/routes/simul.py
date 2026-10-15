import re
from datetime import datetime, timezone

from flask import Blueprint, request, render_template, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import case

from app.extensions import db
from app.models.simul import SimulShow, SimulStatus, SimulStatusType
from app.models.user import User
from app.decorators import role_required, USER_OR_ABOVE, EDITOR_OR_ADMIN

simul_bp = Blueprint('simul', __name__, url_prefix='/simuls')

BUCKETS = ['planning', 'ongoing', 'paused', 'completed', 'dropped']
CATEGORIES = ['tv', 'movie', 'uncategorized']
UPCOMING_FILTERS = ('', 'only', 'exclude')  # '' = include upcoming


def _participants():
    """Grid columns: rateable ARIMA users, stable order."""
    return (User.query.filter(User.role_id.in_(tuple(USER_OR_ABOVE)))
            .order_by(User.sort_order.is_(None), User.sort_order, User.username).all())


def _years():
    rows = db.session.query(SimulShow.year).filter(SimulShow.year.isnot(None)).distinct().all()
    return sorted({r[0] for r in rows}, reverse=True)


def _status_map(shows):
    """{show_id: {'u:<id>'|'m:<name>': SimulStatus}} for O(1) cell lookup."""
    ids = [s.id for s in shows]
    out = {}
    if not ids:
        return out
    for st in SimulStatus.query.filter(SimulStatus.show_id.in_(ids)).all():
        key = f'u:{st.user_id}' if st.user_id else f'm:{st.member_name}'
        out.setdefault(st.show_id, {})[key] = st
    return out


def _merge_blocks(shows):
    """Group same-titled shows of the same type on one page into one block (one row per
    separate watch), placed where the first of them sorts."""
    blocks = {}
    for s in shows:
        blocks.setdefault((s.title.strip().casefold(), s.category), []).append(s)
    return list(blocks.values())


@simul_bp.route('/')
@login_required
def index():
    bucket = request.args.get('bucket', 'ongoing')
    if bucket not in BUCKETS:
        bucket = 'ongoing'
    years = _years()
    year = request.args.get('year', type=int)
    upcoming_filter = request.args.get('upcoming', '')
    if upcoming_filter not in UPCOMING_FILTERS:
        upcoming_filter = ''
    type_filter = request.args.get('type', '')
    if type_filter not in CATEGORIES:
        type_filter = ''
    q = SimulShow.query.filter_by(bucket=bucket)
    if upcoming_filter:
        q = q.filter_by(upcoming=(upcoming_filter == 'only'))
    if type_filter:
        q = q.filter_by(category=type_filter)
    if bucket != 'planning':
        if year not in years:
            year = years[0] if years else None
        if year is not None:
            q = q.filter_by(year=year)
    else:
        year = None
    shows = q.order_by(SimulShow.sort_order, SimulShow.id).all()
    users = _participants()
    status_types = SimulStatusType.query.order_by(SimulStatusType.sort_order).all()
    return render_template(
        'simul.html', bucket=bucket, buckets=BUCKETS, year=year, years=years,
        upcoming_filter=upcoming_filter, type_filter=type_filter,
        shows=shows, blocks=_merge_blocks(shows), users=users, status_map=_status_map(shows),
        status_types=status_types, categories=CATEGORIES,
        can_edit=current_user.is_editor_or_admin, title_width=_title_width())


TITLE_WIDTH_RANGE = (120, 900)


def _title_width():
    s = current_user.settings
    # SQLite may hand the auto-migrated column back as text.
    return int(s.simul_title_width) if s and s.simul_title_width else 320


@simul_bp.route('/title-width', methods=['POST'])
@login_required
def set_title_width():
    width = request.form.get('width', type=int)
    if not width or not current_user.settings:
        abort(400)
    lo, hi = TITLE_WIDTH_RANGE
    current_user.settings.simul_title_width = max(lo, min(hi, width))
    db.session.commit()
    return '', 204


def _render_cell(show, participant_key, status_types):
    """Re-render a single grid cell after an update (HTMX outerHTML swap)."""
    is_user = participant_key.startswith('u:')
    st = SimulStatus.query.filter_by(
        show_id=show.id,
        user_id=int(participant_key[2:]) if is_user else None,
        member_name=None if is_user else participant_key[2:]).first()
    editable = current_user.is_editor_or_admin or participant_key == f'u:{current_user.id}'
    return render_template('fragments/simul_cell.html', show=show, pkey=participant_key,
                           status=st, editable=editable, status_types=status_types)


@simul_bp.route('/status', methods=['POST'])
@login_required
@role_required(USER_OR_ABOVE)
def set_status():
    show_id = request.form.get('show_id', type=int)
    pkey = request.form.get('pkey', '')  # 'u:<id>' or 'm:<name>'
    type_id = request.form.get('status_type_id', type=int)  # missing/0 => clear
    note_raw = request.form.get('note')
    note_sent = note_raw is not None

    show = db.session.get(SimulShow, show_id)
    if not show or not pkey:
        abort(400)

    # Authorization: a user may only edit their own column; editors/admins any.
    if pkey != f'u:{current_user.id}' and not current_user.is_editor_or_admin:
        abort(403)

    is_user = pkey.startswith('u:')
    user_id = int(pkey[2:]) if is_user else None
    member_name = None if is_user else pkey[2:]
    st = SimulStatus.query.filter_by(
        show_id=show_id, user_id=user_id, member_name=member_name).first()

    if not type_id:
        if st:
            db.session.delete(st)
    else:
        if not st:
            st = SimulStatus(show_id=show_id, user_id=user_id, member_name=member_name,
                             status_type_id=type_id)
            db.session.add(st)
        else:
            st.status_type_id = type_id
        if note_sent:
            st.note = note_raw.strip() or None
    show.last_updated = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    status_types = SimulStatusType.query.order_by(SimulStatusType.sort_order).all()
    return _render_cell(show, pkey, status_types)


@simul_bp.route('/show', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def add_show():
    title = (request.form.get('title') or '').strip()
    category = request.form.get('category', 'uncategorized')
    bucket = request.form.get('bucket', 'planning')
    year = request.form.get('year', type=int)
    if category not in CATEGORIES:
        category = 'uncategorized'
    if bucket not in BUCKETS:
        bucket = 'planning'
    if bucket == 'planning':
        year = None
    if title:
        now = datetime.now(timezone.utc).isoformat()
        max_sort = db.session.query(db.func.max(SimulShow.sort_order)).scalar() or 0
        db.session.add(SimulShow(title=title, category=category, bucket=bucket, year=year,
                                 upcoming=request.form.get('upcoming') == '1',
                                 sort_order=max_sort + 1, created_at=now, last_updated=now))
        db.session.commit()
    return redirect(url_for('simul.index', bucket=bucket, year=year))


@simul_bp.route('/show/<int:show_id>/note', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def set_show_note(show_id):
    show = db.session.get(SimulShow, show_id)
    if not show:
        abort(404)
    show.notes = (request.form.get('note') or '').strip() or None
    show.last_updated = datetime.now(timezone.utc).isoformat()
    db.session.commit()
    return '', 204


@simul_bp.route('/show/<int:show_id>/edit', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def edit_show(show_id):
    show = db.session.get(SimulShow, show_id)
    if not show:
        abort(404)
    title = (request.form.get('title') or '').strip()
    if title:
        show.title = title
    url = (request.form.get('url') or '').strip()
    # Only web links: a bare domain gets https://, anything else (e.g. javascript:) is never an href.
    if url and not re.match(r'https?://', url, re.IGNORECASE):
        url = 'https://' + url
    show.url = url or None
    show.notes = (request.form.get('note') or '').strip() or None
    category = request.form.get('category')
    if category in CATEGORIES:
        show.category = category
    show.upcoming = request.form.get('upcoming') == '1'
    bucket = request.form.get('bucket')
    if bucket in BUCKETS:
        show.bucket = bucket
    if show.bucket == 'planning':
        show.year = None
    else:
        show.year = request.form.get('year', type=int) or show.year or datetime.now(timezone.utc).year
    show.last_updated = datetime.now(timezone.utc).isoformat()
    db.session.commit()
    return redirect(url_for('simul.index', bucket=show.bucket, year=show.year))


@simul_bp.route('/show/<int:show_id>/delete', methods=['POST'])
@login_required
@role_required(EDITOR_OR_ADMIN)
def delete_show(show_id):
    show = db.session.get(SimulShow, show_id)
    bucket, year = ('planning', None)
    if show:
        bucket, year = show.bucket, show.year
        db.session.delete(show)
        db.session.commit()
    return redirect(url_for('simul.index', bucket=bucket, year=year))
