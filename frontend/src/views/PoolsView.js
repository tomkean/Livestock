import { View } from './View.js';
import { api } from '../services/api.js';
import { animalCardHtml } from '../components/animalCard.js';
import { esc, toast } from '../ui.js';
import { openAnimalEditor } from '../components/animalEditor.js';

// Releasing (lead it over a barrier it won't cross back, then let go) doesn't count as a kill, so the herd stays calm.
const VERDICT_LABEL = { promote: 'Promote', keep: 'Keep', cull: 'Release', sell: 'Sell', reject: 'Reject' };

/**
 * Pools mode: harems where each ram mates his ewes freely, plus a holding room. Shows where every animal should be,
 * the moves to get there, and a verdict for everything in holding.
 */
const RECENT_MIN = 15;
const SKIPPED_KEY = 'livestock.skippedMoves';  // moves the player said can't be done right now ("id>to")

function skippedMoves() {
    try { return new Set(JSON.parse(localStorage.getItem(SKIPPED_KEY) || '[]')); } catch (e) { return new Set(); }
}

// A lamb can't usefully be moved into a harem until it's grown: say how long that is.
function growingNote(a) {
    if (!a?.born_at) return '';
    const born = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.born_at) ? a.born_at : a.born_at + 'Z');
    const left = Math.ceil(60 - (Date.now() - born) / 60000);
    return left > 0 ? ` <span class="muted">(lamb: grown in ${left} min)</span>` : '';
}

function saveSkipped(set) {
    try { localStorage.setItem(SKIPPED_KEY, JSON.stringify([...set])); } catch (e) { /* only a convenience */ }
}
const PS_PER_ANIMAL = 17.5;  // personal space lost per animal over the cap: 10 = 83%, 11 = 65%, 12 = 48%, 13+ = 30%

function seenAt(a) {
    if (!a.seen_at) return null;
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.seen_at) ? a.seen_at : a.seen_at + 'Z');
}

// How many of the species the cards say are in range of a site, against how many are registered there.
function siteHeadcount(site, animals, cap) {
    const members = animals.filter(a => a.pen === site);
    const readings = members
        .filter(a => a.personal_space != null && seenAt(a) && Date.now() - seenAt(a) < RECENT_MIN * 60000)
        .map(a => a.personal_space)
        .sort((x, y) => x - y);
    const known = `${members.length} registered${members.length ? ` (${members.map(a => esc(a.name || a.code)).join(', ')})` : ''}`;
    if (!readings.length) return `<li><b>${esc(site)}</b>: ${known}, no recent cards</li>`;
    const ps = readings[Math.floor(readings.length / 2)];
    let inRange, text;
    if (ps >= 99) {
        inRange = null;
        text = `${cap} or fewer in range (${ps}%)`;
    } else if (ps <= 31) {
        inRange = cap + 4;
        text = `${cap + 4} or more in range (${ps}%)`;
    } else {
        inRange = Math.round(cap + (100 - ps) / PS_PER_ANIMAL);
        text = `about ${inRange} in range (${ps}%)`;
    }
    const extra = 0;  // the 8 Oct personal space change broke the count estimate: report the reading, infer nothing
    const verdict = extra > 0
        ? ` <span class="warn">- ${extra}${ps <= 31 ? '+' : ''} unaccounted for: a wild one nearby or an uncaptured lamb</span>`
        : '';
    return `<li><b>${esc(site)}</b>: ${known}, middle personal space ${ps}%${verdict}</li>`;
}

export class PoolsView extends View {
    constructor() {
        super();
        this.species = 'sheep';
        this.refreshTimer = null;
    }

    // Automatic capture saw something (an animal, a sale, a move, the location changed): redraw, at most every few
    // seconds, since the plan behind this page takes longer to work out than the Herd page's pens.
    onAutoSeen() {
        if (this.refreshTimer) return;
        this.refreshTimer = setTimeout(() => {
            this.refreshTimer = null;
            if (this.dragging) return this.onAutoSeen();  // not mid-drag: try again shortly
            if (!this.destroyed) this.render();
        }, 3000);
    }

    destroy() {
        super.destroy();
        this.destroyed = true;  // the tabs share one container: never redraw over the next page
        window.removeEventListener('dragover', this.edgeScroll);
        clearTimeout(this.refreshTimer);
    }

