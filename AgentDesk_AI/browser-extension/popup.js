// The popup only shows what background.js saved and asks it to reconnect; it never touches pages.
const el = (id) => document.getElementById(id);
const ago = (iso) => { if (!iso) return 'never'; const s = Math.round((Date.now() - Date.parse(iso)) / 1000); return s < 90 ? `${s} s ago` : `${Math.round(s / 60)} min ago`; };

function show(st) {
  const s = st || {};
  el('conn').textContent = s.connected ? 'connected' : 'disconnected';
  el('conn').className = s.connected ? 'ok' : 'bad';
  el('via').textContent = s.via || '-';
  el('paired').textContent = s.paired ? 'yes' : 'no';
  el('paired').className = s.paired ? 'ok' : 'bad';
  el('version').textContent = s.version || '-';
  el('browser').textContent = s.browser || '-';
  el('backend').textContent = s.backend || '-';
  el('pong').textContent = ago(s.last_pong);
  el('attempts').textContent = String(s.attempts ?? 0);
  el('err').textContent = s.last_error ? `Last problem: ${s.last_error}` : '';
}

async function refresh(what) {
  try { show(await chrome.runtime.sendMessage({ type: 'agentx-popup', what })); }
  catch { show((await chrome.storage.local.get('status')).status); }
}

el('reconnect').addEventListener('click', () => { void refresh('reconnect'); setTimeout(() => void refresh('state'), 1500); });
void refresh('state');
setInterval(() => void refresh('state'), 3000);
