import { GENES, GENE_NAMES, animalLabel } from './animalCard.js';
import { esc } from '../ui.js';

const CYCLE = ['?', 'G', 'O', 'B'];
const ADMIN_VIEW_KEY = 'livestock.adminView';

function adminViewPref() {
    try { return localStorage.getItem(ADMIN_VIEW_KEY) === '1'; } catch (e) { return false; }
}

const BLANK = {
    name: '', species: 'sheep', sex: 'F', origin: 'ranch',
    genes_top: '?????', genes_bottom: '?????',
    herd_top: null, herd_bottom: null,
    pregnant: false, mother_id: null, father_id: null, notes: '', pen: ''
};

/** The buildings set up in Pools (harems, then holding), for the Building picker. */
export function buildingsFrom(settings) {
    const pools = settings?.pools || {};
    const holding = Array.isArray(pools.holding) ? pools.holding : pools.holding ? [pools.holding] : [];
    return [...(pools.harems || []), ...holding];
}

/**
 * Editable animal fields: species, sex, origin, both gene rows (click a circle to cycle ? → Good → Ok → Bad),
 * herd numbers, pregnancy, parents and notes. The second row is only visible to admins in game, so it is
 * hidden unless the 'admin view' switch is on.
 */
export class AnimalForm {
    constructor(container, animals = [], values = {}, buildings = []) {
        this.container = container;
        this.animals = animals;
        this.buildings = buildings;
        this.v = { ...BLANK, ...values };
        this.showSecond = !!values.genes_bottom || values.herd_bottom != null || adminViewPref();
        if (!this.v.genes_bottom) this.v.genes_bottom = '?????';
        this.changeListeners = [];
        this.container.addEventListener('click', e => this._onClick(e));
        this.container.addEventListener('input', e => this._onInput(e));
        this.render();
    }

    onChange(cb) {
        this.changeListeners.push(cb);
    }

    _changed() {
        this.changeListeners.forEach(cb => cb(this.values()));
    }

    set(values) {
        this.v = { ...this.v, ...values };
        if (values.genes_bottom) this.showSecond = true;
        if (!this.v.genes_bottom) this.v.genes_bottom = '?????';
        this.render();
    }

    values() {
        const ranch = this.v.origin === 'ranch';
        return {
            name: this.v.name,
            species: this.v.species,
            sex: this.v.sex,
            origin: this.v.origin,
            genes_top: this.v.genes_top,
            genes_bottom: this.showSecond ? this.v.genes_bottom : null,
            herd_top: this.v.herd_top,
            herd_bottom: this.showSecond ? this.v.herd_bottom : null,
            pregnant: this.v.sex === 'F' && this.v.pregnant,
            mother_id: ranch ? null : this.v.mother_id,
            father_id: ranch ? null : this.v.father_id,
            notes: this.v.notes,
            pen: this.v.pen || ''
        };
    }

    _seg(field, options) {
        return `<div class="seg">${options.map(([value, label]) =>
            `<button type="button" data-field="${field}" data-value="${value}"
                class="${this.v[field] === value ? 'on' : ''}">${label}</button>`).join('')}</div>`;
    }

    _geneRow(row) {
        const genes = this.v[row];
        return GENES.map((g, i) => {
            const allele = genes[i];
            return `<button type="button" class="dot edit a-${allele === '?' ? 'U' : allele}${row === 'genes_bottom' ? ' small' : ''}"
                data-gene-row="${row}" data-index="${i}" title="${GENE_NAMES[g]}">${g}</button>`;
        }).join('');
    }

    _buildingSelect() {
        const names = [...this.buildings];
        if (this.v.pen && !names.includes(this.v.pen)) names.push(this.v.pen);
        const options = names.map(n => `<option value="${esc(n)}" ${this.v.pen === n ? 'selected' : ''}>${esc(n)}</option>`).join('');
        return `<select data-input="pen"><option value="">Outside / not sure (missing)</option>${options}</select>`;
    }

    _parentSelect(field, sex) {
        const options = this.animals
            .filter(a => a.sex === sex && a.species === this.v.species)
            .map(a => `<option value="${a.id}" ${this.v[field] === a.id ? 'selected' : ''}>${esc(animalLabel(a))}</option>`)
            .join('');
        const blank = sex === 'F' ? 'Mother?' : 'Father? (from last mating)';
        return `<select data-input="${field}"><option value="">${blank}</option>${options}</select>`;
    }

    render() {
        const ranch = this.v.origin === 'ranch';
        const herdInput = (field) => `<input type="number" min="0" class="herd-input" data-input="${field}"
            value="${this.v[field] ?? ''}" placeholder="?">`;
        this.container.innerHTML = `
            <div class="form-grid">
                <label>Name</label>
                <input type="text" data-input="name" maxlength="40" value="${esc(this.v.name)}"
                    placeholder="Blank: use the app's ID (e.g. S-07)">
                <label>Species</label>${this._seg('species', [['sheep', '🐑 Sheep'], ['cow', '🐄 Cow']])}
                <label>Sex</label>${this._seg('sex', [['F', '♀ Female'], ['M', '♂ Male'], ['?', '? Unknown']])}
                <label>Origin</label>${this._seg('origin', [['ranch', 'Ranch'], ['bred', 'Bred']])}
                <label>Building</label>${this._buildingSelect()}
                <label>Genes</label>
                <div class="genes edit">
                    <div class="gene-row">${this._geneRow('genes_top')}${herdInput('herd_top')}</div>
                    ${this.showSecond ? `<div class="gene-row">${this._geneRow('genes_bottom')}${herdInput('herd_bottom')}</div>` : ''}
                    <label class="hint"><input type="checkbox" data-input="show_second" ${this.showSecond ? 'checked' : ''}>
                        Second row visible (admin view)</label>
                    <div class="hint">Click a circle: ? → Good → Ok → Bad. The box at the end is the herd number.</div>
                </div>
                ${this.v.sex === 'F' ? `<label>Pregnant</label>
                    <div><input type="checkbox" data-input="pregnant" ${this.v.pregnant ? 'checked' : ''}></div>` : ''}
                ${ranch ? '' : `<label>Parents</label>
                    <div class="parents">${this._parentSelect('mother_id', 'F')}${this._parentSelect('father_id', 'M')}</div>`}
                <label>Notes</label>
                <textarea data-input="notes" rows="2">${esc(this.v.notes)}</textarea>
            </div>`;
    }

    _onClick(e) {
        const seg = e.target.closest('[data-field]');
        if (seg) {
            this.v[seg.dataset.field] = seg.dataset.value;
            this.render();
            this._changed();
            return;
        }
        const geneBtn = e.target.closest('[data-gene-row]');
        if (geneBtn) {
            const row = geneBtn.dataset.geneRow;
            const i = Number(geneBtn.dataset.index);
            const chars = [...this.v[row]];
            chars[i] = CYCLE[(CYCLE.indexOf(chars[i]) + 1) % CYCLE.length];
            this.v[row] = chars.join('');
            this.render();
            this._changed();
        }
    }

    _onInput(e) {
        const field = e.target.dataset.input;
        if (!field) return;
        if (field === 'show_second') {
            this.showSecond = e.target.checked;
            try { localStorage.setItem(ADMIN_VIEW_KEY, this.showSecond ? '1' : '0'); } catch (err) {}
            this.render();
        } else if (field === 'pregnant') {
            this.v.pregnant = e.target.checked;
        } else if (field === 'notes' || field === 'name' || field === 'pen') {
            this.v[field] = e.target.value;
        } else {
            this.v[field] = e.target.value === '' ? null : Number(e.target.value);
        }
        this._changed();
    }
}
