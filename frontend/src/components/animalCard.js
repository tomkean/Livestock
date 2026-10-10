import { esc, media } from '../ui.js';
import { lambStatus, parseTime } from './lambTimer.js';

export const GENES = ['D', 'L', 'Y', 'F', 'H'];
export const GENE_NAMES = { D: 'Dung', L: 'Lifespan', Y: 'Yield', F: 'Fertility', H: 'Hardiness' };
export const SPECIES_ICON = { cattle: '🐄', sheep: '🐑' };

function dot(allele, gene, small) {
    return `<span class="dot a-${allele === '?' ? 'U' : allele}${small ? ' small' : ''}"
        title="${GENE_NAMES[gene]}">${gene}</span>`;
}

function herdDot(herd, small) {
    return `<span class="dot herd${small ? ' small' : ''}" title="Herd">${herd ?? '?'}</span>`;
}

const LETTER_NAME = { G: 'Good', O: 'Ok', B: 'Bad' };

/**
 * Gene circles: the top row as on the in-game card, and under each gene a column of the hidden copies not yet ruled
 * out, most likely first (fainter when less likely; the chance on hover). One circle under a gene means it's settled.
 * On a test server, the captured second row is ringed, so you can see how the inference is doing.
 */
export function geneDots(a) {
    const top = [...a.genes_top].map((g, i) => dot(g, GENES[i], false)).join('') + herdDot(a.herd_top, false);
    const hidden = a.hidden || [];
    if (!hidden.some(col => col.length)) {
        return `<div class="genes"><div class="gene-row">${top}</div></div>`;
    }
    const columns = GENES.map((gene, i) => {
        const truth = a.genes_bottom && a.genes_bottom[i] !== '?' ? a.genes_bottom[i] : null;
        const options = hidden[i] || [];
        const cells = options.map(([letter, p]) => `<span class="dot small a-${letter}${letter === truth ? ' truth' : ''}"
            style="opacity:${Math.max(0.35, Math.min(1, 0.35 + p))}"
            title="${GENE_NAMES[gene]}: hidden copy ${LETTER_NAME[letter]} - ${p >= 0.995 ? 'certain' : Math.round(p * 100) + '%'}${letter === truth ? ' (the second row says so)' : ''}">${letter}</span>`).join('');
        return `<div class="hidden-col">${cells || '<span class="dot small a-U" title="unknown">?</span>'}</div>`;
    }).join('');
    return `<div class="genes"><div class="gene-row">${top}</div><div class="gene-row hidden-row">${columns}</div></div>`;
}

/** "Not seen for 25 min" once automatic capture hasn't seen a live animal for 10 minutes. Information only. */
function unseenTag(a) {
    if (a.status !== 'alive' || !a.seen_at) return '';
    const seen = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.seen_at) ? a.seen_at : a.seen_at + 'Z');
    const minutes = Math.round((Date.now() - seen) / 60000);
    if (minutes < 10) return '';
    const text = minutes < 120 ? `${minutes} min` : minutes < 2880 ? `${Math.round(minutes / 60)} h` : `${Math.round(minutes / 1440)} days`;
    return `<span class="tag unseen" title="Automatic capture last saw this card ${seen.toLocaleString()}">Not seen for ${text}</span>`;
}

export function displayName(a) {
    return a.name || a.code;
}

export function animalLabel(a) {
    return `${SPECIES_ICON[a.species] || ''} ${displayName(a)}`;
}

export function animalCardHtml(a) {
    const free = parseTime(a.free_again_at);
    const cooling = a.status === 'alive' && !a.pregnant && free && free > new Date();
    const badges = [
        a.pregnant ? '<span class="tag pregnant">Pregnant</span>' : '',
        cooling ? `<span class="tag free" title="Cooldown after her last lamb">Free again ${free.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span>` : '',
        a.origin === 'ranch' ? '<span class="tag">Ranch</span>' : '',
        a.status !== 'alive' ? `<span class="tag gone">${esc(a.status)}</span>` : '',
        unseenTag(a)
    ].join('');
    const lamb = a.status === 'alive' ? lambStatus(a) : null;
    const timer = lamb ? `<div class="lamb-timer${lamb.due ? ' due' : ''}" data-animal="${a.id}">${esc(lamb.text)}</div>` : '';
    // Latest conditions from automatic capture. Below 70% overall it won't breed; low food is the starvation warning.
    const seen = a.seen_at ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.seen_at) ? a.seen_at : a.seen_at + 'Z') : null;
    const ago = seen ? Math.max(0, Math.round((Date.now() - seen) / 60000)) : null;
    const conditions = a.overall == null ? '' : `
        <div class="conditions${a.overall < 70 || (a.food != null && a.food < 10) ? ' low' : ''}">
            Food ${a.food ?? '?'}% · Space ${a.personal_space ?? '?'}% · Overall <b>${a.overall}%</b>
            <span class="muted">${ago == null ? '' : ago < 1 ? 'just now' : ago < 120 ? `${ago} min ago` : `${Math.round(ago / 60)} h ago`}</span>
        </div>`;
    // Chance of Good/Good on every target gene - on a live server the only way to know a god animal when you have one.
    const gg = a.good_good || {};
    const godChance = a.target_chance == null ? '' : `
        <div class="god-chance${a.target_chance >= 0.9 ? ' high' : ''}" title="Chance of Good/Good, per target gene: ${
            esc(Object.entries(gg).map(([g, p]) => `${g} ${Math.round(p * 100)}%`).join(', '))}">
            God chance <b>${a.target_chance >= 0.995 ? '100' : a.target_chance < 0.005 && a.target_chance > 0 ? '<1' : Math.round(a.target_chance * 100)}%</b>
            <span class="muted">${esc(Object.entries(gg).map(([g, p]) => `${g}${Math.round(p * 100)}`).join(' '))}</span>
        </div>`;
    // The name image is what matches the animal in game, in whatever script its name is written.
    const nameImage = a.name_image ? `<img class="name-img" src="${media(a.name_image)}" alt="">` : '';
    return `
        <div class="animal-card${a.status !== 'alive' ? ' gone' : ''}" data-id="${a.id}">
            <div class="card-head">
                <span class="code">${SPECIES_ICON[a.species] || ''} ${esc(displayName(a))}</span>
                <span class="sex">${a.sex === 'F' ? '♀' : a.sex === 'M' ? '♂' : '?'}</span>
            </div>
            <div class="card-name">${nameImage}${a.name && a.name !== a.code ? `<span class="tag id">${esc(a.code)}</span>` : ''}</div>
            ${geneDots(a)}
            ${godChance}
            ${conditions}
            ${a.wool_per_shear ? `<div class="hint">Wool ${a.wool_per_shear} per shear (regrows in ${Math.round(a.wool_regrow_min)} min)</div>` : ''}
            ${timer}
            <div class="card-tags">${badges}</div>
        </div>`;
}
