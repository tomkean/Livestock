import './style.css';
import { connect, on, setCapturer } from './services/socket.js';
import { ScreenCaptureService } from './services/ScreenCaptureService.js';
import { captureLocal, requestCapture } from './services/captureActions.js';
import { refreshCaptureBadge, toast } from './ui.js';
import { HerdView } from './views/HerdView.js';
import { CaptureView } from './views/CaptureView.js';
import { LogView } from './views/LogView.js';
import { PlanView } from './views/PlanView.js';
import { api } from './services/api.js';
import { lambStatus } from './components/lambTimer.js';

const VIEWS = { herd: HerdView, capture: CaptureView, plan: PlanView, log: LogView };
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

ScreenCaptureService.onStatusChange(status => {
    setCapturer(status === 'active');
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

connect();
refreshCaptureBadge();
showTab('herd');
