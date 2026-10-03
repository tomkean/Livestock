/**
 * View.js
 * Base class for all UI views (same pattern as Sentinel).
 * Handles mounting and cleanup of intervals and socket subscriptions.
 */
export class View {
    constructor(containerId = 'dynamic-content') {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.intervals = [];
    }

    async render() {
        throw new Error("Render method must be implemented");
    }

    destroy() {
        this.intervals.forEach(id => clearInterval(id));
        this.intervals = [];
    }

    addInterval(callback, ms) {
        const id = setInterval(callback, ms);
        this.intervals.push(id);
        return id;
    }
}
