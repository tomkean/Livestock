import { View } from './View.js';
import { api } from '../services/api.js';
import { animalCardHtml } from '../components/animalCard.js';
import { esc, toast } from '../ui.js';

const VERDICT_LABEL = { promote: 'Promote', keep: 'Keep', cull: 'Cull', sell: 'Sell' };

/**
 * Pools mode: harems where each ram mates his ewes freely, plus a holding room. Shows where every animal should be,
 * the moves to get there, and a verdict for everything in holding.
 */
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
                (crowding stops breeding). Crowding counts sheep within about 3 m, so spread them out: several troughs
                at different spots, no corners to pile into. Separate rooms need no gap between them.
                Capture every newborn: it gets a verdict here straight away.</p>
            <div class="panel">
                <h3>Moves to make</h3>
                ${plan.moves.length ? `<ul>${plan.moves.map(m => `<li><b>${esc(m.name)}</b>: ${esc(m.from || 'not placed')} → ${esc(m.to)}</li>`).join('')}</ul>
                    <button id="btn-apply" class="primary">I've moved them - record it</button>` : '<p class="hint">Everyone is where they should be.</p>'}
            </div>
            ${overflow}
            <div class="pools">${harems}${holdingHtml}</div>`;

        this.container.querySelectorAll('[data-species]').forEach(btn => btn.addEventListener('click', () => {
            this.species = btn.dataset.species;
            this.render();
        }));
        this.container.querySelector('#btn-apply')?.addEventListener('click', async () => {
            await api.post(`/api/pools/apply?species=${this.species}`);
            toast('Rooms recorded');
            document.getElementById('moves-badge')?.classList.add('hidden');
            this.render();
        });
    }
}
