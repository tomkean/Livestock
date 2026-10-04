import { View } from './View.js';
import { api } from '../services/api.js';
import { ScreenCaptureService } from '../services/ScreenCaptureService.js';
import { requestCapture } from '../services/captureActions.js';
import { AnimalForm } from '../components/animalForm.js';
import { animalCardHtml } from '../components/animalCard.js';
import { esc, fmtTime, media, refreshCaptureBadge, toast } from '../ui.js';

const PREVIEW_MAX_WIDTH = 360;

/** Merge a gene row read from a capture into a stored one; '?' in the capture keeps the stored value. */
function mergeRow(stored, seen) {
    if (!seen) return stored;
    if (!stored) return seen;
    return [...seen].map((c, i) => (c === '?' ? stored[i] : c)).join('');
}

/**
 * Review captured frames: mark where the card and name are, enter what the card shows,
 * then save as a new animal or update the existing animal it matches.
 */
export class CaptureView extends View {
    constructor() {
        super();
        this.captures = [];
        this.animals = [];
        this.settings = {};
        this.selected = null;
        this.boxes = { card: null, name: null };
        this.drawMode = 'card';
        this.formValues = null;
        this.readings = {};
        this.matchTimer = null;
    }

    async render() {
        [this.captures, this.animals, this.settings] = await Promise.all([
            api.get('/api/captures'),
            api.get('/api/animals'),
            api.get('/api/settings')
        ]);
        if (!this.captures.some(c => c.id === this.selected?.id)) {
            this.selectCapture(this.captures[0] || null, false);
        }
        const sharing = ScreenCaptureService.isCapturing();

        this.container.innerHTML = `
            <div class="capture-layout">
                <aside class="panel capture-list">
                    <div class="share-controls">
                        <button id="btn-share">${sharing ? 'Stop sharing' : 'Share screen'}</button>
                        <button id="btn-capture-delay">Capture in 5s</button>
                    </div>
                    <p class="hint">Share screen on the gaming PC. Press Capture from any device while an animal card is showing.</p>
                    <h3>Pending captures</h3>
                    <ul class="captures">${this.captures.map(c => `
                        <li data-id="${c.id}" class="${c.id === this.selected?.id ? 'selected' : ''}">
                            <img src="${media('captures/' + c.path)}" alt="">
                            <span>${fmtTime(c.at)}</span>
                            <button data-dismiss="${c.id}" title="Discard">✕</button>
                        </li>`).join('') || '<li class="empty">None</li>'}
                    </ul>
                </aside>
                ${this.selected ? this.reviewHtml() : '<div class="capture-main empty">No capture selected</div>'}
            </div>`;

        this.container.querySelector('#btn-share').addEventListener('click', () => this.toggleShare());
        this.container.querySelector('#btn-capture-delay').addEventListener('click', () => requestCapture(5));
        this.container.querySelectorAll('.captures li[data-id]').forEach(li => li.addEventListener('click', e => {
            if (e.target.closest('[data-dismiss]')) return;
            this.selectCapture(this.captures.find(c => c.id === Number(li.dataset.id)));
        }));
        this.container.querySelectorAll('[data-dismiss]').forEach(btn => btn.addEventListener('click', () =>
            this.dismiss(Number(btn.dataset.dismiss))));

        if (this.selected) this.bindReview();
    }

    reviewHtml() {
        return `
            <div class="capture-main">
                <div class="toolbar">
                    <span>Adjust:</span>
                    <div class="seg">
                        <button data-mode="card" class="${this.drawMode === 'card' ? 'on' : ''}">Card box</button>
                        <button data-mode="name" class="${this.drawMode === 'name' ? 'on' : ''}">Name box</button>
                    </div>
                    <button id="btn-default-boxes">Save boxes as default</button>
                </div>
                <div class="stage" id="stage">
                    <img id="frame" src="${media('captures/' + this.selected.path)}" draggable="false" alt="">
                    <div class="box card" id="box-card"></div>
                    <div class="box name" id="box-name"></div>
                </div>
                <div class="previews">
                    <div><h3>Card</h3><canvas id="prev-card"></canvas></div>
                    <div><h3>Name</h3><canvas id="prev-name"></canvas></div>
                </div>
            </div>
            <aside class="panel capture-form">
                <h3>What the card shows</h3>
                <div id="read-status" class="hint">Reading the card…</div>
                <div id="cap-form"></div>
                <button id="btn-new" class="primary">Save as new animal</button>
                <h3>Already in the herd?</h3>
                <div id="matches"><p class="hint">Fill in sex and some genes or herd numbers to find matches.</p></div>
            </aside>`;
    }

