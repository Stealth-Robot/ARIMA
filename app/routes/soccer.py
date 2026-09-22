from datetime import datetime, timezone

from flask import Blueprint, request, render_template, redirect, url_for, abort, flash
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.soccer import SoccerSeason, SoccerGame, SoccerPlayer, SoccerAvailability
from app.services.soccer import (CATEGORIES, CATEGORY_LABELS, COUNT_LINES, cell_colour,
                                 canonical_date, canonical_time, date_within_horizon,
                                 HOUR_CHOICES, MINUTE_CHOICES, time_from_form,
                                 MAX_FUTURE_DAYS, MAX_GAMES, MAX_NAME, MAX_PLAYERS,
                                 MAX_SEASONS,
                                 count_colour, season_counts, theme_color_scheme)
from app.services.theme import get_resolved_theme

# Deliberately public: no @login_required and no @role_required anywhere in this module.
# The soccer surface is open to anyone who can reach the host, by product decision.
soccer_bp = Blueprint('soccer', __name__, url_prefix='/soccer')

SEASON_LIMIT = 5



def _recent_seasons():
    """The selector's options: most recently created first, capped at 5.

    Ordered by id, not by start_date — a season is created with only a name, so it has no
    span until days are added to it.
    """
    return (SoccerSeason.query.order_by(SoccerSeason.id.desc())
            .limit(SEASON_LIMIT).all())


def _admin_password_ok():
    """Deletes are gated on the admin account's own password, not on a session.

    The rest of this surface is public and has no logged-in user, so the shared
    _verify_password() helper (which reads current_user) cannot be reused here.
    """
    from app.models.user import User
    from app.routes.auth import _check_password
    password = request.form.get('password', '')
    if not password:
        return False
    admin = User.query.filter(User.role_id == 0).first()
    if not admin or not admin.password:
        return False
    return _check_password(admin.password, password)


def _availability_map(games):
    """{game_id: {player_id: SoccerAvailability}} for O(1) cell lookup."""
    ids = [g.id for g in games]
    out = {}
    if not ids:
        return out
    for row in SoccerAvailability.query.filter(SoccerAvailability.game_id.in_(ids)).all():
        out.setdefault(row.game_id, {})[row.player_id] = row
    return out


@soccer_bp.route('/', strict_slashes=False)
def index():
    seasons = _recent_seasons()
    season_id = request.args.get('season', type=int)
    # Resolve any season by id, not just the 5 in the selector — otherwise a season whose
    # start_date falls outside the newest 5 is created and then unreachable.
    season = db.session.get(SoccerSeason, season_id) if season_id else None
    if season is None:
        season = seasons[0] if seasons else None
    # Keep the viewed season visible in the selector even when it is older than the top 5,
    # or the control would show a different season as selected than the grid shows.
    if season is not None and all(s.id != season.id for s in seasons):
        seasons = seasons + [season]

    games, players, availability, counts = [], [], {}, {}
    if season is not None:
        games = (SoccerGame.query.filter_by(season_id=season.id)
                 .order_by(SoccerGame.date, SoccerGame.kickoff, SoccerGame.id).all())
        players = (SoccerPlayer.query.filter_by(season_id=season.id)
                   .order_by(SoccerPlayer.sort_order, SoccerPlayer.id).all())
        availability = _availability_map(games)
        counts = season_counts(games, players, availability)

    _theme = get_resolved_theme(current_user)
    return render_template(
        'soccer.html', season=season, seasons=seasons, games=games,
        players=players, availability=availability, counts_map=counts,
        categories=CATEGORIES, category_labels=CATEGORY_LABELS,
        count_lines=COUNT_LINES, count_colour=count_colour,
        cell_colour=cell_colour,
        # inject_theme gives anonymous visitors {}, which would drop every colour var.
        hour_choices=HOUR_CHOICES, minute_choices=MINUTE_CHOICES,
        # A native date input cannot prefill the year segment alone, so it gets a full date.
        today=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        theme=_theme, color_scheme=theme_color_scheme(_theme))


