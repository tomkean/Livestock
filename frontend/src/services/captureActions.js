import { ScreenCaptureService } from './ScreenCaptureService.js';
import { send } from './socket.js';
import { toast } from '../ui.js';

/** Grab a frame from this browser's shared screen and upload it. */
export async function captureLocal() {
    try {
        const blob = await ScreenCaptureService.grabFrameBlob();
        await ScreenCaptureService.uploadCapture(blob);
    } catch (e) {
        toast(`Capture failed: ${e.message}`, 'error');
    }
}

/** Capture here if this browser is sharing the screen, otherwise ask the browser that is. */
export async function requestCapture(delaySeconds = 0) {
    if (delaySeconds > 0) {
        toast(`Capturing in ${delaySeconds}s. Switch to the game.`);
        await new Promise(resolve => setTimeout(resolve, delaySeconds * 1000));
    }
    if (ScreenCaptureService.isCapturing()) {
        await captureLocal();
    } else if (!send({ type: 'request_capture' })) {
        toast('Not connected to the backend', 'error');
    }
}