    selectCapture(capture, rerender = true) {
        this.selected = capture;
        this.boxes = { card: this.settings.card_box || null, name: this.settings.name_box || null };
        if (rerender) this.render();
    }

    bindReview() {
        const stage = this.container.querySelector('#stage');
        const img = this.container.querySelector('#frame');
        const redraw = () => {
            this.drawBoxes();
            this.drawPreviews();
        };
        img.complete ? redraw() : img.addEventListener('load', redraw);

        this.container.querySelectorAll('[data-mode]').forEach(btn => btn.addEventListener('click', () => {
            this.drawMode = btn.dataset.mode;
            this.container.querySelectorAll('[data-mode]').forEach(b => b.classList.toggle('on', b === btn));
        }));
        this.container.querySelector('#btn-default-boxes').addEventListener('click', async () => {
            this.settings = await api.put('/api/settings', { card_box: this.boxes.card, name_box: this.boxes.name });
            toast('Boxes saved as default');
        });

        stage.addEventListener('mousedown', e => {
            e.preventDefault();
            const rect = stage.getBoundingClientRect();
            const frac = (ev) => [
                Math.min(Math.max((ev.clientX - rect.left) / rect.width, 0), 1),
                Math.min(Math.max((ev.clientY - rect.top) / rect.height, 0), 1)
            ];
            const [x0, y0] = frac(e);
            const move = (ev) => {
                const [x1, y1] = frac(ev);
                this.boxes[this.drawMode] = [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)];
                this.drawBoxes();
            };
            const up = () => {
                window.removeEventListener('mousemove', move);
                window.removeEventListener('mouseup', up);
                this.drawPreviews();
            };
            window.addEventListener('mousemove', move);
            window.addEventListener('mouseup', up);
        });

