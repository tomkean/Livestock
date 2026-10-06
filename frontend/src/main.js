import './style.css';
import { connect, on, send, setCapturer } from './services/socket.js';
import { ScreenCaptureService } from './services/ScreenCaptureService.js';
import { captureLocal, requestCapture } from './services/captureActions.js';
import { refreshCaptureBadge, toast } from './ui.js';
import { HerdView } from './views/HerdView.js';
import { CaptureView } from './views/CaptureView.js';
import { LogView } from './views/LogView.js';
import { PlanView } from './views/PlanView.js';
import { PoolsView } from './views/PoolsView.js';
import { api } from './services/api.js';
import { lambStatus } from './components/lambTimer.js';
import { isAutoOn, onAutoChange, startAuto, stopAuto } from './services/autoCapture.js';

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

function updateShareStatus() {
    const pill = document.getElementById('capture-status');
    if (ScreenCaptureService.isCapturing()) {
        pill.textContent = 'Sharing this screen';
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
document.getElementById('btn-capture').addEventListener('click', () => requestCapture());

// Automatic capture runs on the browser sharing the screen; any device can switch it on or off.
let autoRemote = false;
function showAuto(on) {
    const btn = document.getElementById('btn-auto');
    btn.textContent = on ? 'Auto: on' : 'Auto: off';
    btn.classList.toggle('primary', on);
}
document.getElementById('btn-auto').addEventListener('click', () => {
    if (ScreenCaptureService.isCapturing()) {
        isAutoOn() ? stopAuto() : startAuto();
    } else if (!send({ type: 'auto_capture', enabled: !autoRemote })) {
        toast('Not connected to the backend', 'error');
    } else if (sharers === 0) {
        toast('No browser is sharing the gaming PC screen', 'warn');
    }
});
onAutoChange(on => {
    showAuto(on);
    send({ type: 'auto_status', enabled: on });
});
on('auto_capture', msg => {
    if (!ScreenCaptureService.isCapturing()) return;
    msg.enabled ? startAuto() : stopAuto();
});
on('auto_status', msg => {
    autoRemote = msg.enabled;
    if (!ScreenCaptureService.isCapturing()) showAuto(msg.enabled);
});
let lastSeenToast = 0;
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
    if (status !== 'active') stopAuto();
    updateShareStatus();
});

on('status', msg => {
    sharers = msg.capturers;
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
        badge.textContent = plan.moves.length;
        badge.classList.toggle('hidden', plan.moves.length === 0);
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
