import { View } from './View.js';
import { api } from '../services/api.js';
import { animalCardHtml } from '../components/animalCard.js';
import { esc, toast } from '../ui.js';

const VERDICT_LABEL = { promote: 'Promote', keep: 'Keep', cull: 'Cull', sell: 'Sell' };

/**
 * Pools mode: harems where each ram mates his ewes freely, plus a holding room. Shows where every animal should be,
 * the moves to get there, and a verdict for everything in holding.
 */
const RECENT_MIN = 15;
const SKIPPED_KEY = 'livestock.skippedMoves';  // moves the player said can't be done right now ("id>to")

function skippedMoves() {
    try { return new Set(JSON.parse(localStorage.getItem(SKIPPED_KEY) || '[]')); } catch (e) { return new Set(); }
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
    const extra = inRange == null ? 0 : inRange - members.length;
    const verdict = extra > 0
        ? ` <span class="warn">- ${extra}${ps <= 31 ? '+' : ''} unaccounted for: a wild one nearby or an uncaptured lamb</span>`
        : '';
    return `<li><b>${esc(site)}</b>: ${known}, cards say ${text}${verdict}</li>`;
}

export class PoolsView extends View {
    constructor() {
        super();
        this.species = 'sheep';
    }

    async render() {
        let plan, animals;
        try {
            [plan, animals] = await Promise.all([api.get(`/api/pools?species=${this.species}`), api.get('/api/animals')]);
        } catch (e) {
            this.container.innerHTML = `<div class="panel error">${esc(e.message)}</div>`;
            return;
        }
        const byId = Object.fromEntries(animals.map(a => [a.id, a]));
        const card = (id) => {
            const a = byId[id];
            if (!a) return '';
            const v = plan.verdicts[id];
            const verdict = v ? `<div class="verdict v-${v.verdict}"><b>${VERDICT_LABEL[v.verdict]}</b> ${esc(v.reason)}</div>` : '';
            const moving = a.pen !== plan.pen[id] ? `<div class="hint">now: ${esc(a.pen || 'not placed')}</div>` : '';
            return `<div class="pool-card">${animalCardHtml(a)}${moving}${verdict}</div>`;
        };
        const cfg = plan.config || {};
        const skipped = skippedMoves();
        const moves = plan.moves.filter(m => !skipped.has(`${m.id}>${m.to}`));
        const skippedHere = plan.moves.filter(m => skipped.has(`${m.id}>${m.to}`));
        const harems = Object.entries(plan.harems).map(([name, h]) => `
            <section class="pen pool">
                <h2>${esc(name)} <span class="count">${h.ewes.length} / ${cfg.harem_ewes || 8} ewes</span></h2>
                <h3>Ram</h3>
                <div class="pen-grid">${h.ram ? card(h.ram) : '<p class="empty">No ram yet</p>'}</div>
                <h3>Ewes</h3>
                <div class="pen-grid">${h.ewes.map(card).join('') || '<p class="empty">None</p>'}</div>
            </section>`).join('');
        const order = { promote: 0, keep: 1, sell: 2, cull: 3 };
        const rooms = plan.holding_rooms || [cfg.holding];
        const holdingHtml = rooms.map(room => {
            const ids = Object.entries(plan.pen).filter(([, pen]) => pen === room).map(([id]) => Number(id));
            ids.sort((a, b) => order[plan.verdicts[a]?.verdict] - order[plan.verdicts[b]?.verdict]);
            return `
                <section class="pen pool holding">
                    <h2>${esc(room)} <span class="muted">(holding)</span> <span class="count">${ids.length} / ${cfg.holding_size || 4}</span></h2>
                    <div class="pen-grid">${ids.map(card).join('') || '<p class="empty">Empty</p>'}</div>
                </section>`;
        }).join('');
        const overflow = (plan.overflow || []).length
            ? `<p class="warn">Holding is full: ${plan.overflow.map(id => esc(byId[id]?.name || id)).join(', ')} won't fit - sell or cull.</p>` : '';
        // Each harem and holding area is its own building, 5+ foundations from the others. Past 9 of a species in one
        // (lambs and wild ones included) personal space falls ~17 points per animal: 10 still breeds, 11 doesn't.
        const cap = cfg.site_cap || 9;
        const here = animals.filter(a => a.species === this.species && a.status === 'alive');
        const crowded = [...Object.keys(plan.harems), ...rooms].map(site => {
            const n = here.filter(a => a.pen === site).length;
            return n > cap ? `<p class="warn">${esc(site)} has ${n}: over ${cap} they lose personal space (${n === cap + 1 ? 'about 83%, still breeding' : 'too low to breed'}). Move, sell or cull ${n - cap}.</p>` : '';
        }).join('');
        const headcount = [...Object.keys(plan.harems), ...rooms].map(site => siteHeadcount(site, here, cap)).join('');
        const loggingOff = `<p class="hint">Logging off: move every harem ram to ${esc(rooms[0] || 'holding')}, or the ewes keep lambing overnight and the harem overcrowds and starves.</p>`;

        this.container.innerHTML = `
            <div class="toolbar">
                <h2>Pools</h2>
                <span class="spacer"></span>
                <div class="seg">
                    <button data-species="sheep" class="${this.species === 'sheep' ? 'on' : ''}">🐑 Sheep</button>
                    <button data-species="cow" class="${this.species === 'cow' ? 'on' : ''}">🐄 Cows</button>
                </div>
            </div>
            <p class="hint">Each harem's ram mates his ewes by himself: no arranging matings. Keep each harem to ${cfg.harem_ewes || 8} ewes
                (crowding stops breeding). Crowding has two rules: about 9 sheep at most within 20 m of each other (walls
                and floors don't count, so a bigger herd needs a second site at least 20 m away), and no clumps within
                about 3 m (several troughs at different spots, no corners to pile into).
                Capture every newborn: it gets a verdict here straight away.</p>
            <div class="panel">
                <h3>Moves to make</h3>
                <p class="hint">Easier by day: at night sleeping sheep break off the lead.</p>
                ${moves.length ? `<ul class="moves">${moves.map(m => `<li><b>${esc(m.name)}</b>: ${esc(m.from || 'not placed')} → ${esc(m.to)}
                        <button class="skip" data-skip="${m.id}>${esc(m.to)}" title="Can't do this one: skip it">✕</button></li>`).join('')}</ul>
                    <button id="btn-apply" class="primary">I've made these moves - record them</button>
                    <button id="btn-skip-all">Skip them all</button>` : `<p class="hint">${plan.moves.length ? 'All suggested moves skipped.' : 'Everyone is where they should be.'}</p>`}
                ${skippedHere.length ? `<p class="hint">${skippedHere.length} skipped. <button id="btn-unskip">Show them again</button></p>` : ''}
            </div>
            <div class="panel">
                <h3>Headcount</h3>
                <p class="hint">From personal space on cards read in the last ${RECENT_MIN} minutes: each animal over ${cap} in range costs about 17 points. More in range than registered means a wild sheep nearby or a lamb not captured yet.</p>
                <ul>${headcount}</ul>
            </div>
            ${crowded}${overflow}${loggingOff}
            <div class="pools">${harems}${holdingHtml}</div>`;

        this.container.querySelectorAll('[data-species]').forEach(btn => btn.addEventListener('click', () => {
            this.species = btn.dataset.species;
            this.render();
        }));
        this.container.querySelector('#btn-apply')?.addEventListener('click', async () => {
            await api.post(`/api/pools/apply?species=${this.species}`, { ids: moves.map(m => m.id) });
            toast('Moves recorded');
            document.getElementById('moves-badge')?.classList.add('hidden');
            this.render();
        });
        this.container.querySelectorAll('[data-skip]').forEach(btn => btn.addEventListener('click', () => {
            const set = skippedMoves();
            set.add(btn.dataset.skip);
            saveSkipped(set);
            this.render();
        }));
        this.container.querySelector('#btn-skip-all')?.addEventListener('click', () => {
            const set = skippedMoves();
            moves.forEach(m => set.add(`${m.id}>${m.to}`));
            saveSkipped(set);
            this.render();
        });
        this.container.querySelector('#btn-unskip')?.addEventListener('click', () => {
            const set = skippedMoves();
            skippedHere.forEach(m => set.delete(`${m.id}>${m.to}`));
            saveSkipped(set);
            this.render();
        });
    }
}
