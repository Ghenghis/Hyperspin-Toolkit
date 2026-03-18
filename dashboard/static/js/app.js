/* HyperSpin Extreme Toolkit — Dashboard JavaScript */

// ---- Toast notifications ----
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 4000);
}

// ---- Active nav link ----
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (path === '/' && href === '/')) {
            link.classList.add('active');
        }
    });
    checkAIStatus();
    loadHealthBadge();
});

// ---- Sidebar health badge (global — loads on every page) ----
async function loadHealthBadge() {
    try {
        const data = await apiGet('/api/stats');
        const el = document.getElementById('health-score');
        if (!el) return;
        const score = data.avg_health_score || 0;
        el.textContent = score + '%';
        el.style.color = score >= 75 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--danger)';
    } catch (e) { /* sidebar badge is non-critical */ }
}

// ---- API helpers with error body extraction ----
async function apiGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try { const body = await resp.json(); detail = body.error || detail; } catch (_) {}
        throw new Error(detail);
    }
    return resp.json();
}

async function apiPost(url, body = {}) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try { const b = await resp.json(); detail = b.error || detail; } catch (_) {}
        throw new Error(detail);
    }
    return resp.json();
}

// ---- Button protection helper ----
function withButton(btnId, label, asyncFn) {
    return async function (...args) {
        const btn = document.getElementById(btnId);
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> ' + label + '...'; }
        try {
            await asyncFn(...args);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = label; }
        }
    };
}

// ---- Full audit ----
async function runFullAudit() {
    const btn = document.getElementById('audit-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Auditing...';
    }
    showToast('Starting full ecosystem audit...', 'info');

    try {
        const data = await apiPost('/api/audit/full');
        showToast('Audit complete!', 'success');
        loadHealthBadge();
        if (typeof loadStats === 'function') loadStats();
        if (typeof loadSystems === 'function') loadSystems();
    } catch (e) {
        showToast('Audit failed: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Run Full Audit';
        }
    }
}

// ---- AI status check ----
async function checkAIStatus() {
    try {
        const data = await apiGet('/api/ai/status');
        const dot = document.getElementById('ai-status');
        if (!dot) return;
        const providers = data.providers || {};
        const anyOnline = Object.values(providers).some(v => v);
        dot.className = `status-dot ${anyOnline ? 'online' : 'offline'}`;
        dot.title = anyOnline
            ? 'AI: ' + Object.entries(providers).filter(([,v]) => v).map(([k]) => k).join(', ')
            : 'AI: No providers available';
    } catch (e) {
        const dot = document.getElementById('ai-status');
        if (dot) {
            dot.className = 'status-dot offline';
            dot.title = 'AI: Cannot reach backend';
        }
    }
}

async function checkAI() {
    showToast('Checking AI providers...', 'info');
    try {
        const data = await apiGet('/api/ai/status');
        const providers = data.providers || {};
        const lines = Object.entries(providers).map(
            ([name, avail]) => `${name}: ${avail ? 'Online' : 'Offline'}`
        );
        showToast(lines.join(' | '), lines.some(l => l.includes('Online')) ? 'success' : 'error');
        checkAIStatus();
    } catch (e) {
        showToast('AI check failed: ' + e.message, 'error');
    }
}

// ---- WebSocket with event dispatching ----
let ws = null;
const _wsHandlers = {};

function onWsEvent(eventType, handler) {
    if (!_wsHandlers[eventType]) _wsHandlers[eventType] = [];
    _wsHandlers[eventType].push(handler);
}

function _dispatchWsEvent(data) {
    const eventType = data.event || data.type || '';
    // Exact match handlers
    if (_wsHandlers[eventType]) {
        _wsHandlers[eventType].forEach(h => { try { h(data); } catch(_) {} });
    }
    // Wildcard prefix handlers (e.g. "update.*" matches "update.applied")
    for (const pattern of Object.keys(_wsHandlers)) {
        if (pattern.endsWith('*') && eventType.startsWith(pattern.slice(0, -1))) {
            _wsHandlers[pattern].forEach(h => { try { h(data); } catch(_) {} });
        }
    }
}

function connectWS() {
    try {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws`);
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                _dispatchWsEvent(data);
                // Legacy: toast for audit progress
                if ((data.type === 'audit_progress' || data.event === 'audit_progress') && data.message) {
                    showToast(data.message, 'info');
                }
            } catch (e) { /* ignore non-JSON */ }
        };
        ws.onclose = () => { setTimeout(connectWS, 5000); };
        ws.onerror = () => { /* reconnect handled by onclose */ };
    } catch (e) { /* WebSocket not available */ }
}
connectWS();

// ---- Register global WS event handlers ----
onWsEvent('update.*', () => { loadHealthBadge(); });
onWsEvent('rollback.*', () => { loadHealthBadge(); });
onWsEvent('snapshot.*', () => { loadHealthBadge(); });
onWsEvent('broadcast', (data) => {
    if (data.data && data.data.message) showToast(data.data.message, 'info');
});
