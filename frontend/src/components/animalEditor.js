import { api } from '../services/api.js';
import { AnimalForm, buildingsFrom } from './animalForm.js';
import { animalLabel } from './animalCard.js';
import { esc, toast } from '../ui.js';

/**
 * A pop-up editor for one animal, for pages without the Herd tab's side panel (the Pools page). Quick buttons for the
 * common changes - pregnant or not, sold, dead, missing - and the full form underneath. Calls onDone after a change.
 */
export function openAnimalEditor(animal, animals, settings, onDone) {
    document.querySelector('.editor-overlay')?.remove();
    const overlay = document.createElement('div');
    overlay.className = 'editor-overlay';
    const ewe = animal.sex === 'F';
    overlay.innerHTML = `
        <div class="panel editor">
            <div class="panel-head">
                <h2>${esc(animalLabel(animal))}</h2>
                <button data-close title="Close">✕</button>
            </div>
            <div class="actions">
                ${ewe ? `<button data-quick="pregnant" class="${animal.pregnant ? '' : 'primary'}">${animal.pregnant ? 'Not pregnant' : 'Pregnant'}</button>` : ''}
                <button data-status="sold">Sold</button>
                <button data-status="missing">Missing</button>
                <button data-status="dead" class="danger">Dead</button>
            </div>
            <div class="editor-form"></div>
            <div class="actions">
                <button data-save class="primary">Save changes</button>
                <button data-close>Cancel</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
    const form = new AnimalForm(overlay.querySelector('.editor-form'), animals.filter(a => a.id !== animal.id), animal,
        buildingsFrom(settings));

    const close = () => overlay.remove();
    const apply = async (changes, message) => {
        try {
            await api.patch(`/api/animals/${animal.id}`, changes);
            toast(message);
            close();
            onDone?.();
        } catch (e) {
            toast(e.message, 'error');
        }
    };
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    overlay.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
    overlay.querySelector('[data-quick="pregnant"]')?.addEventListener('click', () =>
        apply({ pregnant: !animal.pregnant }, `${animal.name || animal.code}: ${animal.pregnant ? 'not pregnant' : 'pregnant'}`));
    overlay.querySelectorAll('[data-status]').forEach(b => b.addEventListener('click', () => {
        if (b.dataset.status === 'dead' && !confirm(`Mark ${animal.name || animal.code} as dead?`)) return;
        apply({ status: b.dataset.status }, `${animal.name || animal.code} marked ${b.dataset.status}`);
    }));
    overlay.querySelector('[data-save]').addEventListener('click', () => apply(form.values(), 'Saved'));
}
