from flask import Blueprint, request, render_template, session
from flask_login import login_required, current_user

from app.services.stats import (
    get_display_users, get_artist_stats, get_summary_stats,
    get_artist_score_stats, load_bulk_data,
)
from app.cache import get_cached_bulk_data
from app.services.artist import get_top_level_artists, get_children, get_filtered_navbar

stats_bp = Blueprint('stats', __name__)

GENDER_CSS = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed'}


def _get_viewer_settings():
    """Get the viewing user's filter settings."""
    if current_user.is_authenticated and not current_user.is_system_or_guest and current_user.settings:
        return {
            'include_featured': current_user.settings.include_featured,
            'include_remixes': current_user.settings.include_remixes,
        }
    return {'include_featured': False, 'include_remixes': False}


@stats_bp.route('/artist-stats')
@login_required
def artist_stats():
    """Artist Stats page — rating completion percentages."""
    users = get_display_users()
    settings = _get_viewer_settings()
    bulk = get_cached_bulk_data(**settings)

    summary = get_summary_stats(users, bulk)

    artists = get_top_level_artists(bulk)
    artist_rows = []
    for a in artists:
        stats = get_artist_stats(a.id, users, bulk)
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

    subunits, _ = get_children(artist_id)
    subunit_ids = [sub.id for sub in subunits]
    bulk = load_bulk_data(**settings, artist_ids=subunit_ids)

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
    bulk = get_cached_bulk_data(**settings)

    artists = get_top_level_artists(bulk)
    artist_rows = []
    for a in artists:
        scores = get_artist_score_stats(a.id, users, bulk)
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

    subunits, _ = get_children(artist_id)
    subunit_ids = [sub.id for sub in subunits]
    bulk = load_bulk_data(**settings, artist_ids=subunit_ids)

    rows = []
    for sub in subunits:
        scores = get_artist_score_stats(sub.id, users, bulk)
        rows.append({'artist': sub, 'scores': scores})

    return render_template('fragments/global_stats_row.html',
                           rows=rows, users=users, gender_css=GENDER_CSS, is_subunit=True,
                           parent_artist_id=artist_id)
