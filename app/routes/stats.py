from flask import Blueprint, request, render_template, session, jsonify
from flask_login import login_required, current_user

from app.services.stats import (
    get_display_users, get_artist_stats, get_summary_stats,
    get_artist_score_stats, load_bulk_data, get_app_ops_stats,
)
from app.cache import get_cached_bulk_data, get_cached_railway_stats, get_cache_status
from app.services.railway import get_metrics_series
from app.services.railway_retention import is_enabled as retention_enabled, get_stored_metrics_series
from app.services.artist import get_top_level_artists, get_children, get_filtered_navbar

stats_bp = Blueprint('stats', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'}


def _get_viewer_settings():
    """Get the viewing user's filter settings."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return {
            'include_featured': current_user.settings.include_featured,
            'include_remixes': current_user.settings.include_remixes,
            'include_covers': current_user.settings.include_covers,
            'country_ids': list(current_user.settings.country_ids or []),
            'genre_ids': list(current_user.settings.genre_ids or []),
            'hide_osts': getattr(current_user.settings, 'hide_osts', False),
        }
    return {
        'include_featured': False,
        'include_remixes': False,
        'include_covers': True,
        'country_ids': list(session.get('country_ids') or []),
        'genre_ids': list(session.get('genre_ids') or []),
        'hide_osts': session.get('hide_osts', False),
    }


@stats_bp.route('/artist-stats')
@login_required
def artist_stats():
    """Artist Stats page — rating completion percentages."""
    users = get_display_users()
    settings = _get_viewer_settings()
    country_ids = settings.pop('country_ids')
    genre_ids = settings.pop('genre_ids')
    bulk = get_cached_bulk_data(**settings, genre_ids=genre_ids)

    artists = get_top_level_artists(bulk)
    if country_ids:
        country_set = set(country_ids)
        artists = [a for a in artists if a.country_id in country_set]

    summary = get_summary_stats(users, bulk, artists=artists)

    hide_osts = settings.get('hide_osts', False)
    artist_rows = []
    for a in artists:
        stats = get_artist_stats(a.id, users, bulk)
        if (genre_ids or hide_osts) and stats['song_count'] == 0:
            continue
        artist_rows.append({
            'artist': a,
            'stats': stats,
            'has_subunits': bulk.has_subunits(a.id),
        })

    return render_template('artist_stats.html',
                           users=users, summary=summary, artist_rows=artist_rows,
                           gender_css=GENDER_CSS, navbar_artists=get_filtered_navbar())


@stats_bp.route('/artist-stats/expand/<int:artist_id>')
@login_required
def expand_subunit(artist_id):
    """HTMX endpoint: return stats rows for subunits of an artist."""
    users = get_display_users()
    settings = _get_viewer_settings()
    settings.pop('country_ids')
    genre_ids = settings.pop('genre_ids')

    subunits, _ = get_children(artist_id)
    subunit_ids = [sub.id for sub in subunits]
    bulk = load_bulk_data(**settings, artist_ids=subunit_ids, genre_ids=genre_ids)

    rows = []
    for sub in subunits:
        stats = get_artist_stats(sub.id, users, bulk)
        rows.append({'artist': sub, 'stats': stats})

    return render_template('fragments/stats_row.html',
                           rows=rows, users=users, gender_css=GENDER_CSS, is_subunit=True,
                           parent_artist_id=artist_id)


@stats_bp.route('/global-stats')
@login_required
def global_stats():
    """Global Stats page — average scores per artist per user."""
    users = get_display_users()
    settings = _get_viewer_settings()
    country_ids = settings.pop('country_ids')
    genre_ids = settings.pop('genre_ids')
    bulk = get_cached_bulk_data(**settings, genre_ids=genre_ids)

    artists = get_top_level_artists(bulk)
    if country_ids:
        country_set = set(country_ids)
        artists = [a for a in artists if a.country_id in country_set]
    hide_osts = settings.get('hide_osts', False)
    artist_rows = []
    for a in artists:
        scores = get_artist_score_stats(a.id, users, bulk)
        if (genre_ids or hide_osts) and scores['song_count'] == 0:
            continue
        artist_rows.append({
            'artist': a,
            'scores': scores,
            'has_subunits': bulk.has_subunits(a.id),
        })

    return render_template('global_stats.html',
                           users=users, artist_rows=artist_rows,
                           gender_css=GENDER_CSS, navbar_artists=get_filtered_navbar())


@stats_bp.route('/global-stats/expand/<int:artist_id>')
@login_required
def expand_subunit_scores(artist_id):
    """HTMX endpoint: return score rows for subunits of an artist."""
    users = get_display_users()
    settings = _get_viewer_settings()
    settings.pop('country_ids')
    genre_ids = settings.pop('genre_ids')

    subunits, _ = get_children(artist_id)
    subunit_ids = [sub.id for sub in subunits]
    bulk = load_bulk_data(**settings, artist_ids=subunit_ids, genre_ids=genre_ids)

    rows = []
    for sub in subunits:
        scores = get_artist_score_stats(sub.id, users, bulk)
        rows.append({'artist': sub, 'scores': scores})

    return render_template('fragments/global_stats_row.html',
                           rows=rows, users=users, gender_css=GENDER_CSS, is_subunit=True,
                           parent_artist_id=artist_id)


@stats_bp.route('/operational-stats')
@login_required
def operational_stats():
    """Operational Stats page — app-level health + Railway platform stats.

    The page shell and cheap app-level stats render immediately; the Railway
    block is lazy-loaded as an HTMX fragment so the slow external call never
    blocks first paint.
    """
    from app.services.billing import get_billing_cycles
    return render_template('operational_stats.html',
                           ops=get_app_ops_stats(),
                           cache_status=get_cache_status(),
                           billing_cycles=get_billing_cycles())


@stats_bp.route('/operational-stats/railway-costs')
@login_required
def operational_stats_railway_costs():
    """HTMX fragment: cached Railway project-usage dollar cards."""
    return render_template('fragments/railway_costs.html',
                           railway=get_cached_railway_stats())


@stats_bp.route('/operational-stats/railway')
@login_required
def operational_stats_railway():
    """HTMX fragment: cached Railway platform stats (metrics, deploys, usage)."""
    return render_template('fragments/railway_stats.html',
                           railway=get_cached_railway_stats())


@stats_bp.route('/operational-stats/metrics.json')
@login_required
def operational_stats_metrics():
    """Resource-metric time-series JSON for the charts, windowed by ?start=&end= (unix seconds)."""
    import time as _time
    now = int(_time.time())
    try:
        end = int(request.args.get('end', now))
        start = int(request.args.get('start', now - 7 * 86400))
    except (TypeError, ValueError):
        start, end = now - 7 * 86400, now
    # With retention on, serve from the local store so windows can exceed Railway's
    # 30-day limit; otherwise query Railway live (capped at its retention).
    if retention_enabled():
        return jsonify(get_stored_metrics_series(start, end))
    return jsonify(get_metrics_series(start, end))
