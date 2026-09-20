"""
Compile source-data/*.lang.json into app/data/gamedata.json.

Source: the open-source "Assistant for No Man's Sky" app (github.com/AssistantNMS/App,
GPL-3.0), whose JSON is extracted from the game files. Refresh it with:

    python tools/build_data.py --download

Only the fields the tracker needs are kept, so the app loads one ~1 MB file.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'source-data'
OUT = ROOT / 'app' / 'data' / 'gamedata.json'
BASE_URL = 'https://raw.githubusercontent.com/AssistantNMS/App/main/assets/json/en/'
DEV_URL = 'https://raw.githubusercontent.com/AssistantNMS/App/main/assets/data/developerDetails.json'
MAPPING_API = 'https://api.github.com/repos/monkeyman192/MBINCompiler/releases/latest'

# file stem -> kind label used by the app
ITEM_FILES = {
    'RawMaterials': 'raw',
    'Products': 'product',
    'Curiosity': 'curiosity',
    'TradeItems': 'trade',
    'Technology': 'tech',
    'ConstructedTechnology': 'tech',
    'UpgradeModules': 'upgrade',
    'Cooking': 'food',
    'Others': 'other',
}
RECIPE_FILES = {'Refinery': 'refiner', 'NutrientProcessor': 'cooking'}

# Technology groups that can sit damaged in a crashed starship
SHIP_GROUP_WORDS = ('starship', 'pulse engine', 'hyperdrive', 'spacecraft', 'ship-mounted',
                    'launch', 'warp drive', 'vertical take-off')


def download():
    SRC.mkdir(exist_ok=True)
    for stem in list(ITEM_FILES) + list(RECIPE_FILES):
        url = f'{BASE_URL}{stem}.lang.json'
        print('downloading', url)
        urllib.request.urlretrieve(url, SRC / f'{stem}.lang.json')
    print('downloading', DEV_URL)
    urllib.request.urlretrieve(DEV_URL, SRC / 'developerDetails.json')
    # Save-file key mapping (changes with game updates)
    rel = json.loads(urllib.request.urlopen(MAPPING_API).read())
    for asset in rel.get('assets', []):
        if asset['name'] == 'mapping.json':
            print('downloading', asset['browser_download_url'], f"({rel.get('tag_name')})")
            urllib.request.urlretrieve(asset['browser_download_url'], ROOT / 'app' / 'data' / 'save_mapping.json')


def clean(text: str) -> str:
    """Strip the game's <TAG>markup<> and collapse whitespace."""
    text = re.sub(r'<[A-Z_0-9]*>', '', text or '')
    return re.sub(r'[ \t]*\n\s*', '\n', text).strip()


def load(stem):
    path = SRC / f'{stem}.lang.json'
    if not path.exists():
        print(f'  (missing {path.name}, skipped)')
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    if '--download' in sys.argv:
        download()

    # app item id -> the game's internal id (used to read save files)
    game_ids = {}
    dev_path = SRC / 'developerDetails.json'
    if dev_path.exists():
        for entry in json.loads(dev_path.read_text(encoding='utf-8')):
            for prop in entry.get('Properties', []):
                if prop.get('Name') == 'GameId' and prop.get('Value'):
                    game_ids[entry['Id']] = str(prop['Value']).upper()

    items = {}
    for stem, kind in ITEM_FILES.items():
        for x in load(stem):
            name = (x.get('Name') or '').strip()
            if not name:
                continue
            group = (x.get('Group') or '').strip()
            usages = x.get('Usages') or []
            items[x['Id']] = {
                'id': x['Id'],
                'gid': game_ids.get(x['Id'], ''),
                'name': name,
                'kind': kind,
                'group': group,
                'desc': clean(x.get('Description', ''))[:600],
                'icon': x.get('CdnUrl') or '',
                'colour': (x.get('Colour') or '').strip('#') or '3a4a66',
                'abbrev': x.get('Abbrev') or '',
                'value': x.get('BaseValueUnits') or 0,
                'currency': x.get('CurrencyType') or 'None',
                'stack': int(x.get('MaxStackSize') or 0),
                'requires': [{'id': r['Id'], 'qty': int(r['Quantity'])}
                             for r in (x.get('RequiredItems') or []) if r.get('Quantity', 0) > 0],
                'obsolete': 'IsNoLongerObtainable' in usages,
                'damaged': 'damaged' in group.lower(),
                'ship_part': (group.lower() == 'damaged starship component'
                              or (kind == 'tech' and any(w in group.lower() for w in SHIP_GROUP_WORDS))),
            }

    recipes = []
    for stem, station in RECIPE_FILES.items():
        for r in load(stem):
            out = r.get('Output') or {}
            recipes.append({
                'id': r['Id'],
                'station': station,
                'inputs': [{'id': i['Id'], 'qty': int(i['Quantity'])} for i in r.get('Inputs', [])],
                'output': {'id': out.get('Id'), 'qty': int(out.get('Quantity') or 1)},
                'time': r.get('Time') or '',
                'op': clean((r.get('Operation') or '').replace('Requested Operation:', '')),
            })

    # Drop recipes/requirements that point at unknown items (keeps the app simple and safe)
    known = set(items)
    recipes = [r for r in recipes
               if r['output']['id'] in known and all(i['id'] in known for i in r['inputs'])]
    for it in items.values():
        it['requires'] = [r for r in it['requires'] if r['id'] in known]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'items': list(items.values()), 'recipes': recipes},
                              ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    kinds = {}
    for it in items.values():
        kinds[it['kind']] = kinds.get(it['kind'], 0) + 1
    print(f'items: {len(items)} {kinds} | with game id: {sum(1 for i in items.values() if i["gid"])}')
    print(f'recipes: {len(recipes)} | ship parts: {sum(1 for i in items.values() if i["ship_part"])}')
    print(f'wrote {OUT} ({OUT.stat().st_size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
