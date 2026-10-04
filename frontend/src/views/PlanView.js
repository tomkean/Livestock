import { View } from './View.js';
import { api } from '../services/api.js';
import { SPECIES_ICON } from '../components/animalCard.js';
import { esc, media } from '../ui.js';

const hours = (minutes) => (minutes == null ? '—' : `${(minutes / 60).toFixed(1)} h`);

/** The breeding plan: which pairs to mate now to reach a god male fastest. */
export class PlanView extends View {
    constructor() {
        super();
        this.species = 'sheep';
    }

    async render() {
        this.container.innerHTML = `
            <div class="panel plan">
                <div class="toolbar">
                    <h2>Plan to a god male</h2>
                    <span class="spacer"></span>
                    <div class="seg">
                        <button data-species="sheep" class="${this.species === 'sheep' ? 'on' : ''}">🐑 Sheep</button>
                        <button data-species="cow" class="${this.species === 'cow' ? 'on' : ''}">🐄 Cows</button>
                    </div>
                    <button id="btn-plan" class="primary">Plan</button>
                </div>
                <p class="hint">Simulates the herd forward a few hundred times with the game's timings, and picks the matings
                    that reach a god male (Good/Good on every gene) soonest. Re-plan after every birth: what gets born changes the next step.</p>
                <div id="plan-result"></div>
            </div>`;
        this.container.querySelectorAll('[data-species]').forEach(btn => btn.addEventListener('click', () => {
            this.species = btn.dataset.species;
            this.render();
        }));
        this.container.querySelector('#btn-plan').addEventListener('click', () => this.runPlan());
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
                <div><span class="muted">Typical time to a god male</span><b>${hours(e.median)}</b></div>
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
