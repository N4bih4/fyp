// F4: the new YouTube controls (previous, theatre, captions, quality, loop, skip ad, like, subscribe, now playing, playlist results) and the safety limits
// of the website controls. The page is a small fake DOM; every action must answer with what the page shows AFTERWARDS.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const tabs = new Map([
  [2, { id: 2, url: 'https://www.youtube.com/watch?v=aaa', title: 'First video', incognito: false, active: true, windowId: 1 }],
  [3, { id: 3, url: 'https://example.com/form', title: 'Form', incognito: false, active: false, windowId: 1 }],
  [4, { id: 4, url: 'chrome://extensions/', title: 'Extensions', incognito: false, active: false, windowId: 1 }],
]);
const location = { href: 'https://www.youtube.com/watch?v=aaa', origin: 'https://www.youtube.com', pathname: '/watch' };
const go = (v) => { location.href = `https://www.youtube.com/watch?v=${v}`; };
const video = { currentTime: 10, duration: 300, paused: false, playbackRate: 1, volume: 1, muted: false, loop: false };
let ad = true;
const flexy = { attrs: new Set(), hasAttribute(n) { return this.attrs.has(n); } };
const mk = (extra = {}) => ({ hidden: false, getAttribute: () => null, click() {}, ...extra });
const buttons = {
  '.ytp-prev-button': mk({ click() { go('prev1'); } }),
  '.ytp-size-button': mk({ click() { flexy.attrs.has('theater') ? flexy.attrs.delete('theater') : flexy.attrs.add('theater'); } }),
  '.ytp-skip-ad-button': mk({ click() { ad = false; } }),
};
const captions = mk({ pressed: 'false', getAttribute(n) { return n === 'aria-pressed' ? this.pressed : null; }, click() { this.pressed = this.pressed === 'true' ? 'false' : 'true'; } });
const like = mk({ pressed: 'false', getAttribute(n) { return n === 'aria-pressed' ? this.pressed : null; }, click() { this.pressed = 'true'; } });
const sub = mk({ textContent: 'Subscribe', click() { this.textContent = 'Subscribed'; } });
const player = {
  levels: ['hd1080', 'hd720', 'large', 'medium'], q: 'large',
  getAvailableQualityLevels() { return this.levels; }, setPlaybackQualityRange(lo) { if (lo !== 'auto') this.q = lo; }, setPlaybackQuality() {}, getPlaybackQuality() { return this.q; },
};
let hasCaptions = true;
const textOf = (t) => ({ textContent: t });
const document = {
  title: 'First video - YouTube', fullscreenElement: null, documentElement: { scrollHeight: 5000 },
  querySelector(sel) {
    if (sel === 'video') return video;
    if (sel === '#movie_player') return player;
    if (sel === 'ytd-watch-flexy') return flexy;
    if (sel === '.ytp-subtitles-button') return hasCaptions ? captions : null;
    if (sel.includes('.ytp-skip-ad-button')) return ad ? buttons['.ytp-skip-ad-button'] : null;
    if (sel === '.ytp-prev-button' || sel === '.ytp-size-button') return buttons[sel];
    if (sel.startsWith('like-button-view-model')) return like;
    if (sel.startsWith('#subscribe-button')) return sub;
    if (sel.startsWith('h1.ytd-watch-metadata')) return textOf('  The Real Title ');
    if (sel.startsWith('ytd-watch-metadata ytd-channel-name')) return textOf(' Some Channel ');
    return null;
  },
  querySelectorAll(sel) {
    if (sel === 'ytd-video-renderer') return [];
    if (sel.startsWith('ytd-playlist-renderer')) {
      const a = { href: 'https://www.youtube.com/watch?v=p1&list=PL1', textContent: 'A playlist', click() { go('p1'); } };
      return [{ querySelector: (s) => (s.includes('list=') ? a : { textContent: ' Mix of songs ' }), a }];
    }
    if (sel.includes('list=')) return [{ href: 'https://www.youtube.com/watch?v=p1&list=PL1', click() { go('p1'); } }];
    return [];
  },
};
const window = { scrollY: 0, innerHeight: 800, scrollBy() {} };
const event = { addListener() {} };
const context = vm.createContext({
  URL, WebSocket: { OPEN: 1, CONNECTING: 0 }, navigator: { userAgent: 'Chrome/130' }, fetch: async () => { throw new Error('offline'); },
  setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout, document, location, window, isFinite, Math, Number, getComputedStyle: () => ({ display: 'block' }),
  history: { back() { go('back1'); } },
  chrome: {
    tabs: { query: async () => [...tabs.values()], get: async (id) => { if (!tabs.has(id)) throw new Error('missing'); return tabs.get(id); }, update: async (id, p) => Object.assign(tabs.get(id), p), remove: async () => {}, create: async () => ({}) },
    windows: { update: async () => {} },
    scripting: { executeScript: async (o) => [{ result: await o.func(...o.args) }] },
    action: { setBadgeText() {}, setBadgeBackgroundColor() {}, onClicked: event },
    runtime: { id: 'ext-id', onInstalled: event, onStartup: event, onMessage: event, getManifest: () => ({ version: '2.0.0' }), reload() {} },
    storage: { local: { get: async () => ({}), set: async () => {} } },
    alarms: { create() {}, onAlarm: event },
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8'), context);
const yt = () => ({ tab_id: 2, expected_url: tabs.get(2).url });
const run = (action, extra = {}) => context.command({ action, ...yt(), ...extra });

(async () => {
  let r = await run('previous');
  assert.equal(r.success, true); assert.equal(r.video_id, 'prev1'); assert.equal(r.previous_video_id, 'aaa');
  go('aaa');
  buttons['.ytp-prev-button'] = null;
  r = await run('previous'); assert.equal(r.success, true, 'without a previous button the browser goes back'); assert.equal(r.video_id, 'back1');

  r = await run('theatre', { enable: true }); assert.equal(r.theatre, true); assert.equal(r.success, true);
  r = await run('theatre', { enable: true }); assert.equal(r.theatre, true, 'asking again does not toggle it off');
  r = await run('theatre', { enable: false }); assert.equal(r.theatre, false); assert.equal(r.success, true);

  r = await run('captions', { enable: true }); assert.equal(r.captions, true);
  r = await run('captions', { enable: true }); assert.equal(r.captions, true, 'already on stays on');
  r = await run('captions', { enable: false }); assert.equal(r.captions, false);
  hasCaptions = false;
  r = await run('captions', { enable: true }); assert.equal(r.success, false); assert.match(r.error, /no captions/);
  hasCaptions = true;

  r = await run('quality', { level: 'hd720' }); assert.equal(r.success, true); assert.equal(r.quality, 'hd720');
  r = await run('quality', { level: 'hd2160' }); assert.equal(r.success, false); assert.match(r.error, /not offered/); assert.deepEqual([...r.available], player.levels);
  r = await run('quality', { level: 'auto' }); assert.equal(r.success, true);
  await assert.rejects(run('quality', { level: 'ultra' }), /unknown quality/);

  r = await run('loop', { enable: true }); assert.equal(r.loop, true); assert.equal(video.loop, true);
  r = await run('loop', { enable: false }); assert.equal(r.loop, false);

  r = await run('skip_ad'); assert.equal(r.success, true); assert.equal(r.ad_gone, true);
  r = await run('skip_ad'); assert.equal(r.success, false); assert.match(r.error, /No skippable ad/);

  r = await run('like'); assert.equal(r.success, true); assert.equal(r.liked, true); assert.equal(r.already_liked, false);
  r = await run('like'); assert.equal(r.liked, true); assert.equal(r.already_liked, true, 'a second like does not un-like');

  r = await run('subscribe'); assert.equal(r.subscribed, true); assert.equal(r.channel, 'Some Channel'); assert.equal(r.already_subscribed, false);
  r = await run('subscribe'); assert.equal(r.already_subscribed, true);

  r = await run('now_playing'); assert.equal(r.video_title, 'The Real Title'); assert.equal(r.channel, 'Some Channel'); assert.equal(r.success, true);

  location.pathname = '/results';
  r = await run('results', { kind: 'playlist' }); assert.deepEqual([...r.results], ['Mix of songs']);
  r = await run('click_result', { index: 1, kind: 'playlist' }); assert.equal(r.success, true); assert.equal(r.video_id, 'p1');

  // every page action is limited to the tab that was inspected and to YouTube; website actions never reach chrome:// pages
  await assert.rejects(context.command({ action: 'like', tab_id: 3, expected_url: tabs.get(3).url }), /limited to YouTube/);
  await assert.rejects(context.command({ action: 'read_page', tab_id: 4, expected_url: tabs.get(4).url }), /only on http\(s\)/);
  await assert.rejects(context.command({ action: 'fill', tab_id: 3, expected_url: tabs.get(3).url, field: 'name' }), /field label and the text/);
  await assert.rejects(context.command({ action: 'click_link', tab_id: 3, expected_url: tabs.get(3).url, name: '' }), /words on the link/);
  await assert.rejects(context.command({ action: 'web_scroll', tab_id: 3, expected_url: tabs.get(3).url, amount: 99 }), /scroll amount/);
  await assert.rejects(context.command({ action: 'web_click_result', tab_id: 3, expected_url: tabs.get(3).url }), /result number/);
  await assert.rejects(context.command({ action: 'run_code', tab_id: 3, expected_url: tabs.get(3).url }), /Unsupported/);
  r = await context.command({ action: 'ping' }); assert.equal(r.success, true); assert.equal(r.version, '2.0.0');

  const caps = vm.runInContext('CAPABILITIES', context);
  for (const c of ['previous', 'theatre', 'captions', 'quality', 'loop', 'skip_ad', 'like', 'subscribe', 'now_playing', 'read_page', 'click_link', 'fill', 'reopen', 'bookmarks', 'history', 'ping']) assert.ok(caps.includes(c), c);
  console.log('F4 YouTube checks passed: previous, theatre, captions, quality, loop, skip ad, like, subscribe, now playing, playlist results, input limits.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
