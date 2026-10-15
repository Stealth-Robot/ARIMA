"""One-off: replace all simul shows/statuses with the refreshed xlsx export in
app/data/simul_seed.json. Remove this module and its call once it has run in production."""
import logging

logger = logging.getLogger(__name__)

# Stamped on every reseeded show's created_at so the wipe runs exactly once.
RESEED_STAMP = '2026-10-15T00:00:00+00:00'


def reseed_simuls(database):
    from app.migrations import _seed_simuls
    from app.models.simul import SimulShow

    if SimulShow.query.filter_by(created_at=RESEED_STAMP).first() is not None:
        return
    statuses = database.session.execute(database.text('DELETE FROM simul_status')).rowcount
    shows = database.session.execute(database.text('DELETE FROM simul_show')).rowcount
    database.session.expire_all()
    logger.info('Simul reseed: deleted %d shows and %d statuses', shows, statuses)
    _seed_simuls(database)
    database.session.flush()
    database.session.execute(database.text('UPDATE simul_show SET created_at = :s'), {'s': RESEED_STAMP})
