import { View } from './View.js';
import { api } from '../services/api.js';
import { GENES, GENE_NAMES, SPECIES_ICON } from '../components/animalCard.js';
import { esc, media } from '../ui.js';

const hours = (minutes) => (minutes == null ? '—' : `${(minutes / 60).toFixed(1)} h`);

/** The breeding plan: which pairs to mate now to reach a god male fastest. */
export class PlanView extends View {
    constructor() {
        super();
        this.species = 'sheep';
    }

    async render() {
        if (this.target == null) {
            try { this.target = (await api.get('/api/settings')).target_genes || 'DLYFH'; } catch (e) { this.target = 'DLYFH'; }
        }
        this.container.innerHTML = `
            <div class="panel plan">
                <div class="toolbar">
                    <h2>Plan to a male Good/Good on</h2>
                    <div class="target-genes">${GENES.map(g => `<label title="${GENE_NAMES[g]}">
                        <input type="checkbox" data-gene="${g}" ${this.target.includes(g) ? 'checked' : ''}> ${g} <span class="muted">${GENE_NAMES[g]}</span></label>`).join('')}</div>
                    <span class="spacer"></span>
                    <div class="seg">
                        <button data-species="sheep" class="${this.species === 'sheep' ? 'on' : ''}">🐑 Sheep</button>
                        <button data-species="cow" class="${this.species === 'cow' ? 'on' : ''}">🐄 Cows</button>
                    </div>
                    <button id="btn-plan" class="primary">Plan</button>
                </div>
                <p class="hint">Untick genes you don't care about (e.g. D if dung is worthless to you): every gene left out makes the
                    target much quicker to reach. All five ticked is a full god animal, which may sell better at the barn.
                    Simulates the herd forward a few hundred times with the game's timings, and picks the matings that get there soonest. Re-plan after every birth: what gets born changes the next step.</p>
                <div id="plan-result"></div>
            </div>
            <div class="panel plan">
                <div class="toolbar">
                    <h2>Next barn trip</h2>
                    <span class="spacer"></span>
                    <div class="seg" id="vehicle">
                        <button data-vehicle="lead">Lead on foot</button>
                        <button data-vehicle="single">Single module</button>
                        <button data-vehicle="double">Double module</button>
                    </div>
                </div>
                <div id="trip"></div>
            </div>`;
        this.container.querySelectorAll('[data-species]').forEach(btn => btn.addEventListener('click', () => {
            this.species = btn.dataset.species;
            this.render();
        }));
        this.container.querySelector('#btn-plan').addEventListener('click', () => this.runPlan());
        this.container.querySelectorAll('[data-gene]').forEach(box => box.addEventListener('change', async () => {
            const target = GENES.filter(g => this.container.querySelector(`[data-gene="${g}"]`).checked).join('');
            if (!target) { box.checked = true; return; }  // at least one gene
            this.target = target;
            await api.put('/api/settings', { target_genes: target });
            this.container.querySelector('#plan-result').innerHTML = '<p class="hint">Target changed: press Plan.</p>';
            this.showTrip();
        }));
        this.container.querySelectorAll('[data-vehicle]').forEach(btn => btn.addEventListener('click', async () => {
            await api.put('/api/settings', { vehicle: btn.dataset.vehicle });
            this.showTrip();
        }));
        this.showTrip();
    }