        const form = new AnimalForm(this.container.querySelector('#cap-form'), this.animals, this.formValues || {});
        this.form = form;
        form.onChange(values => {
            this.formValues = values;
            clearTimeout(this.matchTimer);
            this.matchTimer = setTimeout(() => this.findMatches(), 300);
        });
        this.container.querySelector('#btn-new').addEventListener('click', () => this.saveNew());
        this.applyReading();
    }

    /** Read the card automatically and fill in the boxes and the form; the person only checks and corrects. */
    async applyReading() {
        const capture = this.selected;
        const status = this.container.querySelector('#read-status');
        let reading = this.readings[capture.id];
        if (!reading) {
            try {
                reading = await api.get(`/api/captures/${capture.id}/read`);
            } catch (e) {
                reading = { found: false, error: e.message };
            }
            this.readings[capture.id] = reading;
        }
        if (this.selected !== capture || !status) return;  // moved on while reading
        if (!reading.found) {
            status.textContent = reading.error ? `Couldn't read the card: ${reading.error}` : 'No card found in this capture - fill it in by hand.';
            this.findMatches();
            return;
        }
        this.boxes = { card: reading.card_box, name: reading.name_box };
        this.drawBoxes();
        this.drawPreviews();
        const fields = { genes_top: reading.genes_top, herd_top: reading.herd_top, name: reading.name || '' };
        if (reading.genes_bottom) Object.assign(fields, { genes_bottom: reading.genes_bottom, herd_bottom: reading.herd_bottom });
        this.form.set(fields);
        this.formValues = this.form.values();
        const unread = [
            reading.genes_top.includes('?') || (reading.genes_bottom || '').includes('?') ? 'some genes' : '',
            reading.herd_top === null || (reading.genes_bottom && reading.herd_bottom === null) ? 'a marker number' : ''
        ].filter(Boolean);
        status.innerHTML = 'Read from the card. Check it, set the sex, and save.'
            + (reading.name ? '' : " The name isn't plain Latin text (or OCR is off), so the app's ID will be used unless you type one.")
            + (reading.inbred ? ' <b class="warn">The card says INBRED.</b>' : '')
            + (unread.length ? ` <b class="warn">Couldn't read ${unread.join(' or ')} - please fill in.</b>` : '');
        this.findMatches();
    }

    drawBoxes() {
        for (const kind of ['card', 'name']) {
            const el = this.container.querySelector(`#box-${kind}`);
            const box = this.boxes[kind];
            if (!el) continue;
            el.style.display = box ? 'block' : 'none';
            if (box) {
                const [x, y, w, h] = box;
                Object.assign(el.style, { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` });
            }
        }
    }

    drawPreviews() {
        const img = this.container.querySelector('#frame');
        for (const kind of ['card', 'name']) {
            const canvas = this.container.querySelector(`#prev-${kind}`);
            const box = this.boxes[kind];
            if (!canvas || !img) continue;
            if (!box || box[2] === 0 || box[3] === 0) {
                canvas.width = canvas.height = 0;
                continue;
            }
            const [x, y, w, h] = box;
            const sw = w * img.naturalWidth, sh = h * img.naturalHeight;
            const scale = Math.min(1, PREVIEW_MAX_WIDTH / sw);
            canvas.width = Math.round(sw * scale);
            canvas.height = Math.round(sh * scale);
            canvas.getContext('2d').drawImage(img, x * img.naturalWidth, y * img.naturalHeight, sw, sh,
                0, 0, canvas.width, canvas.height);
        }
    }

    cropFields() {
        return { capture_id: this.selected.id, card_box: this.boxes.card, name_box: this.boxes.name };
    }

    async findMatches() {
        const target = this.container.querySelector('#matches');
        if (!target || !this.form) return;
        const v = this.form.values();
        let matches;
        try {
            matches = await api.post('/api/animals/match', v);
        } catch (e) {
            return;
        }
        if (!matches.length) {
            target.innerHTML = '<p class="hint">No matching animal. Save it as new.</p>';
            return;
        }
        target.innerHTML = matches.map(m => `
            <div class="match">
                ${animalCardHtml(m.animal)}
                <button data-update="${m.animal.id}">Update ${esc(m.animal.code)} from this capture</button>
            </div>`).join('');
        target.querySelectorAll('[data-update]').forEach(btn => btn.addEventListener('click', () =>
            this.updateExisting(matches.find(m => m.animal.id === Number(btn.dataset.update)).animal)));
    }

    async saveNew() {
        try {
            const animal = await api.post('/api/animals', { ...this.form.values(), ...this.cropFields() });
            toast(`Saved as ${animal.code}`);
            this.afterSave();
        } catch (e) {
            toast(e.message, 'error');
        }
    }

    async updateExisting(animal) {
        const v = this.form.values();
        const changes = {
            genes_top: mergeRow(animal.genes_top, v.genes_top),
            herd_top: v.herd_top ?? animal.herd_top,
            pregnant: v.pregnant,
            ...this.cropFields()
        };
        // The second row is only known from the admin view; keep what is stored if it wasn't entered.
        changes.genes_bottom = mergeRow(animal.genes_bottom, v.genes_bottom);
        changes.herd_bottom = v.herd_bottom ?? animal.herd_bottom;
        try {
            await api.patch(`/api/animals/${animal.id}`, changes);
            toast(`Updated ${animal.code}`);
            this.afterSave();
        } catch (e) {
            toast(e.message, 'error');
        }
    }

    afterSave() {
        this.formValues = this.formValues ? { species: this.formValues.species } : null;
        this.selected = null;
        refreshCaptureBadge();
        this.render();
    }

    async dismiss(id) {
        if (!confirm('Discard this capture?')) return;
        await api.del(`/api/captures/${id}`);
        if (this.selected?.id === id) this.selected = null;
        refreshCaptureBadge();
        this.render();
    }

    async toggleShare() {
        try {
            if (ScreenCaptureService.isCapturing()) ScreenCaptureService.stopCapture();
            else await ScreenCaptureService.startCapture();
        } catch (e) {
            toast(e.message, 'error');
        }
    }

    // Called by main.js
    onCapturesChanged() {
        this.render();
    }

    onShareStatus() {
        const btn = this.container.querySelector('#btn-share');
        if (btn) btn.textContent = ScreenCaptureService.isCapturing() ? 'Stop sharing' : 'Share screen';
    }

    destroy() {
        super.destroy();
        clearTimeout(this.matchTimer);
    }
}
