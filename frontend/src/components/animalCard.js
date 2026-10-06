import { esc, media } from '../ui.js';
import { lambStatus, parseTime } from './lambTimer.js';

export const GENES = ['D', 'L', 'Y', 'F', 'H'];
export const GENE_NAMES = { D: 'Dung', L: 'Lifespan', Y: 'Yield', F: 'Fertility', H: 'Hardiness' };
export const SPECIES_ICON = { cow: '🐄', sheep: '🐑' };

function dot(allele, gene, small) {
    return `<span class="dot a-${allele === '?' ? 'U' : allele}${small ? ' small' : ''}"
        title="${GENE_NAMES[gene]}">${gene}</span>`;
}

function herdDot(herd, small) {
    return `<span class="dot herd${small ? ' small' : ''}" title="Herd">${herd ?? '?'}</span>`;
}

/** Gene circles laid out like the in-game card: expressed row on top, carried row underneath. */
export function geneDots(a) {
    const top = [...a.genes_top].map((g, i) => dot(g, GENES[i], false)).join('') + herdDot(a.herd_top, false);
    const bottom = a.genes_bottom
        ? [...a.genes_bottom].map((g, i) => dot(g, GENES[i], true)).join('') + herdDot(a.herd_bottom, true)
        : '';
    return `<div class="genes"><div class="gene-row">${top}</div>${bottom ? `<div class="gene-row">${bottom}</div>` : ''}</div>`;
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
        a.status !== 'alive' ? `<span class="tag gone">${esc(a.status)}</span>` : ''
    ].join('');
    const lamb = a.status === 'alive' ? lambStatus(a) : null;
    const timer = lamb ? `<div class="lamb-timer${lamb.due ? ' due' : ''}" data-animal="${a.id}">${esc(lamb.text)}</div>` : '';
    // Latest conditions from automatic capture. Below 70% overall it won't breed; low food is the starvation warning.
    const seen = a.seen_at ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(a.seen_at) ? a.seen_at : a.seen_at + 'Z') : null;
    const ago = seen ? Math.max(0, Math.round((Date.now() - seen) / 60000)) : null;
    const conditions = a.overall == null ? '' : `
        <div class="conditions${a.overall < 70 || (a.food != null && a.food < 50) ? ' low' : ''}">
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
            ${timer}
            <div class="card-tags">${badges}</div>
        </div>`;
}