    /** What to sell and buy at the barn this trip, within what the truck carries. */
    async showTrip() {
        const target = this.container.querySelector('#trip');
        let trip, settings;
        try {
            const keep = (this.planned || []).join(',');
            [trip, settings] = await Promise.all([api.get(`/api/trip?species=${this.species}&keep_ids=${keep}`), api.get('/api/settings')]);
        } catch (e) {
            target.innerHTML = `<p class="error">${esc(e.message)}</p>`;
            return;
        }
        this.container.querySelectorAll('[data-vehicle]').forEach(b => b.classList.toggle('on', b.dataset.vehicle === settings.vehicle));
        const young = this.species === 'cow' ? 'calf' : 'lamb';
        const label = (sex) => (sex === 'M' ? (this.species === 'cow' ? 'bull' : 'ram') : (this.species === 'cow' ? 'cow' : 'ewe'));
        const buy = trip.buy.length
            ? trip.buy.map(sex => `<li>1 ${label(sex)} ${young}</li>`).join('')
            : '<li class="muted">Nothing: every gene shows green and the pens are full.</li>';
        const sell = trip.sell.length
            ? trip.sell.map(a => `<li>${esc(a.name)} (${label(a.sex)})</li>`).join('')
            : `<li class="muted">${trip.capacity.adults === 0 ? "A single module can't carry a grown cow." : 'Nothing to sell yet.'}</li>`;
        target.innerHTML = `
            <div class="trip-cols">
                <div><h3>Take to sell</h3><ul>${sell}</ul></div>
                <div><h3>Buy</h3><ul>${buy}</ul></div>
            </div>
            ${trip.missing.length ? `<p class="warn">No animal shows green on ${trip.missing.join(', ')} yet: keep buying until every gene shows green somewhere.</p>` : ''}
            <p class="hint">Only grown animals sell. Never sold: the best ${this.species === 'cow' ? 'bulls' : 'rams'}, pregnant females (mark them Pregnant), any animal that is the last one showing green on a gene,
                and${this.planned ? '' : ' (once you press Plan)'} any animal the plan wants to mate now.</p>`;
    }

    async runPlan() {
        const target = this.container.querySelector('#plan-result');
        const button = this.container.querySelector('#btn-plan');
        button.disabled = true;
        target.innerHTML = '<p class="hint">Simulating… this takes 10–20 seconds.</p>';
        let plan, animals;
        try {
            [plan, animals] = await Promise.all([
                api.get(`/api/plan?species=${this.species}`),
                api.get('/api/animals')
            ]);
        } catch (e) {
            target.innerHTML = `<p class="error">${esc(e.message)}</p>`;
            button.disabled = false;
            return;
        }
        button.disabled = false;
        // Animals the plan wants to mate now are never offered for sale on the barn trip.
        this.planned = (plan.matings || []).flatMap(m => [m.female_id, m.male_id]);
        this.showTrip();
        if (!plan.possible) {
            target.innerHTML = `<p class="warn">${esc(plan.reason || 'No plan is possible with this herd.')}</p>`;
            return;
        }
        const byId = Object.fromEntries(animals.map(a => [a.id, a]));
        const who = (id) => {
            const a = byId[id];
            if (!a) return '?';
            const img = a.name_image ? `<img class="name-img" src="${media(a.name_image)}" alt="">` : '';
            return `<span class="who">${SPECIES_ICON[a.species] || ''} <b>${esc(a.name || a.code)}</b> ${img}</span>`;
        };
        const e = plan.expected;
        target.innerHTML = `
            <div class="plan-summary">
                <div><span class="muted">Typical time to a male Good/Good on ${esc(plan.target || 'DLYFH')}</span><b>${hours(e.median)}</b></div>
                <div><span class="muted">Worst 1 in 10</span><b>${hours(e.p90)}</b></div>
                <div><span class="muted">Reached within 48 h</span><b>${Math.round(e.success * 100)}%</b></div>
                <div><span class="muted">Births along the way</span><b>~${Math.round(plan.births)}</b></div>
            </div>
            <h3>Mate now</h3>
            ${plan.matings.length ? `<table class="plan-matings">${plan.matings.map(m => `
                <tr><td>${who(m.female_id)}</td><td>×</td><td>${who(m.male_id)}</td>
                    <td class="muted">${m.p_god_male > 0 ? `${(m.p_god_male * 100).toFixed(1)}% god male per birth` : 'building towards it'}</td></tr>`).join('')}
            </table>` : '<p class="hint">Nobody to mate right now: wait for a cooldown or a lamb to grow up.</p>'}
            <p class="hint">Females not listed should rest for now. Surplus lambs can be sold: the plan keeps at most your pen
                capacities of each sex (Settings).</p>
            <h3>Assumptions</h3>
            <ul class="hint">${plan.assumptions.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`;
    }
}
