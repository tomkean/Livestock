import { View } from './View.js';
import { api } from '../services/api.js';
import { animalLabel } from '../components/animalCard.js';
import { esc, fmtTime } from '../ui.js';

/** Every event in the herd, newest first. This is the evidence for MECHANICS.md. */
export class LogView extends View {
    async render() {
        const [events, animals] = await Promise.all([
            api.get('/api/events'),
            api.get('/api/animals?include_gone=true')
        ]);
        const byId = Object.fromEntries(animals.map(a => [a.id, a]));
        const label = (id) => (id && byId[id] ? esc(animalLabel(byId[id])) : '');

        this.container.innerHTML = `
            <div class="panel log">
                <h2>Breeding log</h2>
                <table>
                    <thead><tr><th>When</th><th>Event</th><th>Animal</th><th>With</th><th>Notes</th></tr></thead>
                    <tbody>${events.map(ev => `
                        <tr class="ev-${esc(ev.kind)}">
                            <td>${fmtTime(ev.at)}</td><td>${esc(ev.kind)}</td>
                            <td>${label(ev.animal_id)}</td><td>${label(ev.other_id)}</td>
                            <td>${esc(ev.notes)}</td>
                        </tr>`).join('') || '<tr><td colspan="5" class="empty">Nothing yet</td></tr>'}
                    </tbody>
                </table>
            </div>`;
    }
}
