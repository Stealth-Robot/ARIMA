"""Convert the Lettuce Simuls xlsx export into app/data/simul_seed.json.

Usage: python scripts/simul_xlsx_to_seed.py <path/to/Lettuce Simuls.xlsx>

Does not touch the database; the startup migration imports the JSON.
"""
import json
import os
import re
import sys

import openpyxl

SEED_PATH = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'simul_seed.json')
TYPES_PATH = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'simul_types.json')

STATUS_TYPES = [
    {'key': 'watched', 'label': 'Watched', 'color_hex': '#4a7c59', 'applies_to': 'watch', 'sort_order': 1},
    {'key': 'interested', 'label': 'Interested', 'color_hex': '#4a6f9c', 'applies_to': 'planning', 'sort_order': 2},
    {'key': 'not_interested', 'label': 'Not interested', 'color_hex': '#8a4a4a', 'applies_to': 'planning', 'sort_order': 3},
    {'key': 'other', 'label': 'Other', 'color_hex': '#6f5d94', 'applies_to': 'both', 'sort_order': 4},
]

# Planning title fills, per the sheet's own legend in L1:M2.
CATEGORY_BY_FILL = {
    'FFD9D2E9': 'tv',
    'FFFCE5CD': 'movie',
    'FFB6D7A8': 'tv',  # "upcoming seasonal"
    'theme9': 'movie',  # "upcoming movie"
}
UPCOMING_FILLS = {'FFB6D7A8', 'theme9'}
# Watch sheets reuse only the TV/movie fills; other title highlights there carry no category.
WATCH_CATEGORY_BY_FILL = {'FFD9D2E9': 'tv', 'FFFCE5CD': 'movie'}
NO_STATUS_FILLS = {None, 'FFFFFFFF'}
PLANNING_INTERESTED_FILL = 'FFEA9999'
WATCHED_FILLS = {'FFFF0000', 'FFE06666'}
WATCH_SHEET_RE = re.compile(r'^(OngoingPaused|Completed|Dropped) (\d{4})$')
BUCKET_BY_PREFIX = {'OngoingPaused': 'ongoing', 'Completed': 'completed', 'Dropped': 'dropped'}
# On the OngoingPaused tabs a pale yellow title marks a paused show.
PAUSED_TITLE_FILL = 'FFFFE599'
# No accounts in ARIMA, so their watches are kept as a note on the title instead.
HISTORICAL_MEMBERS = {'Amy', 'Syd'}
# Section labels in the title column, not shows.
NON_SHOW_ROWS = {'COMPLETED AFTER THE END OF YEAR VIDEO', 'See end of Completed 2024 for EOY video'}


def historical_note(names):
    return 'Also watched by ' + ' and '.join(names)


def fill_of(cell):
    if not (cell.fill and cell.fill.fill_type):
        return None
    fg = cell.fill.fgColor
    if fg.type == 'rgb':
        return fg.rgb
    if fg.type == 'theme':
        return 'theme%s' % fg.theme
    return None


