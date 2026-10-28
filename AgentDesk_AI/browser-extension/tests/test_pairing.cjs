// Pairing and bridge-connection checks for background.js using mocked Chrome APIs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function load({ stored = {}, fetchImpl } = {}) {
  const store = { ...stored };
  const badges = [];
  const fetches = [];
  const listeners = [];
  const sockets = [];
  const event = { addListener() {} };
  class FakeSocket {
    constructor(url) { this.url = url; this.readyState = 0; sockets.push(this); }
    send() {}
    close() {}
  }
  FakeSocket.OPEN = 1; FakeSocket.CONNECTING = 0;
  const context = vm.createContext({
    URL, WebSocket: FakeSocket,
    navigator: { userAgent: 'Chrome/130' },
    fetch: async (url, options) => { fetches.push({ url, options }); return fetchImpl ? fetchImpl(url, options) : { ok: true, json: async () => ({ token: 'bridge-token' }) }; },
    setInterval: () => 0, clearInterval() {},
    chrome: {
      runtime: { id: 'ext-id', onInstalled: event, onStartup: event, onMessage: { addListener: fn => listeners.push(fn) } },
      storage: { local: {
        get: async key => ({ [key]: store[key] }),
        set: async values => { Object.assign(store, values); },
      } },
      action: { setBadgeText: o => badges.push(o.text), setBadgeBackgroundColor() {}, onClicked: event },
      alarms: { create() {}, onAlarm: event },
      tabs: {}, windows: {}, scripting: {},
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8'), context);
  // background.js connects once on load; let that attempt finish before asserting.
  const settled = new Promise(resolve => setTimeout(resolve, 20));
  return { context, store, badges, fetches, listeners, sockets, settled };
}

const TOKEN = 'a'.repeat(43);
const GOOD_SENDER = { id: 'ext-id', url: 'http://127.0.0.1:8000/browser-extension/setup.html' };

(async () => {
  // 1. Only the setup page of this extension, with a real-length token, may pair.
  let env = load();
  const accept = (m, s) => vm.runInContext('acceptPairing', env.context)(m, s);
  assert.equal(accept({ type: 'agentx-pair', token: TOKEN }, GOOD_SENDER), true);
  assert.equal(accept({ type: 'agentx-pair', token: 'short' }, GOOD_SENDER), false, 'short token');
  assert.equal(accept({ type: 'agentx-pair', token: TOKEN }, { ...GOOD_SENDER, url: 'https://evil.example/browser-extension/setup.html' }), false, 'foreign page');
  assert.equal(accept({ type: 'agentx-pair', token: TOKEN }, { ...GOOD_SENDER, url: 'http://127.0.0.1:8000/other.html' }), false, 'other local page');
  assert.equal(accept({ type: 'agentx-pair', token: TOKEN }, { ...GOOD_SENDER, id: 'other-ext' }), false, 'other extension');
  assert.equal(accept({ type: 'something-else', token: TOKEN }, GOOD_SENDER), false, 'wrong type');

  // 2. Unpaired: no network call at all, badge asks to pair.
  env = load();
  await env.settled;
  assert.equal(env.fetches.length, 0, 'must not contact the backend when unpaired');
  assert.ok(env.badges.includes('PAIR'));

  // 3. Paired: the API token is sent to the backend as a Bearer header.
  env = load({ stored: { apiToken: TOKEN } });
  await env.settled;
  assert.equal(env.fetches.length, 1);
  assert.equal(env.fetches[0].options.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(env.fetches[0].url, 'http://127.0.0.1:8000/browser/connect-token');
  assert.equal(env.sockets.length, 1);

  // 4. A stored value that is too short is ignored.
  env = load({ stored: { apiToken: 'tiny' } });
  await env.settled;
  assert.equal(env.fetches.length, 0);

  // 5. A rejected token (backend 401) leaves no socket open.
  env = load({ stored: { apiToken: TOKEN }, fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({}) }) });
  await env.settled;
  assert.equal(env.sockets.length, 0);

  // 6. The message listener stores the token only for an accepted sender.
  env = load();
  const listener = env.listeners[0];
  let reply;
  assert.equal(listener({ type: 'agentx-pair', token: TOKEN }, { ...GOOD_SENDER, id: 'nope' }, r => { reply = r; }), false);
  assert.equal(env.store.apiToken, undefined);
  assert.equal(listener({ type: 'agentx-pair', token: TOKEN }, GOOD_SENDER, r => { reply = r; }), true);
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(env.store.apiToken, TOKEN);
  assert.equal(reply.ok, true);

  console.log('Pairing checks passed: sender validation, unpaired no-contact, Bearer header, rejection handling.');
})().catch(error => { console.error(error); process.exitCode = 1; });
