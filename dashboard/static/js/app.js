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
});

// ---- API helpers ----
async function apiGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

async function apiPost(url, body = {}) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
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

// ---- WebSocket ----
let ws = null;
function connectWS() {
    try {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws`);
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'audit_progress') {
                    showToast(data.message, 'info');
                }
            } catch (e) { /* ignore */ }
        };
        ws.onclose = () => { setTimeout(connectWS, 5000); };
    } catch (e) { /* WebSocket not available */ }
}
connectWS();
