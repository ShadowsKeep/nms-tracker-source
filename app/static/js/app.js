/**
 * NMS Tracker — Shadowskeep LLC
 * Shared helpers: API calls, inventory counters, item picker, toasts.
 */
const API_HEADERS = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };

/** POST JSON. Returns the parsed response, or null after showing an error toast. */
async function api(url, body) {
  try {
    const res = await fetch(url, { method: 'POST', headers: API_HEADERS, body: JSON.stringify(body || {}) });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('API error', url, err);
    toast('That did not save', 'Please try again.', 'bad');
    return null;
  }
}

/* ── Toasts ─────────────────────────────────────────────────────────────── */
function toast(title, text, tone) {
  const host = document.getElementById('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast ${tone || ''}`;
  const t = document.createElement('div'); t.className = 'toast-title'; t.textContent = title;
  const d = document.createElement('div'); d.className = 'toast-text'; d.textContent = text || '';
  el.append(t, d);
  host.appendChild(el);
  const close = () => { el.classList.add('out'); setTimeout(() => el.remove(), 300); };
  el.addEventListener('click', close);
  setTimeout(close, tone === 'gold' ? 5200 : 3200);
}
// A toast queued before a page reload
(() => {
  try {
    const queued = sessionStorage.getItem('toast');
    if (queued) { sessionStorage.removeItem('toast'); toast(...JSON.parse(queued)); }
  } catch (e) { /* ignore */ }
})();

/* ── Inventory counters ─────────────────────────────────────────────────── */
const haveTimers = {};
function pushHave(itemId, value, box) {
  clearTimeout(haveTimers[itemId]);
  haveTimers[itemId] = setTimeout(async () => {
    const res = await api(`/api/have/${itemId}`, { have: value });
    if (!res) return;
    document.querySelectorAll(`.have[data-item="${itemId}"] .have-input`).forEach(i => {
      if (i !== document.activeElement) i.value = res.have;
    });
    box.classList.add('saved');
    setTimeout(() => box.classList.remove('saved'), 600);
    document.dispatchEvent(new CustomEvent('have-changed', { detail: { item: itemId, have: res.have } }));
  }, 350);
}

document.querySelectorAll('.have').forEach(box => {
  const input = box.querySelector('.have-input');
  const id = box.dataset.item;
  const clamp = v => Math.max(0, Math.min(9999999, isNaN(v) ? 0 : v));
  box.querySelectorAll('.have-btn').forEach(btn => btn.addEventListener('click', e => {
    e.preventDefault();
    input.value = clamp(parseInt(input.value, 10) + parseInt(btn.dataset.delta, 10));
    pushHave(id, +input.value, box);
    // update the row immediately; the server confirms a moment later
    document.dispatchEvent(new CustomEvent('have-changed', { detail: { item: id, have: +input.value } }));
  }));
  input.addEventListener('input', () => {
    const v = clamp(parseInt(input.value, 10));
    pushHave(id, v, box);
    document.dispatchEvent(new CustomEvent('have-changed', { detail: { item: id, have: v } }));
  });
  input.addEventListener('focus', () => input.select());
});

/* ── Item picker (type-ahead) ───────────────────────────────────────────── */
document.querySelectorAll('[data-picker]').forEach(picker => {
  const input = picker.querySelector('.picker-input');
  const qty = picker.querySelector('.picker-qty');
  const addBtn = picker.querySelector('.picker-add');
  const list = picker.querySelector('.picker-results');
  let chosen = null, timer = null, results = [], cursor = -1;

  function render() {
    list.innerHTML = '';
    results.forEach((it, i) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'picker-row' + (i === cursor ? ' active' : '');
      const tile = document.createElement('span');
      tile.className = 'tile tile-sm';
      tile.style.background = '#' + it.colour;
      if (it.icon) { const img = document.createElement('img'); img.src = it.icon; img.onerror = () => img.remove(); tile.appendChild(img); }
      const name = document.createElement('span'); name.className = 'picker-name'; name.textContent = it.name;
      const group = document.createElement('span'); group.className = 'dim'; group.textContent = it.group;
      row.append(tile, name, group);
      row.addEventListener('click', () => choose(it));
      list.appendChild(row);
    });
    list.classList.toggle('open', results.length > 0);
  }
  function choose(it) {
    chosen = it; input.value = it.name; results = []; cursor = -1; render();
    addBtn.disabled = false;
    if (qty && !it.requires.length && +qty.value === 1) qty.value = 250;  // raw materials come in stacks
    (qty || addBtn).focus();
  }
  input.addEventListener('input', () => {
    chosen = null; addBtn.disabled = true;
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { results = []; render(); return; }
    timer = setTimeout(async () => {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      results = res.ok ? await res.json() : []; cursor = results.length ? 0 : -1; render();
    }, 180);
  });
  input.addEventListener('keydown', e => {
    if (!results.length) return;
    if (e.key === 'ArrowDown') { cursor = (cursor + 1) % results.length; render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { cursor = (cursor - 1 + results.length) % results.length; render(); e.preventDefault(); }
    else if (e.key === 'Enter' && cursor >= 0) { choose(results[cursor]); e.preventDefault(); }
    else if (e.key === 'Escape') { results = []; render(); }
  });
  addBtn.addEventListener('click', async () => {
    if (!chosen) return;
    const n = Math.max(1, parseInt(qty ? qty.value : '1', 10) || 1);
    if (await api('/api/goal', { item_id: chosen.id, qty: n })) location.reload();
  });
  if (qty) qty.addEventListener('keydown', e => { if (e.key === 'Enter') addBtn.click(); });
  document.addEventListener('click', e => { if (!picker.contains(e.target)) { results = []; render(); } });
});
