"""One-off: bring production simuls in line with the corrected import of the live sheet
(app/data/simul_seed.json) without wiping in-app edits. Every step only touches rows still in
their original imported state. Remove this module and its call once it has run in production."""
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

NON_SHOW_ROWS = (('completed', 2024, 'COMPLETED AFTER THE END OF YEAR VIDEO'),
                 ('completed', 2025, 'See end of Completed 2024 for EOY video'))
ADDED_SHOWS = (('completed', 2026, 'Host (2020)'),)


def apply_simul_sheet_fixes(database):
    from app.models.simul import SimulShow, SimulStatus, SimulStatusType
    from app.models.user import User

    types = {t.key: t.id for t in SimulStatusType.query.all()}
    if not {'interested', 'not_interested', 'other', 'watched'} <= set(types):
        return
    with open(os.path.join(os.path.dirname(__file__), 'data', 'simul_seed.json'), encoding='utf-8') as fh:
        seed = json.load(fh)['shows']
    user_ids = {u.username.lower(): u.id for u in User.query.all()}
    now = datetime.now(timezone.utc).isoformat()
    changes = []

    # Planning: red cells were imported as 'Not interested'; the seed now has the right status.
    planning = {(s.title, s.sort_order): s.id for s in SimulShow.query.filter_by(bucket='planning').all()}
    flipped = 0
    for s in seed:
        show_id = planning.get((s['title'], s['sort_order'])) if s['bucket'] == 'planning' else None
        if show_id is None:
            continue
        for st in s['statuses']:
            uid = user_ids.get((st['user'] or '').lower())
            if uid is None or st['status_key'] == 'not_interested':
                continue
            flipped += SimulStatus.query.filter_by(
                show_id=show_id, user_id=uid, status_type_id=types['not_interested']
            ).update({'status_type_id': types[st['status_key']]})
    if flipped:
        changes.append('%d planning statuses corrected' % flipped)

    # Section labels that were imported as shows.
    for bucket, year, title in NON_SHOW_ROWS:
        for show in SimulShow.query.filter_by(bucket=bucket, year=year, title=title).all():
            database.session.delete(show)
            changes.append('removed "%s"' % title)

    # Shows added to the sheet after the import.
    for bucket, year, title in ADDED_SHOWS:
        if SimulShow.query.filter_by(bucket=bucket, year=year, title=title).first():
            continue
        s = next((x for x in seed if (x['bucket'], x['year'], x['title']) == (bucket, year, title)), None)
        if s is None:
            continue
        last = database.session.query(database.func.max(SimulShow.sort_order)).filter_by(
            bucket=bucket, year=year).scalar() or 0
        show = SimulShow(title=title, category=s['category'], bucket=bucket, year=year, url=s.get('url'),
                         notes=s.get('notes'), sort_order=last + 1, created_at=now, last_updated=now)
        for st in s['statuses']:
            uid = user_ids.get((st['user'] or '').lower())
            if uid is not None and st['status_key'] in types:
                show.statuses.append(SimulStatus(user_id=uid, status_type_id=types[st['status_key']],
                                                 note=st['note']))
        database.session.add(show)
        changes.append('added "%s"' % title)
    database.session.flush()

    # Yellow-titled shows on the Ongoing/Paused tabs are paused.
    for s in seed:
        if s['bucket'] != 'paused':
            continue
        n = SimulShow.query.filter_by(bucket='ongoing', year=s['year'], title=s['title']).update(
            {'bucket': 'paused', 'last_updated': now})
        if n:
            changes.append('paused "%s" (%s)' % (s['title'], s['year']))

    # Amy and Syd have no accounts; their watches become a note on the title.
    for s in seed:
        line = next((l for l in (s.get('notes') or '').split('\n') if l.startswith('Also watched by ')), None)
        if not line:
            continue
        show = SimulShow.query.filter_by(bucket=s['bucket'], year=s['year'], title=s['title']).order_by(
            SimulShow.sort_order, SimulShow.id).first()
        if show is None or line in (show.notes or ''):
            continue
        show.notes = '\n'.join(filter(None, [show.notes, line]))
        show.last_updated = now
        changes.append('noted "%s" on "%s"' % (line, s['title']))

    if changes:
        logger.info('Simul sheet fixes: %s', '; '.join(changes))
