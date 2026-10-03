import { esc, media } from '../ui.js';

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

export function animalLabel(a) {
    return `${SPECIES_ICON[a.species] || ''} ${a.code}`;
}

export function animalCardHtml(a) {
    const badges = [
        a.pregnant ? '<span class="tag pregnant">Pregnant</span>' : '',
        a.origin === 'ranch' ? '<span class="tag">Ranch</span>' : '',
        a.status !== 'alive' ? `<span class="tag gone">${esc(a.status)}</span>` : ''
    ].join('');
    const name = a.name_image
        ? `<img class="name-img" src="${media(a.name_image)}" alt="">`
        : '<span class="name-missing">no name image</span>';
    return `
        <div class="animal-card${a.status !== 'alive' ? ' gone' : ''}" data-id="${a.id}">
            <div class="card-head">
                <span class="code">${animalLabel(a)}</span>
                <span class="sex">${a.sex === 'F' ? '♀' : '♂'}</span>
            </div>
            <div class="card-name">${name}</div>
            ${geneDots(a)}
            <div class="card-tags">${badges}</div>
        </div>`;
}
