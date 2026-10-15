"""Work out TV/movie for simul titles the sheet leaves uncategorized and write app/data/simul_types.json.

Usage: python scripts/simul_fill_types.py   (reads app/data/simul_seed.json; needs network)

Sources, in order: the title's link (Letterboxd = movie, MyDramaList/Serializd = TV, AniList and
IMDb formats looked up), the same title typed elsewhere in the sheet, then an exact-name AniList
search for unlinked titles. Anything that is not plainly TV or a movie stays uncategorized.
"""
import json
import os
import re
import time
import urllib.request
from urllib.parse import urlparse

ROOT = os.path.join(os.path.dirname(__file__), '..', 'app', 'data')
SEED_PATH = os.path.join(ROOT, 'simul_seed.json')
OUT_PATH = os.path.join(ROOT, 'simul_types.json')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

ANILIST_FORMATS = {'TV': 'tv', 'TV_SHORT': 'tv', 'ONA': 'tv', 'MOVIE': 'movie'}
IMDB_TYPES = {'movie': 'movie', 'tvMovie': 'movie', 'tvSeries': 'tv', 'tvMiniSeries': 'tv'}


def post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                          'User-Agent': UA})
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get('Retry-After', 60)) + 1)
                continue
            raise
        except (urllib.error.URLError, ConnectionError):
            time.sleep(5)  # AniList occasionally drops the connection mid-run
    raise RuntimeError('AniList request kept failing')


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    return json.load(urllib.request.urlopen(req, timeout=30))


def anilist_formats(ids):
    out = {}
    ids = sorted(set(ids))
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        query = '{' + ' '.join('m%d: Media(id: %d, type: ANIME) { id format }' % (n, n) for n in chunk) + '}'
        data = post_json('https://graphql.anilist.co', {'query': query}).get('data') or {}
        for v in data.values():
            if v:
                out[v['id']] = v['format']
        time.sleep(1)
    return out


def anilist_search(title):
    query = ('query ($s: String) { Page(perPage: 5) { media(search: $s, type: ANIME) '
             '{ format title { romaji english native } synonyms } } }')
    media = post_json('https://graphql.anilist.co', {'query': query, 'variables': {'s': title}})['data']['Page']['media']
    want = title.strip().casefold()
    for m in media:
        names = [m['title'].get('romaji'), m['title'].get('english'), m['title'].get('native')] + (m['synonyms'] or [])
        if any(n and n.strip().casefold() == want for n in names):
            return m['format']
    return None


def imdb_type(tt):
    data = get_json('https://v3.sg.media-imdb.com/suggestion/t/%s.json' % tt)
    for d in data.get('d', []):
        if d.get('id') == tt:
            return d.get('qid')
    return None


def main():
    shows = json.load(open(SEED_PATH, encoding='utf-8'))['shows']
    typed = {}
    for s in shows:
        if s['category'] != 'uncategorized':
            typed.setdefault(s['title'].strip().casefold(), set()).add(s['category'])
    todo = [s for s in shows if s['category'] == 'uncategorized']

    anilist_ids = {}
    for s in todo:
        m = re.match(r'https?://anilist\.co/anime/(\d+)', s['url'] or '')
        if m:
            anilist_ids[s['url']] = int(m.group(1))
    formats = anilist_formats(anilist_ids.values())

    by_url, by_title, report = {}, {}, []
    for s in todo:
        url, title = s['url'], s['title'].strip()
        host = urlparse(url).netloc if url else ''
        cat, source = None, None
        if host == 'letterboxd.com':
            cat, source = 'movie', 'letterboxd'
        elif host in ('mydramalist.com', 'www.serializd.com'):
            cat, source = 'tv', host
        elif url in anilist_ids:
            fmt = formats.get(anilist_ids[url])
            cat, source = ANILIST_FORMATS.get(fmt, 'uncategorized'), 'anilist %s' % fmt
        elif host == 'www.imdb.com':
            m = re.search(r'(tt\d+)', url)
            qid = imdb_type(m.group(1)) if m else None
            cat, source = IMDB_TYPES.get(qid, 'uncategorized'), 'imdb %s' % qid
            time.sleep(0.2)
        if cat is None:
            t = typed.get(title.casefold())
            if t and len(t) == 1:
                cat, source = next(iter(t)), 'same title in sheet'
        if cat is None and not url:
            fmt = anilist_search(title)
            time.sleep(0.8)
            if fmt:
                cat, source = ANILIST_FORMATS.get(fmt, 'uncategorized'), 'anilist name match %s' % fmt
        report.append((s['bucket'], s['year'], title, cat or 'unresolved', source or ''))
        if cat:
            (by_url if url else by_title)[url or title] = cat

    with open(OUT_PATH, 'w', encoding='utf-8') as fh:
        json.dump({'by_url': by_url, 'by_title': by_title}, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write('\n')
    for r in report:
        print('%s|%s|%s|%s|%s' % r)


if __name__ == '__main__':
    main()
