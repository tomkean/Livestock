/**
 * Lambs grow up 60 minutes after birth (measured on a test server), and that's when horns show and they start
 * breeding. Like cloning saplings before they start crossbreeding, they need sorting before then.
 */
export const GROWTH_MINUTES = 60;

export function parseTime(iso) {
    if (!iso) return null;
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
}

export function growsUpAt(a) {
    const born = parseTime(a.born_at);
    return born ? new Date(born.getTime() + GROWTH_MINUTES * 60000) : null;
}

const clock = (d) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

/** What a lamb needs: { text, due } where due means "sort it now". Null for animals with nothing pending. */
export function lambStatus(a, now = new Date()) {
    const grown = growsUpAt(a);
    if (grown && grown > now) {
        const mins = Math.ceil((grown - now) / 60000);
        return { text: `Grows up ${clock(grown)} (${mins} min)`, due: false, at: grown };
    }
    if (a.sex === '?') {
        return { text: grown ? 'Grown: check horns and sort' : 'Sex unknown: check horns', due: true, at: grown };
    }
    return null;
}
