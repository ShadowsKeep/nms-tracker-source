from flask import Blueprint, abort, render_template, request

from datetime import datetime

from app import db, live, savefile, saveimport, services
from app.gamedata import KIND_LABELS, game
from app.models import Goal, Ship

pages_bp = Blueprint('pages', __name__)

SHIP_KINDS = ['Fighter', 'Hauler', 'Explorer', 'Shuttle', 'Exotic', 'Solar', 'Interceptor',
              'Living Ship', 'Freighter', 'Other']
SHIP_CLASSES = ['C', 'B', 'A', 'S']


@pages_bp.app_context_processor
def inject_nav():
    ships = Ship.query.order_by(Ship.created_at).all()
    cfg = live.config()
    # live_known: the owner has made a choice before, so an "off" is respected on the import page
    return {'nav_ships': ships, 'kind_labels': KIND_LABELS, 'item_name': game().name,
            'live_rev': live.rev(), 'live_on': bool(cfg.get('enabled')), 'live_known': bool(cfg)}


@pages_bp.route('/')
def dashboard():
    return render_template('dashboard.html', s=services.summary(), active='dashboard',
                           ships=Ship.query.order_by(Ship.created_at).all())


@pages_bp.route('/collect')
def collect():
    raw_mode = request.args.get('mode', 'raw') != 'direct'
    rows, used = services.collect_list(raw_mode)
    return render_template('collect.html', rows=rows, used=used, raw_mode=raw_mode, active='collect',
                           missing=sum(1 for r in rows if r['missing'] > 0))


@pages_bp.route('/items')
def items():
    g = game()
    q = request.args.get('q', '')
    kind = request.args.get('kind', 'raw' if not q else '')
    results = g.search(q, kinds=[kind] if kind else None, limit=120)
    have = services.stock()
    return render_template('items.html', results=results, q=q, kind=kind, have=have, active='items')


@pages_bp.route('/item/<item_id>')
def item(item_id):
    g = game()
    it = g.get(item_id) or abort(404)
    have = services.stock()
    crafted_from = [dict(item=g.get(r['id']), qty=r['qty']) for r in it['requires']]
    made_by = [g.recipe_view(r) for r in g.made_by.get(item_id, [])]
    used_in = [g.recipe_view(r) for r in g.used_in.get(item_id, [])]
    crafts_into = sorted(g.crafts_into.get(item_id, []), key=lambda i: (i['kind'] != 'product', i['name']))
    # Group "refines into" by what comes out, so 12 ways to make the same thing read as one block
    outputs = {}
    for r in used_in:
        outputs.setdefault(r['output']['item']['id'], {'item': r['output']['item'], 'recipes': []})['recipes'].append(r)
    return render_template(
        'item.html', it=it, have=have.get(item_id, 0), stock=have, crafted_from=crafted_from,
        made_by=made_by, turns_into=sorted(outputs.values(), key=lambda o: o['item']['name']),
        crafts_into=crafts_into, active='items',
    )


@pages_bp.route('/goals')
def goals():
    g = game()
    have = services.stock()
    rows = []
    for goal in Goal.query.order_by(Goal.done, Goal.created_at.desc()).all():
        item = g.get(goal.item_id)
        parts = [dict(item=g.get(i), need=q, have=have.get(i, 0), ok=have.get(i, 0) >= q)
                 for i, q in g.direct_requirements(goal.item_id, goal.qty)]
        rows.append(dict(goal=goal, item=item, parts=parts, ready=all(p['ok'] for p in parts)))
    return render_template('goals.html', rows=rows, active='goals')


@pages_bp.route('/ships')
def ships():
    return render_template('ships.html', ships=Ship.query.order_by(Ship.created_at).all(),
                           ship_kinds=SHIP_KINDS, ship_classes=SHIP_CLASSES, active='ships')


def _repair_rows(sh):
    have = services.stock()
    return [services.repair_status(r, have) for r in sh.repairs]


@pages_bp.route('/ship/<int:ship_id>/repairs')
def ship_repairs(ship_id):
    """Just the repair cards, so the ship page can refresh itself without reloading."""
    sh = db.get_or_404(Ship, ship_id)
    return render_template('_repairs.html', ship=sh, repairs=_repair_rows(sh))


@pages_bp.route('/ship/<int:ship_id>')
def ship(ship_id):
    sh = db.get_or_404(Ship, ship_id)
    repairs = _repair_rows(sh)
    g = game()
    damaged = [p for p in g.ship_parts if p['group'] == 'Damaged Starship Component']
    tech = [p for p in g.ship_parts if p['group'] != 'Damaged Starship Component' and p['requires']]
    return render_template('ship.html', ship=sh, repairs=repairs, damaged=damaged, tech=tech,
                           active='ships', active_ship=sh.id)


@pages_bp.route('/save')
def save_import():
    g = game()
    saves = savefile.find_saves()
    for sv in saves:
        sv['when'] = datetime.fromtimestamp(sv['modified']).strftime('%d %b %Y %H:%M')
    allowed = {sv['path'] for sv in saves}
    chosen = request.args.get('path') or (saves[0]['path'] if saves else None)
    if chosen not in allowed:          # only ever open files we discovered ourselves
        chosen = saves[0]['path'] if saves else None
    data = error = None
    sources, preview, ships = {}, [], []
    if chosen:
        try:
            data = saveimport.read(chosen)
        except Exception as e:  # noqa: BLE001 - show any decode problem to the user
            error = str(e) or e.__class__.__name__
    if data:
        for key, (label, default) in saveimport.SOURCES.items():
            sources[key] = {'label': label, 'default': default, 'count': len(data['totals'].get(key, {}))}
        everything = saveimport.combined(data, list(saveimport.SOURCES))
        preview = sorted(({'item': g.get(i), 'qty': q} for i, q in everything.items()),
                         key=lambda r: (r['item']['kind'] != 'raw', r['item']['name']))
        for sh in data['ships']:
            ships.append(dict(sh, linked=saveimport.linked_ship(chosen, sh['index']) is not None,
                              parts=[{'item': g.get(i), 'qty': q} for i, q in sh['damaged'].items()]))
        ships.sort(key=lambda x: (not x['current'], -x['damaged_total']))
    return render_template('save.html', saves=saves, chosen=chosen, data=data, error=error, sources=sources,
                           preview=preview, ships=ships, root=str(savefile.save_root()), active='save')
