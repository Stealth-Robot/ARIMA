"""One-off: give uncategorized simuls the TV/movie type looked up in app/data/simul_types.json.
Only rows still uncategorized are touched. Remove this module and its call once it has run in production."""
import json
import logging
import os

logger = logging.getLogger(__name__)


def fill_simul_types(database):
    from app.models.simul import SimulShow

    path = os.path.join(os.path.dirname(__file__), 'data', 'simul_types.json')
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as fh:
        types = json.load(fh)
    filled = 0
    for show in SimulShow.query.filter_by(category='uncategorized').all():
        cat = types['by_url'].get(show.url) if show.url else types['by_title'].get(show.title.strip())
        if cat and cat != 'uncategorized':
            show.category = cat
            filled += 1
    if filled:
        logger.info('Filled in the type of %d simul shows', filled)
