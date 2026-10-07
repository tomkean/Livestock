/**
 * Automatic capture: while on, the browser sharing the gaming PC's screen sends the strip of screen where animal cards
 * appear every couple of seconds. The backend ignores frames with no card, quietly updates known animals and files new
 * ones for confirmation, so just looking at the herd keeps it up to date.
 */
import { ScreenCaptureService } from './ScreenCaptureService.js';

const INTERVAL_MS = 2000;
// Cards appear right of centre: at 3840x2160 the card spans about x 2110-2900, y 400-1400. The vendor's Sale panel and
// dialogue sit a little further right (to x 3300), so the strip reaches that far too.
const STRIP = { x0: 0.53, x1: 0.87, y0: 0.10, y1: 0.80 };

let timer = null;
let busy = false;
const listeners = [];

export function onAutoChange(cb) {
    listeners.push(cb);
}

export function isAutoOn() {
    return timer !== null;
}

function notify() {
    listeners.forEach(cb => cb(isAutoOn()));
}

async function tick() {
    if (busy || !ScreenCaptureService.isCapturing()) return;
    busy = true;
    try {
        const video = ScreenCaptureService.videoEl;
        const W = video.videoWidth, H = video.videoHeight;
        if (!W || !H) return;
        const x = Math.round(W * STRIP.x0), y = Math.round(H * STRIP.y0);
        const w = Math.round(W * (STRIP.x1 - STRIP.x0)), h = Math.round(H * (STRIP.y1 - STRIP.y0));
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(video, x, y, w, h, 0, 0, w, h);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
        const form = new FormData();
        form.append('file', blob, 'strip.jpg');
        await fetch(`/api/autocapture?full_width=${W}&full_height=${H}&crop_x=${x}&crop_y=${y}`, { method: 'POST', body: form });
    } catch (e) {
        console.warn('[AutoCapture]', e);
    } finally {
        busy = false;
    }
}

export function startAuto() {
    if (timer) return;
    timer = setInterval(tick, INTERVAL_MS);
    notify();
}

export function stopAuto() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
    notify();
}
