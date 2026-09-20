"""
Turn a decoded save into something the tracker can use, and sync it into the database.

Reading is delegated to app.savefile (strictly read-only). Nothing here writes to the game.
"""
from collections import defaultdict
from datetime import datetime

from app import db, savefile
from app.gamedata import game
from app.models import Inventory, Repair, Ship

# Inventory groups offered on the import page: key -> (label, default on)
SOURCES = {
    'exosuit': ('Exosuit (general + cargo)', True),
    'ships': ('All starship inventories', True),
    'freighter': ('Freighter', True),
    'storage': ('Storage containers', True),
    'vehicles': ('Exocraft', False),
}

SHIP_TYPES = [  # substring of the model path -> ship type used by the tracker
    ('SENTINELSHIP', 'Interceptor'), ('BIOSHIP', 'Living Ship'), ('SAILSHIP', 'Solar'),
    ('ROYAL', 'Exotic'), ('S-CLASS', 'Exotic'), ('SCIENTIFIC', 'Explorer'), ('DROPSHIP', 'Hauler'),
    ('SHUTTLE', 'Shuttle'), ('FIGHTER', 'Fighter'), ('CORVETTE', 'Other'), ('BIGGS', 'Other'),
]

_cache = {}


def _gid(slot) -> str:
    return str(slot.get('Id', '')).lstrip('^').split('#')[0].upper()


def _slots(inv):
    return (inv or {}).get('Slots') or []


def _is_tech(slot) -> bool:
    t = slot.get('Type')
    return (t.get('InventoryType') if isinstance(t, dict) else t) == 'Technology'


def _player_state(doc):
    ctx = 'ExpeditionContext' if doc.get('ActiveContext') == 'Season' and doc.get('ExpeditionContext') else 'BaseContext'
    return (doc.get(ctx) or doc).get('PlayerStateData') or doc.get('PlayerStateData') or {}


def _ship_type(resource) -> str:
    path = str((resource or {}).get('Filename', '')).upper()
    for needle, label in SHIP_TYPES:
        if needle in path:
            return label
    return 'Other'


def read(path):
    """Decode a save (cached by modification time) and summarise it for the tracker."""
    stamp = savefile.Path(path).stat().st_mtime
    hit = _cache.get(path)
    if hit and hit[0] == stamp:
        return hit[1]

    g = game()
    ps = _player_state(savefile.load(path))

    groups = {
        'exosuit': [ps.get('Inventory'), ps.get('Inventory_Cargo')],
        'freighter': [ps.get('FreighterInventory'), ps.get('FreighterInventory_Cargo')],
        'storage': [v for k, v in ps.items() if k.startswith('Chest') and k.endswith('Inventory')]
                   + [ps.get('CorvetteStorageInventory')],
        'vehicles': [v.get('Inventory') for v in (ps.get('VehicleOwnership') or []) if isinstance(v, dict)],
        'ships': [],
    }

    ships = []
    primary = ps.get('PrimaryShip')
    for index, sh in enumerate(ps.get('ShipOwnership') or []):
        if not str((sh.get('Resource') or {}).get('Filename', '')).strip():
            continue  # empty hangar slot
        groups['ships'] += [sh.get('Inventory'), sh.get('Inventory_Cargo')]
        kind = _ship_type(sh.get('Resource'))
        damaged = defaultdict(int)
        unknown = 0
        for slot in _slots(sh.get('Inventory')) + _slots(sh.get('Inventory_TechOnly')) + _slots(sh.get('Inventory_Cargo')):
            if (slot.get('DamageFactor') or 0) <= 0:
                continue
            item = g.by_game_id.get(_gid(slot))
            if item and item['requires']:
                damaged[item['id']] += 1
            else:
                unknown += 1
        name = (sh.get('Name') or '').strip() or f'{kind} (hangar {index + 1})'
        ships.append({
            'index': index, 'name': name, 'kind': kind, 'current': index == primary,
            'damaged': dict(damaged), 'damaged_total': sum(damaged.values()), 'unknown': unknown,
        })

    totals = {key: defaultdict(int) for key in groups}
    unmapped = set()
    for key, inventories in groups.items():
        for inv in inventories:
            for slot in _slots(inv):
                if _is_tech(slot):
                    continue
                item = g.by_game_id.get(_gid(slot))
                amount = int(slot.get('Amount') or 0)
                if item and amount > 0:
                    totals[key][item['id']] += amount
                elif not item:
                    unmapped.add(_gid(slot))

    result = {
        'path': path, 'modified': datetime.fromtimestamp(stamp),
        'totals': {k: dict(v) for k, v in totals.items()},
        'ships': ships, 'unmapped': sorted(unmapped),
        'units': ps.get('Units'), 'nanites': ps.get('Nanites'), 'quicksilver': ps.get('Specials'),
    }
    _cache.clear()
    _cache[path] = (stamp, result)
    return result


