// "search" on the YouTube tab that is already open: the same tab goes to the results page; no other site, no empty query, nothing else is touched.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const tabs = new Map([
  [2, { id: 2, url: 'https://www.youtube.com/', title: 'YouTube', incognito: false, active: true, windowId: 1, status: 'complete' }],
  [3, { id: 3, url: 'https://example.com/', title: 'Example', incognito: false, active: false, windowId: 1, status: 'complete' }],
]);
let created = 0;
const event = { addListener() {} };
const context = vm.createContext({
  URL, WebSocket: { OPEN: 1, CONNECTING: 0 }, navigator: { userAgent: 'Chrome/130' }, fetch: async () => { throw new Error('offline'); },
  setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout, document: {}, location: {}, window: {}, isFinite, Math, Number, encodeURIComponent,
  chrome: {
    tabs: {
      query: async () => [...tabs.values()], get: async (id) => tabs.get(id),
      update: async (id, p) => { Object.assign(tabs.get(id), p.url ? { url: p.url, title: 'results - YouTube', status: 'complete' } : p); return tabs.get(id); },
      remove: async () => {}, create: async () => { created += 1; return {}; },
    },
    windows: { update: async () => {} }, scripting: { executeScript: async () => [] },
    action: { setBadgeText() {}, setBadgeBackgroundColor() {}, onClicked: event },
    runtime: { id: 'ext-id', onInstalled: event, onStartup: event, onMessage: event, getManifest: () => ({ version: '2.0.0' }), reload() {} },
    storage: { local: { get: async () => ({}), set: async () => {} } }, alarms: { create() {}, onAlarm: event },
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8'), context);
const run = (id, extra) => context.command({ action: 'search', tab_id: id, expected_url: tabs.get(id).url, ...extra });

(async () => {
  let r = await run(2, { query: '  gazaarish   music ' });
  assert.equal(r.success, true); assert.equal(r.searched, 'gazaarish music'); assert.equal(created, 0, 'no new tab');
  assert.equal(tabs.get(2).url, 'https://www.youtube.com/results?search_query=gazaarish%20music', 'the same tab went to the results');
  r = await run(2, { query: 'گزارش میوزک' }); assert.equal(r.searched, 'گزارش میوزک', 'Urdu text survives the address');
  await assert.rejects(run(2, { query: '   ' }), /what to search/);
  await assert.rejects(run(3, { query: 'x' }), /limited to YouTube/);
  assert.equal(tabs.get(3).url, 'https://example.com/', 'another site is never navigated');
  console.log('Search checks passed: same tab, no new tab, Urdu text, empty query, YouTube only.');
})().catch((e) => { console.error(e); process.exit(1); });