    async render() {
        let plan, animals;
        try {
            [plan, animals, this.settings] = await Promise.all([api.get(`/api/pools?species=${this.species}`),
                api.get('/api/animals'), api.get('/api/settings')]);
        } catch (e) {
            this.container.innerHTML = `<div class="panel error">${esc(e.message)}</div>`;
            return;
        }
        const byId = Object.fromEntries(animals.map(a => [a.id, a]));
        const cfg = plan.config || {};
        const skipped = skippedMoves();
        const moves = plan.moves.filter(m => !skipped.has(`${m.id}>${m.to}`));
        const skippedHere = plan.moves.filter(m => skipped.has(`${m.id}>${m.to}`));
        const location = this.settings?.location || '';
        const fromHere = moves.filter(m => location && (m.from || '') === location);
        const elsewhere = moves.filter(m => !fromHere.includes(m));
        const here = animals.filter(a => a.species === this.species && a.status === 'alive');
        const rooms = plan.holding_rooms || [cfg.holding];
        // Who breeds where, and with whom: the first line on each breeding animal's card.
        const heads = new Set(Object.values(plan.harems).map(h => h.ram).filter(Boolean));
        const pairOf = {};
        const nameOf = (id) => byId[id]?.name || byId[id]?.code || '';
        for (const [room, h] of Object.entries(plan.harems)) {
            if (h.ram) pairOf[h.ram] = { room, with: h.ewes.map(nameOf).join(', ') };
            for (const e of h.ewes) pairOf[e] = { room, with: h.ram ? nameOf(h.ram) : '' };
        }
        const order = { promote: 0, keep: 1, sell: 2, reject: 2, cull: 3 };
        // Each card sits in the building the animal is in now; the plan shows as a note.
        // Seen by automatic capture in the last 2 hours; anything else may already have gone (sold, lost) unnoticed.
        const confirmed = (a) => { const t = seenAt(a); return t && Date.now() - t < 2 * 3600000; };
        const card = (a) => {
            const v = plan.verdicts[a.id];
            const verdict = v ? `<div class="verdict v-${v.verdict}"><b>${VERDICT_LABEL[v.verdict]}</b> ${esc(v.reason)}</div>` : '';
            const to = plan.pen[a.id];
            const moving = to && to !== a.pen && !skipped.has(`${a.id}>${to}`)
                ? `<div class="hint move">→ move to <b>${esc(to)}</b> <button class="skip" data-skip="${a.id}>${esc(to)}" title="Not doing this one: skip it">✕</button></div>` : '';
            const role = pairOf[a.id] ? `<div class="hint role">Breeds in <b>${esc(pairOf[a.id].room)}</b>${pairOf[a.id].with ? ` with ${esc(pairOf[a.id].with)}` : ''}</div>` : '';
            return `<div class="pool-card" draggable="true" data-drag="${a.id}" title="Drag to another room to record a move">${animalCardHtml(a)}${role}${moving}${verdict}</div>`;
        };
        const grid = (list) => `<div class="pen-grid">${list.map(card).join('') || '<p class="empty">None</p>'}</div>`;
        const section = (name, kind) => {
            const inside = here.filter(a => a.pen === name);
            const growing = (a) => { const t = a.born_at && new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.born_at) ? a.born_at : a.born_at + 'Z'); return t && Date.now() - t < 60 * 60000; };
            const young = inside.filter(a => (a.sex !== 'M' && a.sex !== 'F') || growing(a));
            const rams = inside.filter(a => a.sex === 'M' && !young.includes(a)).sort((x, y) => heads.has(y.id) - heads.has(x.id));
            const ewes = inside.filter(a => a.sex === 'F');
            const planned = kind === 'harem' ? byId[plan.harems[name]?.ram] : null;
            const resting = plan.ram_waits?.[name];  // its ewes are all pregnant or resting: the ram waits elsewhere
            const waiting = planned && planned.pen !== name && !resting ? planned : null;  // its ram is elsewhere (e.g. overnight)
            const sorted = (list) => list.sort((x, y) => (order[plan.verdicts[x.id]?.verdict] ?? -1) - (order[plan.verdicts[y.id]?.verdict] ?? -1));
            const room = (plan.rooms || []).find(r => r.name === name) || {};
            const over = inside.length > (room.capacity || Infinity);
            return `
                <section class="pen pool${kind === 'holding' ? ' holding' : ''}${over ? ' over' : ''}" data-room="${esc(name)}">
                    <h2>${esc(name)} ${kind === 'harem' ? '<span class="muted">(breeding)</span>' : ''} <span class="count${over ? ' warn' : ''}" title="animals here now / the room's capacity">${inside.length} / ${room.capacity ?? '?'}</span></h2>
                    ${over ? `<p class="warn">Over capacity: ${inside.length} in a room for ${room.capacity}.</p>` : ''}
                    ${inside.some(a => !confirmed(a)) ? `<p class="hint">Unconfirmed (not seen for 2 h): ${inside.filter(a => !confirmed(a)).map(a => esc(a.name || a.code)).join(', ')}</p>` : ''}
                    ${plan.quiet?.[name] ? `<p class="hint quiet">No new pregnancies for ${plan.quiet[name].minutes ?? 'a long time'}${plan.quiet[name].minutes != null ? ' min' : ''} with ${plan.quiet[name].ready.length} ewe${plan.quiet[name].ready.length === 1 ? '' : 's'} ready (${plan.quiet[name].ready.map(esc).join(', ')}). Try swapping rams with another harem, or taking the ram for a short walk outside.</p>` : ''}
                    ${resting ? `<p class="hint">Ram ${esc(byId[resting.ram]?.name || '')} waits in ${esc(resting.room)}: ${esc(resting.why)}${resting.until ? ` (lamb due about ${new Date(resting.until).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })})` : ''}. Bring him back once the lambs are out of here.</p>` : ''}
                    ${waiting ? `<p class="warn">Harem ram: <b>${esc(waiting.name || waiting.code)}</b>, now in ${esc(waiting.pen || 'no building')} - move him here</p>` : ''}
                    ${rams.length ? `<h3>Rams</h3>${grid(rams)}` : kind === 'harem' && !waiting ? '<h3>Rams</h3><p class="empty">No ram</p>' : ''}
                    ${ewes.filter(a => !young.includes(a)).length ? `<h3>Ewes</h3>${grid(sorted(ewes.filter(a => !young.includes(a))))}` : ''}
                    ${young.length ? `<h3>Lambs and unsexed</h3>${grid(sorted(young))}` : ''}
                    ${inside.length ? '' : '<p class="empty">Empty</p>'}
                </section>`;
        };
        const harems = (plan.rooms || []).map(r => section(r.name, plan.harems[r.name] ? 'harem' : 'holding')).join('');
        // When the farm is overcrowded: who goes first. Breeding pairs, promoted lambs and pregnant ewes never appear.
        const cull = plan.cull_order || [];
        const cullHtml = cull.length ? `
            <div class="panel cull-order"><h2>If you need space: remove in this order</h2>
                <ol>${cull.map(c => `<li><b>${esc(c.name)}</b> <span class="muted">${esc(c.room || 'room unknown')} - ${esc(c.why)}</span></li>`).join('')}</ol>
            </div>` : '';
        // A sheep's room is only ever where it was seen or where you put it: new arrivals start here.
        const rooms_known = new Set((plan.rooms || []).map(r => r.name));
        const unknown = here.filter(a => !rooms_known.has(a.pen));
        const unknownHtml = unknown.length ? `
                <section class="pen pool" data-room="">
                    <h2>Room unknown <span class="muted">(drag each one to the room it's in)</span> <span class="count">${unknown.length}</span></h2>
                    ${grid(unknown)}
                </section>` : '';
        const holdingHtml = '';  // every room is drawn above, whatever it's used for this round
        const known = new Set([...Object.keys(plan.harems), ...rooms]);
        const unplaced = here.filter(a => !known.has(a.pen));
        const unplacedHtml = unplaced.length ? `
                <section class="pen pool">
                    <h2>Not placed <span class="muted">(set the building on the Herd tab, or use Where I am)</span> <span class="count">${unplaced.length}</span></h2>
                    ${grid(unplaced)}
                </section>` : '';
        const overflow = (plan.overflow || []).length
            ? `<p class="warn">The rooms hold ${plan.capacity} and there's no place for ${plan.overflow.map(id => esc(byId[id]?.name || id)).join(', ')}: see the removal order below, or add a room.</p>` : '';
        // Each harem and holding area is its own building, 5+ foundations from the others. Past 9 of a species in one
        // (lambs and wild ones included) personal space falls ~17 points per animal: 10 still breeds, 11 doesn't.
        const cap = cfg.site_cap || 9;
        const crowded = '';
        const headcount = '';
        const loggingOff = '';
        // The rooms: names and capacities only - the plan decides each round what each one is for.
        const roomRows = (plan.rooms || []).map((r, i) => `
            <tr><td><input data-room-name="${i}" value="${esc(r.name)}"></td>
                <td><input type="number" min="1" max="99" data-room-cap="${i}" value="${r.capacity}" style="width:4em"></td>
                <td><button data-room-del="${i}" title="Remove this room">✕</button></td></tr>`).join('');
        const roomsHtml = `
            <details class="panel rooms-editor"${(plan.rooms || []).length ? '' : ' open'}>
                <summary><b>Rooms</b> <span class="muted">${(plan.rooms || []).length} rooms, ${plan.capacity ?? 0} places</span></summary>
                <p class="hint">Name each room and how many sheep it holds in good health. Rooms have no fixed job: each
                    round the plan puts breeding pairs in rooms for two or more (the biggest is kept for the flock) and
                    everyone else one sex per room, within these numbers.</p>
                <table>${roomRows}</table>
                <p><button id="room-add">Add a room</button> <button id="room-save" class="primary">Save rooms</button></p>
            </details>`;

        this.container.innerHTML = `
            <div class="toolbar">
                <h2>Pools</h2>
                <span class="spacer"></span>
                <div class="seg">
                    <button data-species="sheep" class="${this.species === 'sheep' ? 'on' : ''}">🐑 Sheep</button>
                    <button data-species="cattle" class="${this.species === 'cattle' ? 'on' : ''}">🐄 Cattle</button>
                </div>
            </div>
            <p class="hint">Each breeding room holds one pair; every other room one sex, within its capacity. Capture every
                newborn: it gets a verdict here straight away.</p>
            <div class="panel">
                <h3>${location ? `Take from ${esc(location)}` : 'Moves'}</h3>
                ${fromHere.length ? `<ul class="moves">${fromHere.map(m => `<li><b>${esc(m.name)}</b> → ${esc(m.to)}${growingNote(byId[m.id])}
                        <button class="skip" data-skip="${m.id}>${esc(m.to)}" title="Not doing this one: skip it">✕</button></li>`).join('')}</ul>`
                    : `<p class="hint">${location ? `Nothing to take from ${esc(location)}.` : 'Set "Where am I?" at the top to see what to take from that building.'}</p>`}
                ${elsewhere.length ? `<p class="hint">${elsewhere.length} more from other buildings (see the notes on the cards): ${elsewhere.map(m => esc(m.name)).join(', ')}.</p>` : ''}
                ${!moves.length && plan.moves.length ? '<p class="hint">All suggested moves skipped.</p>' : ''}
                <p class="hint">Moves record themselves: Auto capture sees the sheep in its new building. Easier by day: sleeping sheep break off the lead.</p>
                ${skippedHere.length ? `<p class="hint">${skippedHere.length} skipped. <button id="btn-unskip">Show them again</button></p>` : ''}
            </div>
            ${roomsHtml}${overflow}
            ${plan.safe_mode ? `<div class="panel safe-banner"><b>Safe Mode</b>: one sex per room, no breeding, the best animals spread out.${plan.overflow?.length ? ` <span class="warn">${plan.overflow.length} ewe(s) share the ewes' room: no room of their own.</span>` : ''} Turn it off on the Plan page.</div>` : ''}
            <div class="pools">${harems}${holdingHtml}${unknownHtml}</div>${cullHtml}`;

        // The rooms editor: names and capacities, saved together.
        const editor = this.container.querySelector('.rooms-editor');
        const readRooms = () => [...editor.querySelectorAll('[data-room-name]')].map(input => ({
            name: input.value.trim(),
            capacity: Number(editor.querySelector(`[data-room-cap="${input.dataset.roomName}"]`).value) || 1,
        })).filter(r => r.name);
        const saveRooms = async (rooms) => {
            const names = rooms.map(r => r.name);
            if (new Set(names).size !== names.length) { toast('Two rooms have the same name', 'error'); return; }
            const settings = await api.get('/api/settings');
            await api.put('/api/settings', { pools: { ...(settings.pools || {}), rooms } });
            toast(`Rooms saved: ${rooms.length} rooms, ${rooms.reduce((n, r) => n + r.capacity, 0)} places`);
            this.render();
        };
        editor?.querySelector('#room-add')?.addEventListener('click', () => {
            const rooms = readRooms();
            rooms.push({ name: `Room ${rooms.length + 1}`, capacity: 2 });
            saveRooms(rooms);
        });
        editor?.querySelector('#room-save')?.addEventListener('click', () => saveRooms(readRooms()));
        editor?.querySelectorAll('[data-room-del]').forEach(b => b.addEventListener('click', () => {
            const rooms = readRooms();
            const gone = rooms.splice(Number(b.dataset.roomDel), 1)[0];
            if (gone && here.some(a => a.pen === gone.name) && !confirm(`${gone.name} still has sheep recorded in it. Remove the room anyway?`)) return;
            saveRooms(rooms);
        }));

        // Click a sheep to edit it (pregnant, sold, room...); drag it onto another room to record a move.
        this.container.querySelectorAll('[data-drag]').forEach(el => el.addEventListener('click', e => {
            if (e.target.closest('button')) return;  // the card's own buttons (skip a move, ...)
            const a = byId[Number(el.dataset.drag)];
            if (a) openAnimalEditor(a, animals, this.settings || {}, () => this.render());
        }));
        // Drag a sheep onto another room to record that you've moved it there. Near the top or bottom of the window
        // the page scrolls, so a far room can be reached in one drag (no stopping in a room on the way).
        if (!this.edgeScroll) {
            const EDGE = 90;
            this.edgeScroll = e => {
                if (!this.dragging) return;
                const step = e.clientY < EDGE ? -(EDGE - e.clientY) / 3 : e.clientY > innerHeight - EDGE ? (e.clientY - innerHeight + EDGE) / 3 : 0;
                if (step) window.scrollBy(0, step);
            };
            window.addEventListener('dragover', this.edgeScroll);
        }
        this.container.querySelectorAll('[data-drag]').forEach(el => el.addEventListener('dragstart', e => {
            e.dataTransfer.setData('text/plain', el.dataset.drag);
            e.dataTransfer.effectAllowed = 'move';
            el.classList.add('dragging');
            this.dragging = true;
        }));
        this.container.querySelectorAll('[data-drag]').forEach(el => el.addEventListener('dragend', () => {
            el.classList.remove('dragging');
            this.dragging = false;
        }));
        this.container.querySelectorAll('[data-room]').forEach(room => {
            room.addEventListener('dragover', e => { e.preventDefault(); room.classList.add('drop-target'); });
            room.addEventListener('dragleave', e => { if (!room.contains(e.relatedTarget)) room.classList.remove('drop-target'); });
            room.addEventListener('drop', async e => {
                e.preventDefault();
                room.classList.remove('drop-target');
                const id = Number(e.dataTransfer.getData('text/plain'));
                const a = byId[id];
                if (!a || a.pen === room.dataset.room) return;
                try {
                    await api.patch(`/api/animals/${id}`, { pen: room.dataset.room });
                    toast(`${a.name || a.code}: ${a.pen || 'not placed'} → ${room.dataset.room}`);
                    this.render();
                } catch (err) {
                    toast(err.message, 'error');
                }
            });
        });
        this.container.querySelectorAll('[data-species]').forEach(btn => btn.addEventListener('click', () => {
            this.species = btn.dataset.species;
            this.render();
        }));
        this.container.querySelectorAll('[data-skip]').forEach(btn => btn.addEventListener('click', () => {
            const set = skippedMoves();
            set.add(btn.dataset.skip);
            saveSkipped(set);
            this.render();
        }));
        this.container.querySelector('#btn-unskip')?.addEventListener('click', () => {
            const set = skippedMoves();
            skippedHere.forEach(m => set.delete(`${m.id}>${m.to}`));
            saveSkipped(set);
            this.render();
        });
    }
}