def _render_count(game, season):
    """Re-render one date's count cell for the out-of-band swap after a cell change."""
    players = SoccerPlayer.query.filter_by(season_id=season.id).all()
    counts = season_counts([game], players, _availability_map([game]))
    return render_template('fragments/soccer_count.html', game=game,
                           counts=counts.get(game.id, {}), count_lines=COUNT_LINES,
                           count_colour=count_colour, oob=True)


@soccer_bp.route('/availability', methods=['POST'])
def set_availability():
    game_id = request.form.get('game_id', type=int)
    player_id = request.form.get('player_id', type=int)
    raw = request.form.get('available', '')

    if game_id is None or player_id is None:
        abort(400)
    game = db.session.get(SoccerGame, game_id)
    player = db.session.get(SoccerPlayer, player_id)
    if not game or not player or game.season_id != player.season_id:
        abort(400)

    row = SoccerAvailability.query.filter_by(game_id=game_id, player_id=player_id).first()
    if raw not in ('0', '1'):
        if row:
            db.session.delete(row)
    elif row:
        row.available = int(raw)
    else:
        db.session.add(SoccerAvailability(game_id=game_id, player_id=player_id,
                                          available=int(raw)))
    try:
        db.session.commit()
    except IntegrityError:
        # Two first-writes to the same empty cell race the unique index; the loser re-reads
        # and updates instead of 500ing.
        db.session.rollback()
        row = SoccerAvailability.query.filter_by(game_id=game_id,
                                                 player_id=player_id).first()
        if row:
            row.available = int(raw)
            db.session.commit()

    row = SoccerAvailability.query.filter_by(game_id=game_id, player_id=player_id).first()
    cell = render_template('fragments/soccer_cell.html', game=game, player=player,
                           row=row, cell_colour=cell_colour)
    return cell + _render_count(game, game.season)


@soccer_bp.route('/player', methods=['POST'])
def add_player():
    season_id = request.form.get('season_id', type=int)
    category = request.form.get('category', '')
    name = (request.form.get('name') or '').strip()

    season = db.session.get(SoccerSeason, season_id)
    if not season or not name or category not in CATEGORIES:
        flash('Could not add that player — a name and a valid group are required.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    if len(name) > MAX_NAME:
        flash(f'Player names are limited to {MAX_NAME} characters.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    if SoccerPlayer.query.filter_by(season_id=season_id).count() >= MAX_PLAYERS:
        flash(f'This season already has the maximum of {MAX_PLAYERS} players.', 'error')
        return redirect(url_for('soccer.index', season=season_id))

    max_sort = (db.session.query(db.func.max(SoccerPlayer.sort_order))
                .filter_by(season_id=season_id).scalar() or 0)
    db.session.add(SoccerPlayer(season_id=season_id, name=name, category=category,
                                sort_order=max_sort + 1))
    db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))


@soccer_bp.route('/season/<int:season_id>/rename', methods=['POST'])
def rename_season(season_id):
    season = db.session.get(SoccerSeason, season_id)
    name = (request.form.get('name') or '').strip()
    if not season:
        return 'Not found', 404
    if not name or len(name) > MAX_NAME:
        flash(f'A season needs a name of at most {MAX_NAME} characters.', 'error')
    else:
        season.name = name
        db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))


@soccer_bp.route('/player/<int:player_id>/rename', methods=['POST'])
def rename_player(player_id):
    player = db.session.get(SoccerPlayer, player_id)
    name = (request.form.get('name') or '').strip()
    if not player:
        return 'Not found', 404
    if not name or len(name) > MAX_NAME:
        flash(f'A player needs a name of at most {MAX_NAME} characters.', 'error')
    else:
        player.name = name
        db.session.commit()
    return redirect(url_for('soccer.index', season=player.season_id))


