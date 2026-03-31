"""Export all data from the lettuce kpop spreadsheet to JSON.

Usage:
    python scripts/export_spreadsheet.py "lettuce kpop.xlsx" --output data.json
"""

import argparse
import json
import re
import sys

import openpyxl

NON_DATA_SHEETS = {
    'Changelog', 'RULES', 'STATS', 'STATS 2.0', 'TEMPLATE', 'DIRECTORY',
}
MISC_ARTISTS_SHEET = 'Misc. Artists'

# Columns B-L (index 1-11 in 0-based) are user ratings
USER_COL_START = 1   # column B
USER_COL_END = 11    # column L (inclusive)
S_FLAG_COL = 15      # column P (0-based)


def parse_args():
    parser = argparse.ArgumentParser(description='Export spreadsheet to JSON')
    parser.add_argument('spreadsheet', help='Path to .xlsx file')
    parser.add_argument('--output', '-o', default='data.json', help='Output JSON file')
    return parser.parse_args()


def extract_users(ws):
    """Extract user list from header row of any artist sheet."""
    users = []
    header = [cell.value for cell in ws[1]]
    for i in range(USER_COL_START, USER_COL_END + 1):
        name = header[i]
        if name is None:
            continue
        is_locked = name.startswith('🔒')
        clean_name = name.replace('🔒', '').strip()
        users.append({
            'username': clean_name,
            'sort_order': len(users) + 1,
            'is_locked': is_locked,
        })
    return users


def parse_album_header(text):
    """Parse 'Album Name (Year)' → (name, year)."""
    if not text:
        return text, None
    match = re.match(r'^(.+?)\s*\((\d{4})\)\s*$', text.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return text.strip(), None


def extract_ratings(ws, row_idx, users):
    """Extract ratings for a song row. Returns dict of username→rating."""
    ratings = {}
    for i, user in enumerate(users):
        col = USER_COL_START + i + 1  # openpyxl is 1-based
        value = ws.cell(row=row_idx, column=col).value
        if value is not None:
            try:
                r = int(round(float(value)))
                if 0 <= r <= 5:
                    ratings[user['username']] = r
            except (ValueError, TypeError):
                pass
    return ratings


def extract_artist(ws, artist_name, users):
    """Extract albums and songs from an artist sheet."""
    albums = []
    current_album = None
    track_num = 0

    for row_idx in range(2, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=1).value
        if name is None or str(name).strip() == '':
            continue

        s_flag = ws.cell(row=row_idx, column=S_FLAG_COL + 1).value

        if s_flag is False or s_flag == 'False':
            # Album header row
            album_name, year = parse_album_header(str(name))
            current_album = {
                'name': album_name,
                'year': year,
                'songs': [],
            }
            albums.append(current_album)
            track_num = 0
        elif s_flag is True or s_flag == 'True':
            # Song row
            track_num += 1
            ratings = extract_ratings(ws, row_idx, users)
            song = {
                'name': str(name).strip(),
                'track_number': track_num,
                'ratings': ratings,
            }
            if current_album is not None:
                current_album['songs'].append(song)
            else:
                # Song without album — create a default album
                current_album = {
                    'name': f'{artist_name} - Singles',
                    'year': None,
                    'songs': [song],
                }
                albums.append(current_album)

    # Filter out empty albums (subunit/member headers with no songs)
    return [a for a in albums if a['songs']]


def extract_misc_artists(ws, users):
    """Extract songs from Misc. Artists sheet. Each song has artist in parens."""
    entries = []
    for row_idx in range(2, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=1).value
        if name is None or str(name).strip() == '':
            continue

        s_flag = ws.cell(row=row_idx, column=S_FLAG_COL + 1).value
        if s_flag is not True and s_flag != 'True':
            continue

        text = str(name).strip()
        # Split on last '(' to get "Song Name (Artist Name)"
        match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', text)
        if match:
            song_name = match.group(1).strip()
            artist_name = match.group(2).strip()
        else:
            song_name = text
            artist_name = 'Unknown'

        ratings = extract_ratings(ws, row_idx, users)
        entries.append({
            'song_name': song_name,
            'artist_name': artist_name,
            'ratings': ratings,
        })

    return entries


def extract_changelog(ws):
    """Extract changelog entries."""
    entries = []
    for row_idx in range(2, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=1).value
        desc = ws.cell(row=row_idx, column=2).value
        date = ws.cell(row=row_idx, column=3).value

        if desc is None:
            continue

        date_str = None
        if date:
            if hasattr(date, 'strftime'):
                date_str = date.strftime('%Y-%m-%d')
            else:
                date_str = str(date)[:10]

        entries.append({
            'user': str(name).strip() if name else None,
            'description': str(desc).strip(),
            'date': date_str,
        })

    return entries


def main():
    args = parse_args()

    print(f'Loading {args.spreadsheet}...')
    wb = openpyxl.load_workbook(args.spreadsheet, data_only=True)
    print(f'  {len(wb.sheetnames)} sheets found')

    # Get users from first artist sheet
    artist_sheet_names = [
        name for name in wb.sheetnames
        if name not in NON_DATA_SHEETS and name != MISC_ARTISTS_SHEET
    ]

    if not artist_sheet_names:
        print('ERROR: No artist sheets found')
        sys.exit(1)

    users = extract_users(wb[artist_sheet_names[0]])
    print(f'  {len(users)} users: {[u["username"] for u in users]}')

    # Extract artists
    artists = []
    total_songs = 0
    total_albums = 0
    total_ratings = 0

    for sheet_name in artist_sheet_names:
        ws = wb[sheet_name]
        albums = extract_artist(ws, sheet_name, users)
        song_count = sum(len(a['songs']) for a in albums)
        rating_count = sum(
            len(s['ratings']) for a in albums for s in a['songs']
        )

        if albums:
            artists.append({
                'name': sheet_name,
                'albums': albums,
            })
            total_albums += len(albums)
            total_songs += song_count
            total_ratings += rating_count

        if len(artists) % 50 == 0 and len(artists) > 0:
            print(f'  Processed {len(artists)} artists...')

    print(f'  {len(artists)} artists, {total_albums} albums, {total_songs} songs, {total_ratings} ratings')

    # Extract Misc. Artists
    misc_entries = []
    if MISC_ARTISTS_SHEET in wb.sheetnames:
        misc_entries = extract_misc_artists(wb[MISC_ARTISTS_SHEET], users)
        print(f'  {len(misc_entries)} misc artist songs')

    # Extract Changelog
    changelog = []
    if 'Changelog' in wb.sheetnames:
        changelog = extract_changelog(wb['Changelog'])
        print(f'  {len(changelog)} changelog entries')

    # Build output
    data = {
        'users': users,
        'artists': artists,
        'misc_artists': misc_entries,
        'changelog': changelog,
    }

    # Write JSON
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f'\nExported to {args.output}')
    print(f'  Artists: {len(artists)}')
    print(f'  Albums: {total_albums}')
    print(f'  Songs: {total_songs}')
    print(f'  Ratings: {total_ratings}')
    print(f'  Misc songs: {len(misc_entries)}')
    print(f'  Changelog: {len(changelog)}')


if __name__ == '__main__':
    main()
