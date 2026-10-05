import { View } from './View.js';
import { api } from '../services/api.js';
import { AnimalForm } from '../components/animalForm.js';
import { GENE_NAMES, animalCardHtml, animalLabel } from '../components/animalCard.js';
import { renderParents } from '../components/parentsList.js';
import { growsUpAt, lambStatus } from '../components/lambTimer.js';
import { esc, fmtTime, media, refreshCaptureBadge, toast } from '../ui.js';

const pct = (p) => `${Math.round(p * 1000) / 10}%`;

/**
 * The base: a Male pen and a Female pen (cows and sheep mixed), a mating recorder,
 * and a detail panel for editing one animal.
 */
export class HerdView extends View {
    constructor() {
        super();
        this.animals = [];
        this.settings = {};
        this.showGone = false;
        this.selectedId = null;
        this.form = null;
    }

    async render() {
        [this.animals, this.settings] = await Promise.all([
            api.get(`/api/animals?include_gone=${this.showGone}`),
            api.get('/api/settings')
        ]);
        const alive = this.animals.filter(a => a.status === 'alive');
        // Lambs (still growing, whatever their sex) and unsexed animals together; the ram and ewe pens hold grown animals.
        const now = new Date();
        const growing = (a) => { const g = growsUpAt(a); return g != null && g > now; };
        const inPen = (a, sex) => (sex === '?' ? (a.sex === '?' || growing(a)) : (a.sex === sex && !growing(a)));
        const pen = (sex, title) => {
            const members = this.animals.filter(a => inPen(a, sex));
            const living = members.filter(a => a.status === 'alive').length;
            if (sex === '?' && !members.length) return '';
            const capacity = this.settings.pen_capacity?.[sex];
            const count = capacity == null ? `${living}` : `${living} / ${capacity}`;
            return `
                <section class="pen">
                    <h2>${title} <span class="count${capacity != null && living > capacity ? ' over' : ''}">${count}</span></h2>
                    <div class="pen-grid">${members.map(animalCardHtml).join('') || '<p class="empty">Empty</p>'}</div>
                </section>`;
        };
        const options = (sex) => alive.filter(a => a.sex === sex)
            .map(a => `<option value="${a.id}">${esc(animalLabel(a))}</option>`).join('');

        this.container.innerHTML = `
            <div class="herd-layout">
                <div class="herd-main">
                    <div class="toolbar">
                        <span>Record mating:</span>
                        <select id="mate-f"><option value="">Female…</option>${options('F')}</select>
                        <span>×</span>
                        <select id="mate-m"><option value="">Male…</option>${options('M')}</select>
                        <button id="btn-mate">Record</button>
                        <span class="spacer"></span>
                        <label><input type="checkbox" id="show-gone" ${this.showGone ? 'checked' : ''}> Show sold / dead / missing</label>
                    </div>
                    <div id="odds"></div>
                    <div class="pens">${pen('?', 'Lambs (growing) and unsexed')}${pen('M', 'Males')}${pen('F', 'Females')}</div>
                </div>
                <aside id="detail" class="panel ${this.selectedId ? '' : 'hidden'}"></aside>
            </div>`;

        this.container.querySelectorAll('.animal-card').forEach(el =>
            el.addEventListener('click', () => this.select(Number(el.dataset.id))));
        this.container.querySelector('#show-gone').addEventListener('change', e => {
            this.showGone = e.target.checked;
            this.render();
        });
        this.container.querySelector('#btn-mate').addEventListener('click', () => this.recordMating());
        ['#mate-f', '#mate-m'].forEach(sel =>
            this.container.querySelector(sel).addEventListener('change', () => this.showOdds()));

        if (this.selectedId) this.renderDetail();
        // Keep the lamb countdowns current without re-rendering (which would discard edits in the detail panel).
        this.intervals.forEach(id => clearInterval(id));
        this.intervals = [];
        this.addInterval(() => this.container.querySelectorAll('.lamb-timer').forEach(el => {
            const a = this.animals.find(x => x.id === Number(el.dataset.animal));
            const st = a && lambStatus(a);
            if (st) { el.textContent = st.text; el.classList.toggle('due', st.due); }
        }), 20000);
    }

    select(id) {
        this.selectedId = id;
        this.container.querySelector('#detail').classList.remove('hidden');
        this.container.querySelectorAll('.animal-card').forEach(el =>
            el.classList.toggle('selected', Number(el.dataset.id) === id));
        this.renderDetail();
    }

