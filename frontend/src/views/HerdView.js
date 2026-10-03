import { View } from './View.js';
import { api } from '../services/api.js';
import { AnimalForm } from '../components/animalForm.js';
import { animalCardHtml, animalLabel } from '../components/animalCard.js';
import { esc, fmtTime, media, toast } from '../ui.js';

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
        const pen = (sex, title) => {
            const members = this.animals.filter(a => a.sex === sex);
            const living = members.filter(a => a.status === 'alive').length;
            const capacity = this.settings.pen_capacity?.[sex] ?? '?';
            return `
                <section class="pen">
                    <h2>${title} <span class="count${living > capacity ? ' over' : ''}">${living} / ${capacity}</span></h2>
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
                        <label><input type="checkbox" id="show-gone" ${this.showGone ? 'checked' : ''}> Show sold / dead</label>
                    </div>
                    <div class="pens">${pen('M', 'Males')}${pen('F', 'Females')}</div>
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

        if (this.selectedId) this.renderDetail();
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
            ? `<button data-status="sold">Mark sold</button><button data-status="dead" class="danger">Mark dead</button>`
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
            </div>
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
        panel.querySelectorAll('[data-status]').forEach(btn => btn.addEventListener('click', () => {
            const status = btn.dataset.status;
            if (status !== 'alive' && !confirm(`Mark ${a.code} as ${status}?`)) return;
            this.save(a.id, { status });
        }));
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

    async recordMating() {
        const mother_id = Number(this.container.querySelector('#mate-f').value);
        const father_id = Number(this.container.querySelector('#mate-m').value);
        if (!mother_id || !father_id) {
            toast('Pick a female and a male', 'error');
            return;
        }
        try {
            const result = await api.post('/api/matings', { mother_id, father_id });
            toast(result.incest ? 'Mating recorded. They share a herd number, so this counts as incest.' : 'Mating recorded',
                result.incest ? 'warn' : 'info');
            if (this.selectedId) this.renderDetail();
        } catch (e) {
            toast(e.message, 'error');
        }
    }
}
