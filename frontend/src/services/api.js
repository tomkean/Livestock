async function request(method, url, body) {
    const opts = { method, headers: {} };
    if (body instanceof FormData) {
        opts.body = body;
    } else if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
        let detail = await res.text();
        try { detail = JSON.parse(detail).detail ?? detail; } catch (e) {}
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return res.json();
}

export const api = {
    get: (url) => request('GET', url),
    post: (url, body) => request('POST', url, body),
    put: (url, body) => request('PUT', url, body),
    patch: (url, body) => request('PATCH', url, body),
    del: (url) => request('DELETE', url)
};