    async renderDetail() {
        const a = this.animals.find(x => x.id === this.selectedId);
        const panel = this.container.querySelector('#detail');
        if (!a) {
            panel.classList.add('hidden');
            return;
        }
        const events = await api.get(`/api/events?animal_id=${a.id}&limit=50`);
        const byId = Object.fromEntries(this.animals.map(x => [x.id, x]));
        const statusButtons = a.status === 'alive'
            ? `<button data-status="sold">Mark sold</button><button data-status="missing">Mark missing</button><button data-status="dead" class="danger">Mark dead</button>`
            : `<button data-status="alive">Restore to herd</button>`;

        panel.innerHTML = `
            <div class="panel-head">
                <h2>${esc(animalLabel(a))}</h2>
                <button id="detail-close" title="Close">✕</button>
            </div>
            ${a.name_image ? `<img class="name-img large" src="${media(a.name_image)}" alt="">` : ''}
            ${a.card_image ? `<img class="card-img" src="${media(a.card_image)}" alt="">` : ''}
            <div id="detail-form"></div>
            <div class="actions">
                <button id="detail-save" class="primary">Save changes</button>
                ${statusButtons}
                <button id="detail-delete" class="danger" title="For mistakes and duplicates. Use Mark sold / Mark dead for real departures.">Delete record</button>
            </div>
            <h3>Parents</h3>
            <div id="detail-parents"><button id="btn-find-parents">Find parents</button></div>
            <h3>History</h3>
            <ul class="events">${events.map(ev => `
                <li><span class="when">${fmtTime(ev.at)}</span> ${esc(ev.kind)}
                ${ev.other_id && byId[ev.other_id] ? ' · ' + esc(animalLabel(byId[ev.other_id])) : ''}
                ${ev.notes ? ` <span class="muted">${esc(ev.notes)}</span>` : ''}</li>`).join('')}</ul>`;

        this.form = new AnimalForm(panel.querySelector('#detail-form'), this.animals.filter(x => x.id !== a.id), a);
        panel.querySelector('#detail-close').addEventListener('click', () => {
            this.selectedId = null;
            panel.classList.add('hidden');
            this.container.querySelectorAll('.animal-card.selected').forEach(el => el.classList.remove('selected'));
        });
        panel.querySelector('#detail-save').addEventListener('click', () => this.save(a.id, this.form.values()));
        panel.querySelector('#detail-delete').addEventListener('click', () => this.deleteRecord(a));
        panel.querySelector('#btn-find-parents').addEventListener('click', () => this.findParents(a));
        panel.querySelectorAll('[data-status]').forEach(btn => btn.addEventListener('click', () => {
            const status = btn.dataset.status;
            if (status === 'dead' && !confirm(`Mark ${a.name || a.code} as dead?`)) return;
            this.save(a.id, { status });
        }));
    }

    async findParents(a) {
        const target = this.container.querySelector('#detail-parents');
        target.innerHTML = '<p class="hint">Checking every pair…</p>';
        try {
            const [candidates, everyone] = await Promise.all([
                api.get(`/api/animals/${a.id}/parents`),
                api.get('/api/animals?include_gone=true')
            ]);
            renderParents(target, candidates, Object.fromEntries(everyone.map(x => [x.id, x])),
                (c) => this.save(a.id, { origin: 'bred', mother_id: c.mother_id, father_id: c.father_id }));
        } catch (e) {
            target.innerHTML = `<p class="error">${esc(e.message)}</p>`;
        }
    }

    async deleteRecord(a) {
        const name = a.name || a.code;
        if (!confirm(`Delete ${name} (${a.code}) completely?

This is for mistakes and duplicates: its history is removed and `
                + `its capture goes back to Pending. If the animal really left the herd, use Mark sold or Mark dead instead.`)) return;
        try {
            await api.del(`/api/animals/${a.id}`);
            toast(`Deleted ${name}`);
            this.selectedId = null;
            refreshCaptureBadge();
            await this.render();
        } catch (e) {
            toast(e.message, 'error');
        }
    }

    async save(id, changes) {
        try {
            await api.patch(`/api/animals/${id}`, changes);
            toast('Saved');
            await this.render();
        } catch (e) {
            toast(e.message, 'error');
        }
    }

    async showOdds() {
        const target = this.container.querySelector('#odds');
        const mother_id = this.container.querySelector('#mate-f').value;
        const father_id = this.container.querySelector('#mate-m').value;
        if (!mother_id || !father_id) {
            target.innerHTML = '';
            return;
        }
        let odds;
        try {
            odds = await api.get(`/api/odds?mother_id=${mother_id}&father_id=${father_id}`);
        } catch (e) {
            target.innerHTML = `<div class="panel error">${esc(e.message)}</div>`;
            return;
        }
        const bar = (expressed) => ['G', 'O', 'B'].filter(a => expressed[a] > 0).map(a =>
            `<span class="odds-seg a-${a}" style="flex:${expressed[a]}" title="${pct(expressed[a])}">${pct(expressed[a])}</span>`).join('');
        const genotypes = (g) => Object.entries(g).sort((a, b) => b[1] - a[1])
            .map(([k, p]) => `${k[0]}/${k[1]} ${pct(p)}`).join(' · ');
        const caveats = [
            odds.rows_known ? '' : 'Some second rows are unknown, so hidden copies are guessed (each possibility equally likely).',
            odds.markers_known ? '' : 'Some lineage markers are unknown, so the inbred chance may be too low.'
        ].filter(Boolean);
        target.innerHTML = `
            <div class="panel odds">
                <h3>One lamb from this mating</h3>
                <table>${odds.genes.map(g => `
                    <tr><th title="${GENE_NAMES[g.gene]}">${g.gene}</th>
                        <td class="odds-bar">${bar(g.expressed)}</td>
                        <td class="muted">${genotypes(g.genotypes)}</td></tr>`).join('')}
                </table>
                <div class="odds-summary">
                    <span>Inbred: <b>${pct(odds.p_inbred)}</b></span>
                    <span>All Good showing: <b>${pct(odds.p_all_good)}</b></span>
                    <span>God male (Good/Good on all, ♂): <b>${pct(odds.p_god_male)}</b></span>
                </div>
                ${caveats.map(c => `<p class="hint">${c}</p>`).join('')}
            </div>`;
    }

    async recordMating() {
        const mother_id = Number(this.container.querySelector('#mate-f').value);
        const father_id = Number(this.container.querySelector('#mate-m').value);
        if (!mother_id || !father_id) {
            toast('Pick a female and a male', 'error');
            return;
        }
        try {
            const result = await api.post('/api/matings', { mother_id, father_id });
            toast(result.p_inbred
                ? `Mating recorded. The lamb has a ${pct(result.p_inbred)} chance of being inbred.`
                : 'Mating recorded', result.p_inbred ? 'warn' : 'info');
            if (this.selectedId) this.renderDetail();
        } catch (e) {
            toast(e.message, 'error');
        }
    }
}
