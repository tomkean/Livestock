import './style.css';
import { connect, on, send, setCapturer } from './services/socket.js';
import { ScreenCaptureService } from './services/ScreenCaptureService.js';
import { captureLocal } from './services/captureActions.js';
import { refreshCaptureBadge, toast } from './ui.js';
import { HerdView } from './views/HerdView.js';
import { CaptureView } from './views/CaptureView.js';
import { LogView } from './views/LogView.js';
import { PlanView } from './views/PlanView.js';
import { PoolsView } from './views/PoolsView.js';
import { api } from './services/api.js';
import { lambStatus } from './components/lambTimer.js';
import { isAutoOn, onAutoChange, setPaused, startAuto, stopAuto } from './services/autoCapture.js';
const AWAY = 'Away';  // the "Where am I?" choice that stops the watching

const VIEWS = { herd: HerdView, capture: CaptureView, pools: PoolsView, plan: PlanView, log: LogView };
let currentView = null;
let sharers = 0;

async function showTab(name) {
    if (currentView) currentView.destroy();
    document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    currentView = new VIEWS[name]();
    try {
        await currentView.render();
    } catch (e) {
        currentView.container.innerHTML = `<div class="panel error">Could not load: ${e.message}</div>`;
    }
}

// What the sharing browser says it shares. Browsers label a window share with its title (usually) or an ID; a title
// that isn't Rust's means the wrong window was picked (Steam, Discord) and every frame would be ignored.
let shareSource = '';
const looksLikeTitle = (label) => label && !/^(screen|window|web-contents-media-stream):/i.test(label);
const notRust = (label) => looksLikeTitle(label) && !/rust/i.test(label);
function updateShareStatus() {
    const pill = document.getElementById('capture-status');
    const label = ScreenCaptureService.isCapturing() ? (ScreenCaptureService.sourceLabel || '') : shareSource;
    pill.title = label ? `Shared: ${label}` : '';
    if (notRust(label)) {
        pill.textContent = `Sharing "${label.slice(0, 30)}" - not Rust?`;
        pill.className = 'pill warn';
    } else if (ScreenCaptureService.isCapturing()) {
        pill.textContent = looksLikeTitle(label) ? `Sharing: ${label.slice(0, 30)}` : 'Sharing this screen';
        pill.className = 'pill live';
    } else if (sharers > 0) {
        pill.textContent = 'Gaming PC screen shared';
        pill.className = 'pill live';
    } else {
        pill.textContent = 'No screen shared';
        pill.className = 'pill';
    }
    currentView?.onShareStatus?.();
}

document.querySelectorAll('#tabs button').forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tab)));

// Sharing the screen means "watch": automatic capture runs whenever this browser shares, except while the player has
// said they're away from the livestock. The chip shows the state on every device.
let remoteWatching = false;
let away = false;
function showWatching() {
    const chip = document.getElementById('btn-auto');
    const sharingHere = ScreenCaptureService.isCapturing();
    const watching = (sharingHere ? isAutoOn() : remoteWatching) && !away;
    chip.textContent = away ? 'Away' : watching ? 'Watching' : 'Not sharing';
    chip.classList.toggle('primary', watching);
    chip.title = away ? 'Away from livestock: frames are ignored. Pick a place in "Where am I?" to start watching again.'
        : watching ? 'The shared screen is being watched: cards and vendor screens are read every 2 seconds.'
        : 'Press Share screen on the gaming PC to start watching.';
}
document.getElementById('btn-auto').addEventListener('click', () => {
    if (!ScreenCaptureService.isCapturing() && !remoteWatching) toast('Share the gaming PC screen to start watching', 'info');
});
onAutoChange(on => {
    showWatching();
    send({ type: 'auto_status', enabled: on, source: ScreenCaptureService.sourceLabel || '' });
});
on('auto_status', msg => {
    remoteWatching = msg.enabled;
    shareSource = msg.source || '';
    showWatching();
    updateShareStatus();
});
// A small live view of the latest frame Auto read: a wrong window shows at a glance. Only on the Capture tab, so the
// game PC spends nothing on it while playing.
const preview = document.getElementById('auto-preview');
setInterval(() => {
    const onCapture = document.querySelector('#tabs button.active')?.dataset.tab === 'capture';
    const watching = onCapture && (ScreenCaptureService.isCapturing() ? isAutoOn() : remoteWatching) && !away;
    preview.classList.toggle('hidden', !watching);
    if (watching) preview.src = `/api/autocapture/last.jpg?t=${Date.now()}`;
}, 5000);
preview.addEventListener('error', () => preview.classList.add('hidden'));
preview.addEventListener('click', () => window.open(preview.src, '_blank'));
let lastSeenToast = 0;
// Where the player is: picked here until Rust+ can tell. Every open app follows the same choice.
const where = document.getElementById('where');
function showWhere(settings) {
    const places = [...((settings?.pools?.rooms) || []).map(r => r.name), 'Vendor'];
    const here = settings?.location || '';
    away = here === AWAY;
    setPaused(away);
    showWatching();
    // No blank choice: not knowing the room is "Somewhere on the farm" (watches, files by sex, moves nobody).
    where.innerHTML = `<option value="Farm" ${here === 'Farm' || !here ? 'selected' : ''}>Somewhere on the farm</option>`
        + `<option value="${AWAY}" ${away ? 'selected' : ''}>Away from livestock</option>`
        + places.map(p => `<option value="${p.replace(/"/g, '&quot;')}" ${p === here ? 'selected' : ''}>${p.replace(/</g, '&lt;')}</option>`).join('');
}
api.get('/api/settings').then(showWhere).catch(() => {});
where.addEventListener('change', async () => {
    try {
        await api.put('/api/settings', { location: where.value });
        away = where.value === AWAY;
        setPaused(away);
        showWatching();
        toast(away ? 'Away from livestock: not watching' : where.value === 'Farm' ? 'Somewhere on the farm: watching, rooms not tracked' : `At ${where.value}`);
    } catch (e) {
        toast(e.message, 'error');
    }
});
on('location', msg => {
    if (where.value !== msg.location) api.get('/api/settings').then(showWhere).catch(() => {});
    currentView?.onAutoSeen?.(msg);  // e.g. Pools: "Take from <here>"
});
// The vendor reader: each offer as it's read, and the sale when the visit ends.
on('vendor_offer', msg => {
    // The verdict: worth to you (your item values) against the book value, and take it or wait for the next offer.
    const verdict = msg.take === undefined ? '' :
        ` - worth ~${msg.worth} to you (book ${msg.book})${msg.unknown ? ', plus an item it can\'t value' : ''}. ` +
        `${msg.take ? 'TAKE IT' : 'TURN IT DOWN'}: ${msg.why}`;
    toast(`${msg.name}, offer ${msg.number}${msg.rare ? ' (rare mood!)' : ''}: ${msg.items}${verdict}`, msg.take === false ? 'warn' : 'info', 15000);
});
on('vendor_refused', msg => toast(`Offers turned down - ${msg.name} stays in the herd`, 'info'));
on('vendor_unsure', msg => toast(`${msg.name}'s offers recorded but NOT marked sold (too valuable to assume). If you did sell, mark it sold on the Herd tab.`, 'warn'));
on('vendor_sold', msg => {
    toast(`Sold ${msg.name} on offer ${msg.number}: ${msg.items}. Not sold? Undo in the Log tab`, 'info');
    currentView?.onAutoSeen?.(msg);
});
on('auto_missing', msg => {
    toast(`Not seen in ${msg.building} for 30 min: ${msg.names.join(', ')} - marked missing`, 'warn');
    currentView?.onAutoSeen?.(msg);
});
on('auto_new', msg => {
    currentView?.onAutoSeen?.(msg);
    const sex = msg.sex === 'M' ? 'ram' : msg.sex === 'F' ? 'ewe' : 'sex unknown';
    toast(`New: ${msg.name} (${msg.lamb ? 'lamb, ' : ''}${sex})${msg.pen ? ' in ' + msg.pen : ''} - registered automatically`, 'info');
});

