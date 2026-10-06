import { displayName } from './animalCard.js';
import { esc } from '../ui.js';

/**
 * Candidate parent pairs from the parent finder, each with a "Use" button.
 * `animalsById` must include sold and dead animals, since they can still be parents.
 */
export function renderParents(target, candidates, animalsById, onUse) {
    if (!candidates.length) {
        target.innerHTML = '<p class="hint">No pair in the herd could have produced this card. Born to animals not in the app, or bought.</p>';
        return;
    }
    const name = (id) => esc(animalsById[id] ? displayName(animalsById[id]) : '?');
    target.innerHTML = `<table class="parents-table">${candidates.map((c, i) => `
        <tr>
            <td>♀ <b>${name(c.mother_id)}</b> × ♂ <b>${name(c.father_id)}</b></td>
            <td class="muted">${Math.round(c.chance * 100)}%${c.mated ? ' · mating recorded' : ''}${c.same_building ? ' · both in its building' : ''}</td>
            <td><button data-use="${i}">Use</button></td>
        </tr>`).join('')}</table>
        <p class="hint">Chances are relative to the other pairs that fit.</p>`;
    target.querySelectorAll('[data-use]').forEach(btn => btn.addEventListener('click', () =>
        onUse(candidates[Number(btn.dataset.use)])));
}
