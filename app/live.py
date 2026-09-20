"""
Live sync: notice when the game writes a new save and pull it in without being asked.

There is no background thread. Every open page polls /api/live every few seconds; that poll
does a cheap stat() of the watched save slot and only decodes the file when it has changed.
The save is still only ever read (see app.savefile).
"""
import json
import threading
import time

from app import db, savefile, saveimport
from app.models import Setting

KEY = 'live_sync'
SETTLE_SECONDS = 2          # leave a file alone while the game may still be writing it

_lock = threading.Lock()
_state = {'rev': 0, 'note': '', 'failed': None}


def config() -> dict:
    row = db.session.get(Setting, KEY)
    try:
        return json.loads(row.value) if row else {}
    except ValueError:
        return {}


def _store(cfg: dict):
    row = db.session.get(Setting, KEY)
    if row is None:
        row = Setting(key=KEY)
        db.session.add(row)
    row.value = json.dumps(cfg)
    db.session.commit()


def enable(path, sources):
    """Watch the game slot that `path` belongs to (both its auto and manual file)."""
    found = next((s for s in savefile.find_saves() if s['path'] == path), None)
    if found is None:
        return
    _store({'enabled': True, 'account': found['account'], 'slot': found['slot'],
            'sources': list(sources), 'mtime': found['modified']})


def disable():
    cfg = config()
    cfg['enabled'] = False      # stored even when it was never on, so the choice is remembered
    _store(cfg)


def rev() -> int:
    return _state['rev']


def poll() -> dict:
    cfg = config()
    if cfg.get('enabled') and _lock.acquire(blocking=False):
        try:
            _check(cfg)
        finally:
            _lock.release()
    return {'enabled': bool(cfg.get('enabled')), 'rev': _state['rev'], 'note': _state['note']}


def _check(cfg):
    slot = [s for s in savefile.find_saves()
            if s['account'] == cfg.get('account') and s['slot'] == cfg.get('slot')]
    if not slot:
        return
    newest = slot[0]                      # find_saves() is newest first
    stamp = newest['modified']
    if stamp == cfg.get('mtime') or stamp == _state['failed']:
        return
    if time.time() - stamp < SETTLE_SECONDS:
        return
    try:
        data = saveimport.read(newest['path'])
    except Exception:  # noqa: BLE001 - half-written or unreadable: wait for the next save
        _state['failed'] = stamp
        return
    tracked = {info['index'] for info in data['ships']
               if saveimport.linked_ship(newest['path'], info['index'])}
    sources = [s for s in (cfg.get('sources') or []) if s in saveimport.SOURCES]
    # no sources ticked means "leave my numbers alone", not "I own nothing"
    inv = saveimport.sync_inventory(data, sources) if sources else {'items': 0, 'changed': 0}
    ships = saveimport.sync_ships(data, newest['path'], tracked)
    cfg['mtime'] = stamp
    _store(cfg)

    bits = []
    if inv['changed']:
        bits.append(f"{inv['changed']} material{'' if inv['changed'] == 1 else 's'} updated")
    if ships['repairs_fixed']:
        bits.append(f"{ships['repairs_fixed']} repair{'' if ships['repairs_fixed'] == 1 else 's'} ticked off")
    if ships['repairs_added']:
        bits.append(f"{ships['repairs_added']} new damage listed")
    if bits or ships['repairs_reopened']:
        _state['rev'] += 1
        _state['note'] = ' · '.join(bits) or 'Repairs updated'
