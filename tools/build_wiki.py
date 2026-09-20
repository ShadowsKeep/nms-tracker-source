"""
Fetch "where do I find this?" notes from the No Man's Sky Wiki into app/data/wiki.json.

    python tools/build_wiki.py

Source: https://nomanssky.fandom.com (community wiki, text licensed CC BY-SA 3.0). For every
material, product, curiosity and trade item in gamedata.json it reads the page's infobox rarity
and its "Sources" section through the MediaWiki API (50 pages per request, about 15 requests).
The app shows the text with a link back to the page, which is the attribution the licence asks for.
Run it after build_data.py; the app works without the file, it just has no location notes.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMEDATA = ROOT / 'app' / 'data' / 'gamedata.json'
OUT = ROOT / 'app' / 'data' / 'wiki.json'
API = 'https://nomanssky.fandom.com/api.php'
PAGE = 'https://nomanssky.fandom.com/wiki/'
AGENT = 'NMSTracker/1.0 (Shadowskeep LLC; personal companion app; build-time fetch)'
KINDS = {'raw', 'product', 'curiosity', 'trade'}
SECTION_NAMES = ('sources', 'source', 'acquisition', 'obtaining', 'how to obtain', 'location', 'locations')
MAX_LINES, MAX_CHARS = 8, 420


def fetch(titles):
    query = urllib.parse.urlencode({
        'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
        'redirects': 1, 'format': 'json', 'formatversion': 2, 'titles': '|'.join(titles)})
    req = urllib.request.Request(f'{API}?{query}', headers={'User-Agent': AGENT})
    with urllib.request.urlopen(req, timeout=40) as res:
        return json.loads(res.read())['query']


def plain(text: str) -> str:
    """Wikitext -> readable text."""
    text = re.sub(r'<ref[^>]*?/>|<ref.*?</ref>', '', text, flags=re.S)
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\[(?:File|Image|Category):[^\]]*\]\]', '', text, flags=re.I)
    text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text)            # [[Page|label]] -> label
    text = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', text)               # [url label] -> label
    for _ in range(3):                                                        # {{tpl|text}} -> text
        text = re.sub(r'\{\{[^{}|]*\|([^{}|]*)(?:\|[^{}]*)?\}\}', r'\1', text)
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    text = text.replace("'''", '').replace("''", '')
    return re.sub(r'\s+', ' ', text).strip()


def sources(wikitext: str):
    lines = []
    for m in re.finditer(r'^==\s*([^=].*?)\s*==\s*$', wikitext, flags=re.M):
        if m.group(1).strip().lower() not in SECTION_NAMES:
            continue
        rest = wikitext[m.end():]
        end = re.search(r'^==[^=]', rest, flags=re.M)
        body = rest[:end.start()] if end else rest
        for _ in range(4):                                     # drop templates that span lines (recipe tables)
            body = re.sub(r'\{\{[^{}]*\n[^{}]*\}\}', '', body)
        for raw in body.splitlines():
            raw = raw.strip()
            if not raw or raw.startswith(('{|', '|', '!', '<gallery', '=', '{{', '}}')):
                continue                                       # tables, sub-headings, galleries
            depth = len(raw) - len(raw.lstrip('*#:'))
            text = plain(raw.lstrip('*#: '))
            if len(text) > 3:
                lines.append({'text': text[:MAX_CHARS], 'sub': depth > 1})
        break
    return lines[:MAX_LINES]


def rarity(wikitext: str) -> str:
    m = re.search(r'^\|\s*rarity\s*=\s*([^\n|}]+)', wikitext, flags=re.M | re.I)
    return plain(m.group(1)).title() if m else ''


def main():
    items = [i for i in json.loads(GAMEDATA.read_text(encoding='utf-8'))['items']
             if i['kind'] in KINDS and not i.get('obsolete')]
    by_name = {}
    for it in items:
        by_name.setdefault(it['name'], []).append(it['id'])
    names = sorted(by_name)
    out, missing = {}, []
    for start in range(0, len(names), 50):
        batch = names[start:start + 50]
        data = fetch(batch)
        # the API reports how it renamed each requested title; follow that chain back to ours
        back = {n: n for n in batch}
        for step in ('normalized', 'redirects'):
            for r in data.get(step, []):
                if r['from'] in back:
                    back[r['to']] = back[r['from']]
        for page in data.get('pages', []):
            name = back.get(page['title'])
            if not name or page.get('missing'):
                continue
            text = page['revisions'][0]['slots']['main']['content']
            if 'infobox' not in text.lower():
                continue                                       # disambiguation or unrelated page
            entry = {'rarity': rarity(text), 'sources': sources(text),
                     'url': PAGE + urllib.parse.quote(page['title'].replace(' ', '_'))}
            if entry['rarity'] or entry['sources']:
                for item_id in by_name[name]:
                    out[item_id] = entry
        print(f'{min(start + 50, len(names))}/{len(names)} looked up, {len(out)} with notes')
        time.sleep(1)                                          # be polite to the wiki
    missing = [n for n in names if not any(i in out for i in by_name[n])]
    OUT.write_text(json.dumps({'licence': 'CC BY-SA 3.0', 'source': 'https://nomanssky.fandom.com',
                               'items': out}, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f'wrote {OUT} ({len(out)} items, {OUT.stat().st_size // 1024} KB); no notes for {len(missing)}')


if __name__ == '__main__':
    main()
