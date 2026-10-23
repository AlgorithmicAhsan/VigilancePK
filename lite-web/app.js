// Vigilance-PK dashboard core: settings, helpers, sign-in, navigation, status.
// Loaded first; reports.js and lists.js build on the globals defined here.

// Single place to point the dashboard at its backend.
// Change this to your deployed API before publishing the page.
const API_BASE = 'http://localhost:8000';

const $ = (id) => document.getElementById(id);

// --- Untrusted-content helpers (ADR-010) -----------------------------------
// Feed text, list entries and answers all come from outside. Anything put
// into HTML goes through esc(); anything used as a URL goes through safeUrl().
function esc(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Only http(s) survives. Blocks javascript:, data: and friends.
function safeUrl(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return '';
    try {
        const url = new URL(raw, window.location.href);
        return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : '';
    } catch (e) {
        return '';
    }
}

// "2026-10-20T08:15:00+00:00" -> "20 Oct"
function shortDate(iso) {
    const d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) return 'Undated';
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function timeAgo(iso) {
    const d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) return '';
    const mins = Math.round((Date.now() - d) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    return hours < 24 ? `${hours} h ago` : d.toLocaleString('en-GB');
}

// --- Session (ADR-031) -----------------------------------------------------
// The signed token lives in localStorage so a new tab stays signed in until
// it expires (12 h). Safe only because the page escapes all outside text
// and loads no third-party scripts.
const SESSION_KEY = 'vigilance-session';
const session = {
    get() {
        try {
            const s = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
            return s && s.expires_at * 1000 > Date.now() ? s : null;
        } catch (e) { return null; }
    },
    set(s) { try { localStorage.setItem(SESSION_KEY, JSON.stringify(s)); } catch (e) { /* private mode */ } },
    clear() { try { localStorage.removeItem(SESSION_KEY); } catch (e) { /* private mode */ } },
};

class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
}

// Every API call goes through here: adds the token, and turns a 401 into a
// clean sign-out instead of a broken page.
async function api(path, { method = 'GET', body, raw, headers = {} } = {}) {
    const s = session.get();
    const h = { ...headers };
    if (s) h.Authorization = `Bearer ${s.token}`;
    let payload = raw;
    if (body !== undefined) {
        h['Content-Type'] = 'application/json';
        payload = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE}${path}`, { method, headers: h, body: payload });
    if (res.status === 401) {
        signOut('Your session has ended. Please sign in again.');
        throw new ApiError(401, 'Signed out.');
    }
    if (!res.ok) {
        const problem = await res.json().catch(() => ({}));
        throw new ApiError(res.status, typeof problem.detail === 'string' ? problem.detail : `API returned ${res.status}`);
    }
    return res;
}
const apiJson = async (path, opts) => (await api(path, opts)).json();

// --- Sign-in / sign-out ----------------------------------------------------
let currentUser = null;

function showLogin(message = '') {
    currentUser = null;
    document.body.removeAttribute('data-role');
    $('app').hidden = true;
    $('login-view').hidden = false;
    $('login-error').textContent = message;
    $('login-password').value = '';
    $('login-username').focus();
}

function signOut(message = '') {
    session.clear();
    showLogin(message);
}

$('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('login-btn');
    btn.disabled = true;
    $('login-error').textContent = '';
    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: $('login-username').value.trim(), password: $('login-password').value }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Sign-in failed (${res.status}).`);
        session.set(data);
        $('login-password').value = '';
        startApp();
    } catch (err) {
        $('login-error').textContent = err.message === 'Failed to fetch' ? "Can't reach the server." : err.message;
    } finally {
        btn.disabled = false;
    }
});

$('signout-btn').addEventListener('click', () => signOut());

async function startApp() {
    if (!session.get()) return showLogin();
    try {
        currentUser = await apiJson('/auth/me');
    } catch (err) {
        if (err.status !== 401) showLogin(err.message === 'Failed to fetch' ? "Can't reach the server." : err.message);
        return;
    }
    document.body.dataset.role = currentUser.role;
    $('who').textContent = `${currentUser.username} (${currentUser.role})`;
    $('login-view').hidden = true;
    $('app').hidden = false;
    route();
    refreshConnection();
}

// --- Navigation: #reports (default) or #lists ------------------------------
const views = {};  // filled in by reports.js and lists.js: name -> { open() }

function route() {
    if (!currentUser) return;
    const name = location.hash === '#lists' ? 'lists' : 'reports';
    for (const v of ['reports', 'lists']) $(`view-${v}`).hidden = v !== name;
    document.querySelectorAll('.nav a').forEach(a => {
        if (a.dataset.view === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    views[name]?.open();
}
window.addEventListener('hashchange', route);

// --- Status (ADR-013: every value measured or read from the API) ----------
$('status-btn').addEventListener('click', async () => {
    const rows = [];
    const started = performance.now();
    try {
        const stats = await apiJson('/stats');
        rows.push(['API', `Reachable (${Math.round(performance.now() - started)} ms)`]);
        rows.push(['Reports stored', stats.total_logs]);
        if (stats.not_yet_searchable) rows.push(['Not yet searchable', `${stats.not_yet_searchable} (the next sync finishes them)`]);
        rows.push(['Chat model', stats.engine]);
        rows.push(['Gemini key', stats.gemini_key_configured ? 'Configured' : 'Missing']);
        const sync = await apiJson('/sync/status').catch(() => null);
        if (sync?.running) rows.push(['Last sync', 'Running now']);
        else if (sync?.finished_at) {
            const r = sync.result;
            rows.push(['Last sync', sync.error ? `Failed ${timeAgo(sync.finished_at)}`
                : `${timeAgo(sync.finished_at)}: ${r?.new ?? 0} new, ${r?.failed ?? 0} failed`]);
        } else rows.push(['Last sync', 'None since the server started']);
    } catch (err) {
        if (err.status === 401) return;
        rows.push(['API', `Unreachable after ${Math.round(performance.now() - started)} ms`]);
        rows.push(['Detail', err.message]);
    }
    rows.push(['Signed in as', `${currentUser.username} (${currentUser.role})`]);
    rows.push(['Endpoint', API_BASE]);
    $('status-list').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
    $('status-dialog').showModal();
});

async function refreshConnection() {
    if (!currentUser) return;
    const conn = $('conn');
    try {
        await api('/stats');
        conn.dataset.state = 'ok';
        $('conn-label').textContent = 'Connected';
    } catch (e) {
        if (e.status === 401) return;
        conn.dataset.state = 'down';
        $('conn-label').textContent = 'API offline';
    }
}
setInterval(refreshConnection, 30000);

// Boot once every script has loaded and registered its view.
window.addEventListener('DOMContentLoaded', startApp);