def text(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def comment_of(cell):
    return text(cell.comment.text) if cell.comment else None


def status_for(cell, planning):
    """Return (status_key, note, video_url) for one participant cell, or None when blank."""
    fill = fill_of(cell)
    value = text(cell.value)
    note_parts = []
    youtube = None
    is_not_interested = False
    written = False
    if value:
        if 'youtube.com' in value or 'youtu.be' in value:
            youtube = value
        elif value.lower() == 'not interested':
            is_not_interested = True
        else:
            note_parts.append(value)
            written = True
    if comment_of(cell):
        note_parts.append(comment_of(cell))
    note = '\n'.join(note_parts) or None

    if planning:
        # Red marks interest ("Who's Interested?"), but "Not Interested" text decides even under red; red with other writing is unclear.
        if is_not_interested:
            key = 'not_interested'
        elif fill == PLANNING_INTERESTED_FILL:
            key = 'other' if written else 'interested'
        elif fill not in NO_STATUS_FILLS or note:
            key = 'other'
        else:
            key = None
    else:
        if is_not_interested:
            key = 'not_interested'
        elif fill in WATCHED_FILLS:
            key = 'watched'
        elif fill not in NO_STATUS_FILLS or note:
            key = 'other'
        else:
            key = None
    if key is None:
        return None if youtube is None else (None, None, youtube)
    return key, note, youtube


def convert(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    shows = []
    for ws in wb.worksheets:
        if ws.title == 'Simul Planning':
            planning, bucket, year, header_row = True, 'planning', None, 2
        else:
            m = WATCH_SHEET_RE.match(ws.title)
            if not m:
                print('Skipping unrecognised sheet %r' % ws.title, file=sys.stderr)
                continue
            planning, bucket, year, header_row = False, BUCKET_BY_PREFIX[m.group(1)], int(m.group(2)), 1

        members = {}
        for c in ws[header_row][1:]:
            name = text(c.value)
            if not name or name.isupper():
                break  # planning's category legend starts after the member columns
            members[c.column] = name
        extra_col = max(members) + 1

        for row in ws.iter_rows(min_row=header_row + 1):
            title = text(row[0].value)
            if not title or title in NON_SHOW_ROWS:
                continue
            title_fill = fill_of(row[0])
            show = {
                'title': title,
                'category': (CATEGORY_BY_FILL if planning else WATCH_CATEGORY_BY_FILL).get(
                    title_fill, 'uncategorized'),
                'upcoming': planning and title_fill in UPCOMING_FILLS,
                'bucket': 'paused' if bucket == 'ongoing' and title_fill == PAUSED_TITLE_FILL else bucket,
                'year': year,
                'url': text(row[0].hyperlink.target) if row[0].hyperlink else None,
                'notes': comment_of(row[0]),
                'years_running': None if planning else text(row[extra_col - 1].value) if len(row) >= extra_col else None,
                'sort_order': len(shows) + 1,
                'statuses': [],
            }
            # Watch tabs colour each separate watch differently; red is the main one.
            groups = {'main': show['statuses']}
            historical = []
            for cell in row[1:]:
                name = members.get(cell.column)
                if not name:
                    continue
                result = status_for(cell, planning)
                if result is None:
                    continue
                key, note, youtube = result
                if youtube:
                    show['notes'] = '\n'.join(filter(None, [show['notes'], youtube]))  # video links live in the title note
                if key is None:
                    continue
                if name in HISTORICAL_MEMBERS:
                    historical.append(name)
                    continue
                group = 'main'
                fill = fill_of(cell)
                if not planning and key == 'other' and fill not in NO_STATUS_FILLS:
                    group, key = fill, 'watched'
                groups.setdefault(group, []).append({
                    'user': name,
                    'member_name': None,
                    'status_key': key,
                    'note': note,
                })
            if historical:
                show['notes'] = '\n'.join(filter(None, [show['notes'], historical_note(historical)]))
            colour_groups = [g for k, g in groups.items() if k != 'main']
            if colour_groups and not show['statuses']:
                # No red watch on this row: the first colour becomes its main row.
                show['statuses'] = colour_groups.pop(0)
            shows.append(show)
            for statuses in colour_groups:
                shows.append({
                    'title': title, 'category': show['category'], 'upcoming': show['upcoming'], 'bucket': show['bucket'], 'year': year,
                    'url': show['url'], 'notes': None, 'years_running': None,
                    'sort_order': len(shows) + 1, 'statuses': statuses,
                })
    # The sheet only types planning titles; looked-up types (scripts/simul_fill_types.py) fill the rest.
    if os.path.exists(TYPES_PATH):
        types = json.load(open(TYPES_PATH, encoding='utf-8'))
        for s in shows:
            if s['category'] == 'uncategorized':
                s['category'] = (types['by_url'].get(s['url']) if s['url'] else types['by_title'].get(s['title'])) \
                    or 'uncategorized'
    return {'status_types': STATUS_TYPES, 'shows': shows}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = convert(sys.argv[1])
    with open(SEED_PATH, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print('Wrote %d shows to %s' % (len(data['shows']), os.path.normpath(SEED_PATH)))


if __name__ == '__main__':
    main()