def combined(data, sources):
    out = defaultdict(int)
    for key in sources:
        for item_id, amount in data['totals'].get(key, {}).items():
            out[item_id] += amount
    return dict(out)


# ── syncing into the tracker ────────────────────────────────────────────────
def sync_inventory(data, sources) -> dict:
    """Make the tracker's inventory match the save for the chosen sources."""
    wanted = combined(data, sources)
    changed = 0
    rows = {r.item_id: r for r in Inventory.query.all()}
    for item_id, amount in wanted.items():
        row = rows.get(item_id)
        if row is None:
            db.session.add(Inventory(item_id=item_id, have=amount))
            changed += 1
        elif row.have != amount:
            row.have = amount
            changed += 1
    for item_id, row in rows.items():
        if item_id not in wanted and row.have:
            row.have = 0          # you no longer own any of it
            changed += 1
    db.session.commit()
    return {'items': len(wanted), 'changed': changed}


def ship_keys(save_path, index) -> list:
    """save_key values for one hangar slot. A game slot is two files (auto + manual save),
    so a ship imported from one must still be recognised when the other is the newer file."""
    p = savefile.Path(save_path)
    digits = ''.join(ch for ch in p.stem if ch.isdigit())
    n = int(digits) if digits else 1
    twin = n + 1 if n % 2 else n - 1
    twin_path = p.with_name(f"save{'' if twin == 1 else twin}.hg")
    return [f'{p}#{index}', f'{twin_path}#{index}']


def linked_ship(save_path, index):
    return Ship.query.filter(Ship.save_key.in_(ship_keys(save_path, index))).first()


def sync_ships(data, save_path, indexes) -> dict:
    """Create/update tracker ships from the save. The save is the truth for how many slots of
    each part are still broken; slots repaired in game are ticked off one by one."""
    created = fixed = added = reopened = 0
    for info in data['ships']:
        if info['index'] not in indexes:
            continue
        ship = linked_ship(save_path, info['index'])
        if ship is None:
            if not info['damaged']:
                continue          # nothing to track on a healthy ship
            ship = Ship(name=info['name'], kind=info['kind'], save_key=f"{save_path}#{info['index']}")
            db.session.add(ship)
            db.session.flush()
            created += 1
        else:
            ship.name = info['name']
        rows_by_item = defaultdict(list)
        for rep in ship.repairs:
            rows_by_item[rep.item_id].append(rep)
        for item_id, count in info['damaged'].items():
            rows = rows_by_item.pop(item_id, [])
            if not rows:
                db.session.add(Repair(ship_id=ship.id, item_id=item_id, qty=count))
                added += 1
                continue
            still_open = sum(r.remaining for r in rows)
            if count < still_open:                  # some were repaired in game
                left = still_open - count
                fixed += left
                for rep in rows:
                    take = min(rep.remaining, left)
                    rep.set_fixed(rep.fixed + take)
                    left -= take
            elif count > still_open:                # ticked off here but still broken in game
                extra = count - still_open
                reopened += extra
                for rep in reversed(rows):
                    take = min(rep.fixed, extra)
                    rep.set_fixed(rep.fixed - take)
                    extra -= take
                if extra:                           # more damage than was ever listed
                    rows[0].qty += extra
                    rows[0].set_fixed(rows[0].fixed)
        for rows in rows_by_item.values():   # was damaged, is not any more: repaired in game
            for rep in rows:
                fixed += rep.remaining
                rep.set_fixed(rep.qty)
    db.session.commit()
    return {'created': created, 'repairs_added': added, 'repairs_fixed': fixed,
            'repairs_reopened': reopened}