@soccer_bp.route('/day/<int:game_id>/edit', methods=['POST'])
def edit_day(game_id):
    game = db.session.get(SoccerGame, game_id)
    if not game:
        return 'Not found', 404
    season_id = game.season_id
    date = canonical_date(request.form.get('date'))
    # A submitted-but-empty time means "no specific time, inherit the season's"; a field
    # that is absent entirely (a non-browser post) leaves the existing value alone.
    kickoff, present = time_from_form(request.form)
    if not present:
        kickoff = game.kickoff

    if not date:
        flash('That is not a valid date.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    if not date_within_horizon(date):
        flash(f'That date is more than {MAX_FUTURE_DAYS} days out.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    game.date = date
    game.kickoff = kickoff
    db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))


@soccer_bp.route('/player/<int:player_id>/delete', methods=['POST'])
def delete_player(player_id):
    if not _admin_password_ok():
        return 'Incorrect password', 403
    player = db.session.get(SoccerPlayer, player_id)
    if player is None:
        return 'Not found', 404
    season_id = player.season_id
    db.session.delete(player)   # availability rows cascade
    db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))


@soccer_bp.route('/season/<int:season_id>/delete', methods=['POST'])
def delete_season(season_id):
    if not _admin_password_ok():
        return 'Incorrect password', 403
    season = db.session.get(SoccerSeason, season_id)
    if season is None:
        return 'Not found', 404
    db.session.delete(season)   # games, players and availability cascade
    db.session.commit()
    return redirect(url_for('soccer.index'))


@soccer_bp.route('/season', methods=['POST'])
def add_season():
    """A season is just a name. Its days are added one at a time, and its span is derived
    from them."""
    name = (request.form.get('name') or '').strip()
    if not name or len(name) > MAX_NAME:
        flash(f'A season needs a name of at most {MAX_NAME} characters.', 'error')
        return redirect(url_for('soccer.index'))
    if SoccerSeason.query.count() >= MAX_SEASONS:
        flash(f'There are already {MAX_SEASONS} seasons.', 'error')
        return redirect(url_for('soccer.index'))

    # Captured before the insert, or the new season would be its own most recent.
    previous = SoccerSeason.query.order_by(SoccerSeason.id.desc()).first()

    season = SoccerSeason(name=name, start_date='', end_date='',
                          created_at=datetime.now(timezone.utc).isoformat())
    db.session.add(season)
    db.session.flush()

    if previous is not None:
        squad = (SoccerPlayer.query.filter_by(season_id=previous.id)
                 .order_by(SoccerPlayer.sort_order, SoccerPlayer.id).all())
        for player in squad:
            db.session.add(SoccerPlayer(season_id=season.id, name=player.name,
                                        category=player.category,
                                        sort_order=player.sort_order))
    db.session.commit()
    return redirect(url_for('soccer.index', season=season.id))


@soccer_bp.route('/day', methods=['POST'])
def add_day():
    season_id = request.form.get('season_id', type=int)
    date = canonical_date(request.form.get('date'))
    kickoff, _ = time_from_form(request.form)

    season = db.session.get(SoccerSeason, season_id)
    if not season or not date:
        flash('Could not add that day — a season and a valid date are required.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    if not date_within_horizon(date):
        flash(f'That date is more than {MAX_FUTURE_DAYS} days out.', 'error')
        return redirect(url_for('soccer.index', season=season_id))
    if SoccerGame.query.filter_by(season_id=season_id).count() >= MAX_GAMES:
        flash(f'This season already has the maximum of {MAX_GAMES} games.', 'error')
        return redirect(url_for('soccer.index', season=season_id))

    # A date may repeat: several fixtures can share a day, distinguished by kickoff.
    db.session.add(SoccerGame(season_id=season_id, date=date, kickoff=kickoff))
    db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))


@soccer_bp.route('/day/<int:game_id>/delete', methods=['POST'])
def delete_day(game_id):
    if not _admin_password_ok():
        return 'Incorrect password', 403
    game = db.session.get(SoccerGame, game_id)
    if game is None:
        return 'Not found', 404
    season_id = game.season_id
    db.session.delete(game)   # availability rows cascade
    db.session.commit()
    return redirect(url_for('soccer.index', season=season_id))
