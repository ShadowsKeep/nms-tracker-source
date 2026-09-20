"""Business logic: turning goals + open ship repairs into a collect list."""
from app import db
from app.gamedata import game
from app.models import Goal, Inventory, Repair, Ship


def stock() -> dict:
    return {row.item_id: row.have for row in Inventory.query.all()}


def set_have(item_id: str, value: int) -> int:
    value = max(0, min(int(value), 9_999_999))
    row = db.session.get(Inventory, item_id)
    if row is None:
        row = Inventory(item_id=item_id, have=value)
        db.session.add(row)
    else:
        row.have = value
    db.session.commit()
    return value


def consume(requirements):
    """Remove used materials from the inventory (never below zero)."""
    for item_id, qty in requirements:
        row = db.session.get(Inventory, item_id)
        if row:
            row.have = max(0, row.have - qty)
    db.session.commit()


def requirement_lines():
    """Every open need as (item_id, qty, source_label): the goal item or broken part itself."""
    g = game()
    lines = []
    for goal in Goal.query.filter_by(done=False).all():
        lines.append((goal.item_id, goal.qty, f'Goal: {goal.qty}× {g.name(goal.item_id)}'))
    for rep in Repair.query.filter_by(done=False).join(Ship).all():
        item = g.get(rep.item_id)
        if item and item['requires']:
            lines.append((rep.item_id, rep.qty, f'{rep.ship.name}: {item["name"]}'))
    return lines


def collect_list(raw_mode: bool):
    """Rows for the Collect page, most-missing first."""
    g = game()
    have = stock()
    needs, from_stock = g.expand(requirement_lines(), have, raw_mode)
    rows = []
    for item_id, info in needs.items():
        item = g.get(item_id)
        owned = have.get(item_id, 0)
        need = info['qty']
        rows.append({
            'item': item,
            'need': need,
            'have': owned,
            'missing': max(0, need - owned),
            'percent': min(100, round(owned / need * 100)) if need else 100,
            'sources': sorted(info['sources']),
            'craftable': bool(item['requires']),
            'refinable': bool(g.made_by.get(item_id)),
        })
    rows.sort(key=lambda r: (r['missing'] == 0, -r['missing'] / max(r['need'], 1), r['item']['name']))
    used = [{'item': g.get(i), 'qty': q} for i, q in from_stock.items()]
    return rows, used


def summary():
    rows, _ = collect_list(raw_mode=True)
    ships = Ship.query.all()
    return {
        'materials_total': len(rows),
        'materials_missing': sum(1 for r in rows if r['missing'] > 0),
        'materials_ready': sum(1 for r in rows if r['missing'] == 0),
        'goals_open': Goal.query.filter_by(done=False).count(),
        'goals_done': Goal.query.filter_by(done=True).count(),
        'ships': len(ships),
        'repairs_open': sum(s.total - s.fixed for s in ships),
        'repairs_done': sum(s.fixed for s in ships),
        'top_missing': [r for r in rows if r['missing'] > 0][:6],
    }


def repair_status(repair, have):
    """Can this repair be done right now with what is in the inventory?"""
    g = game()
    item = g.get(repair.item_id)
    parts = []
    ready = True
    for req in (item['requires'] if item else []):
        need = req['qty'] * repair.qty
        owned = have.get(req['id'], 0)
        ok = owned >= need
        ready = ready and ok
        parts.append({'item': g.get(req['id']), 'need': need, 'have': owned, 'ok': ok})
    return {'repair': repair, 'item': item, 'parts': parts, 'ready': ready and bool(parts)}
