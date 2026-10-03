/**
 * ScreenCaptureService.js
 * Handles in-browser game screen capture via navigator.mediaDevices.getDisplayMedia.
 * Adapted from Sentinel's ScreenCaptureService: uploads to /api/captures and has no auth.
 */

class ScreenCaptureManager {
    constructor() {
        this.stream = null;
        this.videoEl = null;
        this.canvasEl = null;
        this.audioContext = null;
        this.statusListeners = [];
    }

    onStatusChange(cb) {
        if (typeof cb === 'function') this.statusListeners.push(cb);
    }

    _notify(status) {
        this.statusListeners.forEach(cb => cb(status));
    }

    isCapturing() {
        return !!(this.stream && this.stream.active && this.stream.getVideoTracks().some(t => t.readyState === 'live'));
    }

    async startCapture() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
            if (!window.isSecureContext) {
                throw new Error("Screen capture needs a secure origin. Add this address to chrome://flags/#unsafely-treat-insecure-origin-as-secure.");
            }
            throw new Error("Screen capture API not supported in this browser.");
        }

        try {
            this.stream = await navigator.mediaDevices.getDisplayMedia({
                video: {
                    displaySurface: "monitor",
                    cursor: "never",
                    frameRate: { ideal: 5, max: 30 }
                },
                audio: false
            });

            // Off-screen hidden video element continuously decodes incoming stream frames
            if (!this.videoEl) {
                this.videoEl = document.createElement('video');
                this.videoEl.autoplay = true;
                this.videoEl.muted = true;
                this.videoEl.playsInline = true;
                this.videoEl.style.display = 'none';
                document.body.appendChild(this.videoEl);
            }
            this.videoEl.srcObject = this.stream;
            await this.videoEl.play().catch(e => console.warn("[ScreenCapture] Video autoplay muted:", e));

            if (!this.canvasEl) {
                this.canvasEl = document.createElement('canvas');
            }

            // Silent audio keeps the background tab from being throttled while gaming
            this._startKeepAliveAudio();

            const videoTrack = this.stream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.onended = () => {
                    console.log("[ScreenCapture] Screen stream ended by user.");
                    this.stopCapture();
                };
            }

            this._notify('active');
            return true;
        } catch (err) {
            console.error("[ScreenCapture] Failed to initialize screen capture:", err);
            this.stopCapture();
            throw err;
        }
    }

    stopCapture() {
        if (this.stream) {
            this.stream.getTracks().forEach(t => {
                try { t.stop(); } catch (e) {}
            });
            this.stream = null;
        }
        if (this.videoEl) {
            this.videoEl.srcObject = null;
        }
        this._stopKeepAliveAudio();
        this._notify('inactive');
    }

    async grabFrameBlob(quality = 0.92) {
        if (!this.isCapturing()) {
            throw new Error("Screen stream is not active.");
        }

        if (!this.videoEl || !this.videoEl.videoWidth) {
            await new Promise(resolve => setTimeout(resolve, 150));
        }

        const width = this.videoEl.videoWidth || 1920;
        const height = this.videoEl.videoHeight || 1080;

        this.canvasEl.width = width;
        this.canvasEl.height = height;

        const ctx = this.canvasEl.getContext('2d');
        ctx.drawImage(this.videoEl, 0, 0, width, height);

        return new Promise((resolve, reject) => {
            this.canvasEl.toBlob(blob => {
                if (blob) resolve(blob);
                else reject(new Error("Failed to generate JPEG blob from canvas."));
            }, 'image/jpeg', quality);
        });
    }

    async uploadCapture(blob) {
        const formData = new FormData();
        formData.append('file', blob, `capture_${Date.now()}.jpg`);
        const res = await fetch('/api/captures', { method: 'POST', body: formData });
        if (!res.ok) {
            throw new Error(`Upload failed (${res.status}): ${await res.text()}`);
        }
        return await res.json();
    }

    _startKeepAliveAudio() {
        try {
            if (!this.audioContext) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (!AudioCtx) return;
                this.audioContext = new AudioCtx();
            }
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume().catch(() => {});
            }
            const osc = this.audioContext.createOscillator();
            const gain = this.audioContext.createGain();
            gain.gain.value = 0.0001; // Inaudible
            osc.connect(gain);
            gain.connect(this.audioContext.destination);
            osc.start();
            this._keepAliveOsc = osc;
        } catch (e) {
            console.debug("[ScreenCapture] Keepalive audio notice:", e);
        }
    }

    _stopKeepAliveAudio() {
        if (this._keepAliveOsc) {
            try { this._keepAliveOsc.stop(); } catch (e) {}
            this._keepAliveOsc = null;
        }
    }
}

export const ScreenCaptureService = new ScreenCaptureManager();