on('auto_seen', msg => {
    currentView?.onAutoSeen?.(msg);
    if (Date.now() - lastSeenToast > 4000) {
        lastSeenToast = Date.now();
        const low = msg.overall != null && msg.overall < 70;
        toast(`${msg.name}: food ${msg.food ?? '?'}%, overall ${msg.overall ?? '?'}%`, low ? 'warn' : 'info');
    }
});

ScreenCaptureService.onStatusChange(status => {
    setCapturer(status === 'active');
    if (status === 'active') startAuto(); else stopAuto();  // sharing means watching
    showWatching();
    updateShareStatus();
});

on('status', msg => {
    sharers = msg.capturers;
    if (msg.source !== undefined) shareSource = msg.source;
    updateShareStatus();
});
on('capture_request', () => {
    if (ScreenCaptureService.isCapturing()) captureLocal();
});
on('capture_ready', () => {
    toast('Capture received');
    refreshCaptureBadge();
    currentView?.onCapturesChanged?.();
});
on('capture_warning', msg => toast(msg.message, 'warn'));
on('close', () => {
    sharers = 0;
    updateShareStatus();
});

// Header reminder for lambs: they must be sorted by sex before they grow up and start breeding.
async function refreshLambStatus() {
    const el = document.getElementById('lamb-status');
    let animals;
    try {
        animals = await api.get('/api/animals');
    } catch (e) {
        return;
    }
    const pending = animals.map(a => ({ a, st: lambStatus(a) })).filter(x => x.st);
    const due = pending.filter(x => x.st.due);
    const next = pending.filter(x => !x.st.due).sort((x, y) => x.st.at - y.st.at)[0];
    if (due.length) {
        el.textContent = `${due.length} lamb${due.length > 1 ? 's' : ''} to sort now`;
        el.className = 'pill due';
    } else if (next) {
        el.textContent = `Next lamb: ${next.st.text.toLowerCase()}`;
        el.className = 'pill';
    } else {
        el.className = 'pill hidden';
    }
}
setInterval(refreshLambStatus, 30000);
refreshLambStatus();

// Pools tab badge: how many sheep the app wants moved between rooms.
async function refreshMoves() {
    const badge = document.getElementById('moves-badge');
    try {
        const plan = await api.get('/api/pools?species=sheep');
        let skipped = new Set();
        try { skipped = new Set(JSON.parse(localStorage.getItem('livestock.skippedMoves') || '[]')); } catch (e) {}
        const open = plan.moves.filter(m => !skipped.has(`${m.id}>${m.to}`)).length;
        badge.textContent = open;
        badge.classList.toggle('hidden', open === 0);
    } catch (e) {
        badge.classList.add('hidden');
    }
}
setInterval(refreshMoves, 30000);
refreshMoves();
on('auto_seen', () => refreshMoves());
on('capture_ready', () => refreshMoves());

connect();
refreshCaptureBadge();
showTab('herd');
