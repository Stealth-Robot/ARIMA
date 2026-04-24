"""Import song-level notes from notes_export.json into Song.note fields.

Usage:
    flask import-notes

Reads spreadsheet/notes_export.json (produced by flask export-notes) and sets
Song.note for matching songs. Skips songs that already have a note in the app.
"""

import json
import os

from app.extensions import db
from app.models.music import Artist, Song, ArtistSong

INPUT_PATH = os.path.join('spreadsheet', 'notes_export.json')


def _build_song_lookup():
    """Build (artist_id, song_name) -> song_id lookup."""
    lookup = {}
    for a_s in ArtistSong.query.filter_by(artist_is_main=True).all():
        song = db.session.get(Song, a_s.song_id)
        if song:
            lookup[(a_s.artist_id, song.name)] = song.id
    return lookup


def _build_artist_map():
    """Build artist_name -> artist_id lookup."""
    return {a.name: a.id for a in Artist.query.all()}


def import_notes():
    """Import song-level notes from JSON into Song.note fields."""
    if not os.path.exists(INPUT_PATH):
        print(f'ERROR: {INPUT_PATH} not found. Run "flask export-notes" first.')
        return

    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print('=== IMPORT SONG NOTES ===')

    artist_map = _build_artist_map()
    song_lookup = _build_song_lookup()

    imported = 0
    skipped_has_note = 0
    skipped_not_found = 0

    for genre, entries in data.items():
        print(f'\n[{genre.upper()}] {len(entries)} notes to process')
        genre_imported = 0

        for entry in entries:
            tab_name = entry['artist_tab']
            song_name = entry['song']
            note_text = entry['note']

            # Try (artist_id, song_name) first
            song_id = None
            artist_id = artist_map.get(tab_name)
            if artist_id:
                song_id = song_lookup.get((artist_id, song_name))

            # Fallback: direct name lookup
            if not song_id:
                song = Song.query.filter_by(name=song_name).first()
                if song:
                    song_id = song.id

            if not song_id:
                skipped_not_found += 1
                continue

            song = db.session.get(Song, song_id)
            if song.note:
                skipped_has_note += 1
                continue

            song.note = note_text
            genre_imported += 1
            imported += 1

        db.session.commit()
        print(f'  Imported: {genre_imported}')

    print(f'\n=== IMPORT COMPLETE ===')
    print(f'  Notes imported:                  {imported}')
    print(f'  Notes skipped (already has note): {skipped_has_note}')
    print(f'  Notes skipped (song not found):   {skipped_not_found}')
