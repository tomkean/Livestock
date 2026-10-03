/**
 * socket.js
 * WebSocket link to the backend. Reconnects automatically and re-announces whether this browser is a capturer.
 */

const handlers = {};
let ws = null;
let capturer = false;

export function on(type, callback) {
    (handlers[type] ||= []).push(callback);
}

export function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
        return true;
    }
    return false;
}

export function setCapturer(value) {
    capturer = value;
    send({ type: 'hello', capturer });
}

export function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
        send({ type: 'hello', capturer });
        (handlers.open || []).forEach(cb => cb());
    };
    ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch (err) { return; }
        (handlers[msg.type] || []).forEach(cb => cb(msg));
    };
    ws.onclose = () => {
        (handlers.close || []).forEach(cb => cb());
        setTimeout(connect, 2000);
    };
}
