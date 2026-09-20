from flask import Blueprint, abort, jsonify, request

from app import db, live, savefile, saveimport, services
from app.gamedata import game
from app.models import Goal, Repair, Ship

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.before_request
def _require_xhr_for_mutations():
    """CSRF guard: other web pages cannot add this header cross-origin without a preflight."""
    if request.method == 'POST' and request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        abort(403)


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _qty(value, default=1, top=99_999) -> int:
    try:
        return max(1, min(int(value), top))
    except (TypeError, ValueError):
        return default


def _item_or_404(item_id):
    return game().get(item_id) or abort(404)


# ── search (item pickers) ───────────────────────────────────────────────────
@api_bp.route('/search')
def search():
    g = game()
    results = g.search(request.args.get('q', ''), limit=25,
                       ship_only=request.args.get('ship') == '1')
    return jsonify([{'id': i['id'], 'name': i['name'], 'group': i['group'], 'icon': i['icon'],
                     'colour': i['colour'],
                     'requires': [{'name': g.name(r['id']), 'qty': r['qty']} for r in i['requires']]}
                    for i in results])


# ── inventory ───────────────────────────────────────────────────────────────
@api_bp.route('/have/<item_id>', methods=['POST'])
def set_have(item_id):
    _item_or_404(item_id)
    data = _body()
    if 'delta' in data:
        current = services.stock().get(item_id, 0)
        try:
            value = current + int(data['delta'])
        except (TypeError, ValueError):
            abort(400)
    else:
        try:
            value = int(data.get('have', 0))
        except (TypeError, ValueError):
            abort(400)
    return jsonify({'item_id': item_id, 'have': services.set_have(item_id, value)})


# ── goals ───────────────────────────────────────────────────────────────────
@api_bp.route('/goal', methods=['POST'])
def add_goal():
    data = _body()
    item = _item_or_404(data.get('item_id'))
    goal = Goal(item_id=item['id'], qty=_qty(data.get('qty')), note=(data.get('note') or '')[:300] or None)
    db.session.add(goal)
    db.session.commit()
    return jsonify({'id': goal.id, 'name': item['name'], 'qty': goal.qty})


@api_bp.route('/goal/<int:goal_id>/toggle', methods=['POST'])
def toggle_goal(goal_id):
    goal = db.get_or_404(Goal, goal_id)
    goal.done = not goal.done
    db.session.commit()
    if goal.done and _body().get('consume'):
        services.consume(game().direct_requirements(goal.item_id, goal.qty))
    return jsonify({'id': goal.id, 'done': goal.done})


@api_bp.route('/goal/<int:goal_id>/delete', methods=['POST'])
def delete_goal(goal_id):
    db.session.delete(db.get_or_404(Goal, goal_id))
    db.session.commit()
    return jsonify({'status': 'ok'})


# ── ships & repairs ─────────────────────────────────────────────────────────
@api_bp.route('/ship', methods=['POST'])
def add_ship():
    data = _body()
    name = (data.get('name') or '').strip()[:120]
    if not name:
        abort(400)
    ship = Ship(name=name, kind=(data.get('kind') or '')[:40] or None,
                ship_class=(data.get('ship_class') or '')[:2] or None,
                location=(data.get('location') or '')[:200] or None)
    db.session.add(ship)
    db.session.commit()
    return jsonify({'id': ship.id})


@api_bp.route('/ship/<int:ship_id>/update', methods=['POST'])
def update_ship(ship_id):
    ship = db.get_or_404(Ship, ship_id)
    data = _body()
    if 'notes' in data:
        ship.notes = (data.get('notes') or '')[:4000]
    if 'location' in data:
        ship.location = (data.get('location') or '')[:200] or None
    db.session.commit()
    return jsonify({'status': 'ok'})


@api_bp.route('/ship/<int:ship_id>/delete', methods=['POST'])
def delete_ship(ship_id):
    db.session.delete(db.get_or_404(Ship, ship_id))
    db.session.commit()
    return jsonify({'status': 'ok'})


@api_bp.route('/ship/<int:ship_id>/repair', methods=['POST'])
def add_repair(ship_id):
    ship = db.get_or_404(Ship, ship_id)
    data = _body()
    item = _item_or_404(data.get('item_id'))
    qty = _qty(data.get('qty'), top=60)
    # another broken slot of a part already listed just raises its count
    rep = next((r for r in ship.repairs if r.item_id == item['id'] and not r.done), None)
    if rep is None:
        rep = Repair(ship_id=ship.id, item_id=item['id'], qty=qty)
        db.session.add(rep)
    else:
        rep.qty = min(60, rep.qty + qty)
    db.session.commit()
    return jsonify({'id': rep.id, 'qty': rep.qty})


@api_bp.route('/repair/<int:repair_id>/fix', methods=['POST'])
def fix_repair(repair_id):
    """Tick damaged slots off one at a time: {'delta': 1} or an absolute {'fixed': n}."""
    rep = db.get_or_404(Repair, repair_id)
    data = _body()
    before = rep.fixed
    try:
        target = int(data['fixed']) if 'fixed' in data else before + int(data.get('delta', 1))
    except (TypeError, ValueError):
        abort(400)
    rep.set_fixed(target)
    db.session.commit()
    gained = rep.fixed - before
    if gained > 0 and data.get('consume'):
        item = game().get(rep.item_id)
        services.consume([(r['id'], r['qty'] * gained) for r in (item['requires'] if item else [])])
    ship = rep.ship
    return jsonify({'id': rep.id, 'fixed': rep.fixed, 'qty': rep.qty, 'done': rep.done,
                    'ship_fixed': ship.fixed, 'ship_total': ship.total,
                    'ship_complete': gained > 0 and ship.fixed == ship.total, 'ship_name': ship.name})


@api_bp.route('/repair/<int:repair_id>/delete', methods=['POST'])
def delete_repair(repair_id):
    db.session.delete(db.get_or_404(Repair, repair_id))
    db.session.commit()
    return jsonify({'status': 'ok'})


# ── save file import ────────────────────────────────────────────────────────
@api_bp.route('/save/sync', methods=['POST'])
def save_sync():
    data = _body()
    path = data.get('path')
    if path not in {s['path'] for s in savefile.find_saves()}:
        abort(400)                       # never open an arbitrary path from a request
    try:
        parsed = saveimport.read(path)
    except Exception:  # noqa: BLE001
        abort(422)
    sources = [s for s in (data.get('sources') or []) if s in saveimport.SOURCES]
    ships = {int(i) for i in (data.get('ships') or []) if str(i).lstrip('-').isdigit()}
    result = {
        'inventory': saveimport.sync_inventory(parsed, sources) if sources else {'items': 0, 'changed': 0},
        'ships': saveimport.sync_ships(parsed, path, ships),
    }
    if 'auto' in data:                   # "keep in sync" tick box on the import page
        live.enable(path, sources) if data['auto'] else live.disable()
    return jsonify(result)


# ── live sync ───────────────────────────────────────────────────────────────
@api_bp.route('/live', methods=['POST'])
def live_poll():
    """Polled by every page. Pulls in a newer save when live sync is on."""
    return jsonify(live.poll())


@api_bp.route('/live/off', methods=['POST'])
def live_off():
    live.disable()
    return jsonify({'status': 'ok'})
