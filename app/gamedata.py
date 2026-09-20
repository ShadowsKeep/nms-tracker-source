"""
In-memory No Man's Sky game data with the indexes the tracker needs.

Loaded once from app/data/gamedata.json (built by tools/build_data.py).
"""
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

KIND_LABELS = {
    'raw': 'Raw Material', 'product': 'Product', 'curiosity': 'Curiosity', 'trade': 'Trade Item',
    'tech': 'Technology', 'upgrade': 'Upgrade Module', 'food': 'Food', 'other': 'Other',
}
STATION_LABELS = {'refiner': 'Refiner', 'cooking': 'Nutrient Processor'}


def _data_file(name='gamedata.json') -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'app' / 'data' / name  # type: ignore[attr-defined]
    return Path(__file__).parent / 'data' / name


# words in a wiki "Sources" note that mean you can simply pay for the thing
_BUY_WORDS = ('trade terminal', 'purchas', 'bought', 'buy ', 'for sale', 'sold ')


def _wiki_notes() -> dict:
    """Where-to-find notes from the NMS wiki (tools/build_wiki.py). Optional file."""
    try:
        return json.loads(_data_file('wiki.json').read_text(encoding='utf-8'))['items']
    except (OSError, ValueError, KeyError):
        return {}


class GameData:
    def __init__(self, raw: dict):
        self.items = {i['id']: i for i in raw['items']}
        self.recipes = raw['recipes']
        self.made_by = defaultdict(list)      # item id -> recipes that OUTPUT it
        self.used_in = defaultdict(list)      # item id -> recipes that take it as INPUT
        self.crafts_into = defaultdict(list)  # item id -> items whose blueprint REQUIRES it
        for r in self.recipes:
            self.made_by[r['output']['id']].append(r)
            for inp in r['inputs']:
                self.used_in[inp['id']].append(r)
        for it in self.items.values():
            for req in it['requires']:
                self.crafts_into[req['id']].append(it)
        notes = _wiki_notes()
        for it in self.items.values():
            it['kind_label'] = KIND_LABELS.get(it['kind'], it['kind'])
            wiki = it['wiki'] = notes.get(it['id'])
            # "hard to find": the wiki calls it rare, or it can only be found (not bought or made)
            text = ' '.join(s['text'] for s in wiki['sources']).lower() if wiki else ''
            makeable = bool(it['requires'] or self.made_by.get(it['id']))
            it['hard'] = bool(wiki) and not makeable and wiki['rarity'] != 'Common' and (wiki['rarity'] == 'Rare' or (
                bool(text) and not any(w in text for w in _BUY_WORDS)))
            it['search'] = (it['name'] + ' ' + it['group']).lower()
        # game id (as written in save files) -> item; materials win over lookalike entries
        rank = {'raw': 0, 'product': 1, 'trade': 2, 'curiosity': 3, 'tech': 4}
        self.by_game_id = {}
        for it in sorted(self.items.values(), key=lambda i: rank.get(i['kind'], 9)):
            if it.get('gid'):
                self.by_game_id.setdefault(it['gid'], it)
        self.ship_parts = sorted((i for i in self.items.values() if i['ship_part']),
                                 key=lambda i: (i['group'] != 'Damaged Starship Component', i['name']))

    # ── lookups ────────────────────────────────────────────────────────────
    def get(self, item_id):
        return self.items.get(item_id)

    def name(self, item_id):
        it = self.items.get(item_id)
        return it['name'] if it else item_id

    def search(self, q='', kinds=None, limit=60, ship_only=False):
        q = (q or '').strip().lower()
        words = q.split()
        pool = self.ship_parts if ship_only else self.items.values()
        out = []
        for it in pool:
            if kinds and it['kind'] not in kinds:
                continue
            if words and not all(w in it['search'] for w in words):
                continue
            out.append(it)
        # exact / prefix matches first, then raw materials and products, then the rest
        rank = {'raw': 0, 'product': 1, 'tech': 2, 'trade': 3, 'curiosity': 4}
        out.sort(key=lambda i: (not i['name'].lower().startswith(q) if q else False,
                                rank.get(i['kind'], 9), i['name']))
        return out[:limit]

    def recipe_view(self, r):
        """Recipe with names resolved, for templates."""
        return {
            'station': STATION_LABELS.get(r['station'], r['station']),
            'op': r['op'],
            'time': r['time'],
            'inputs': [dict(item=self.items[i['id']], qty=i['qty']) for i in r['inputs']],
            'output': dict(item=self.items[r['output']['id']], qty=r['output']['qty']),
        }

    # ── requirement maths ──────────────────────────────────────────────────
    def direct_requirements(self, item_id, qty):
        """What building `qty` of an item needs. A plain material just needs itself."""
        it = self.items.get(item_id)
        if not it:
            return []
        if it['requires']:
            return [(r['id'], r['qty'] * qty) for r in it['requires']]
        return [(item_id, qty)]

    def expand(self, lines, stock, raw_mode):
        """
        lines: iterable of (item_id, qty, source_label)
        stock: {item_id: have}
        Returns (needs, from_stock):
          needs      {item_id: {'qty': int, 'sources': set()}}  things to go and get
          from_stock {item_id: int}  crafted parts already in the inventory that were used
        Each line is the top-level thing wanted (a goal item or a broken component). It is
        broken into its ingredients after first using up any you already own. In raw mode
        crafted ingredients are broken down further, again using owned stock first.
        """
        needs = defaultdict(lambda: {'qty': 0, 'sources': set()})
        from_stock = defaultdict(int)
        pool = dict(stock)

        def walk(item_id, qty, source, depth):
            it = self.items.get(item_id)
            if not it or qty <= 0:
                return
            # The top-level thing (a goal or a broken part) always breaks into its ingredients;
            # deeper crafted parts only break down in raw mode.
            if it['requires'] and depth < 8 and (depth == 0 or raw_mode):
                used = min(pool.get(item_id, 0), qty)
                if used:
                    pool[item_id] -= used
                    from_stock[item_id] += used
                    qty -= used
                for req in it['requires']:
                    walk(req['id'], req['qty'] * qty, source, depth + 1)
                return
            needs[item_id]['qty'] += qty
            needs[item_id]['sources'].add(source)

        for item_id, qty, source in lines:
            walk(item_id, qty, source, 0)
        return needs, from_stock


@lru_cache(maxsize=1)
def game() -> GameData:
    return GameData(json.loads(_data_file().read_text(encoding='utf-8')))
