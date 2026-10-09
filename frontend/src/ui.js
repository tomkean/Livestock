import { api } from './services/api.js';

let toastTimer = null;

export function toast(message, kind = 'info', ms = 4000) {
    const el = document.getElementById('toast');
    el.textContent = message;
    el.className = `show ${kind}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = ''; }, ms);
}

export function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

export function media(path) {
    return `/media/${path}`;
}

// The backend stores UTC without a zone marker.
export function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
    return d.toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export async function refreshCaptureBadge() {
    const badge = document.getElementById('capture-badge');
    try {
        const pending = await api.get('/api/captures');
        badge.textContent = pending.length;
        badge.classList.toggle('hidden', pending.length === 0);
    } catch (e) {
        badge.classList.add('hidden');
    }
}
