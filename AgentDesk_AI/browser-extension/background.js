const API = 'http://127.0.0.1:8000';
let socket = null;
let connecting = false;
let heartbeat = null;
const seen = new Map();
const VERSION = chrome.runtime.getManifest ? chrome.runtime.getManifest().version : '0';
const CAPABILITIES = ['inspect', 'open', 'close', 'pause', 'resume', 'reload', 'switch', 'read', 'seek', 'speed', 'volume', 'mute', 'unmute',
  'fullscreen', 'next', 'results', 'click_result', 'scroll', 'previous', 'theatre', 'captions', 'quality', 'loop', 'skip_ad', 'like', 'subscribe',
  'now_playing', 'search', 'results_kind', 'read_page', 'click_link', 'fill', 'web_results', 'web_click_result', 'web_scroll', 'reopen', 'bookmarks', 'history', 'ping', 'status'];
// Everything that needs the page itself (the DOM) on YouTube. Each is checked afterwards by reading the page again.
const PAGE_ACTIONS = ['seek', 'speed', 'volume', 'mute', 'unmute', 'fullscreen', 'next', 'results', 'click_result', 'scroll', 'previous', 'theatre',
  'captions', 'quality', 'loop', 'skip_ad', 'like', 'subscribe', 'now_playing', 'search'];
// Page actions on ANY http(s) site (never an incognito tab, never a password / card / one-time-code field).
const WEB_ACTIONS = ['read_page', 'click_link', 'fill', 'web_results', 'web_click_result', 'web_scroll'];
const YOUTUBE_HOSTS = ['www.youtube.com', 'm.youtube.com', 'youtube.com'];

// Runs INSIDE the YouTube page (chrome.scripting serialises it, so it must not use anything outside itself). Returns the state it
// observed after acting, never what it intended: seek -> the real currentTime, speed -> the real playbackRate, next -> the new video id.
async function pageControl(action, p) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let video = document.querySelector('video');
  if (!video && ['seek', 'speed', 'volume', 'mute', 'unmute', 'loop', 'quality', 'theatre', 'captions', 'like', 'subscribe', 'now_playing', 'skip_ad', 'fullscreen'].includes(action)) {
    for (let i = 0; i < 100 && !video; i++) { await wait(200); video = document.querySelector('video'); }      // up to 20 s on a slow connection
  }
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const videoId = () => new URL(location.href).searchParams.get('v') || '';
  const snap = () => ({
    url: location.origin + location.pathname + (videoId() ? '?v=' + videoId() : ''), title: document.title, video_id: videoId(),
    time: video ? Math.round(video.currentTime * 10) / 10 : null, duration: video && isFinite(video.duration) ? Math.round(video.duration) : null,
    paused: video ? video.paused : null, rate: video ? video.playbackRate : null, volume: video ? Math.round(video.volume * 100) : null,
    muted: video ? video.muted : null, fullscreen: !!document.fullscreenElement, scroll_y: Math.round(window.scrollY || 0),
    scroll_max: Math.max(0, Math.round((document.documentElement.scrollHeight || 0) - (window.innerHeight || 0))),
  });
  const noVideo = { success: false, error: 'There is no video on this YouTube page.' };
  // Organic videos only: ads, Shorts shelves, channels and people are other elements; kind 'playlist' returns playlists / mixes instead.
  const results = (kind) => {
    if (kind === 'playlist') {
      return [...document.querySelectorAll('ytd-playlist-renderer, yt-lockup-view-model, ytd-radio-renderer')].map((el) => {
        const a = el.querySelector('a[href*="list="]');
        return a ? { title: String((el.querySelector('#video-title, h3, .yt-lockup-metadata-view-model-wiz__title') || a).textContent || '').trim().slice(0, 120), href: a.href } : null;
      }).filter(Boolean);
    }
    return [...document.querySelectorAll('ytd-video-renderer')].map((el) => {
      const a = el.querySelector('a#video-title');
      const isAd = !!(el.closest && el.closest('ytd-ad-slot-renderer, ytd-promoted-video-renderer')) || !!el.querySelector('ytd-badge-supported-renderer .badge-style-type-ad');
      return a && !isAd && String(a.href || '').includes('/watch') && !String(a.href).includes('/shorts/') ? { title: String(a.textContent || '').trim().slice(0, 120), href: a.href } : null;
    }).filter(Boolean);
  };
  const press = (el) => { el.click(); return true; };
  const q = (...sels) => { for (const sel of sels) { const el = document.querySelector(sel); if (el) return el; } return null; };
  const player = () => document.querySelector('#movie_player');
  const channelName = () => { const el = q('ytd-watch-metadata ytd-channel-name a', '#owner ytd-channel-name a', '#channel-name a', 'ytd-video-owner-renderer a'); return el ? String(el.textContent || '').trim() : ''; };
  const videoTitle = () => { const el = q('h1.ytd-watch-metadata', 'ytd-watch-metadata h1', 'h1.title'); return el ? String(el.textContent || '').trim() : String(document.title || '').replace(/ - YouTube$/, ''); };
  if (action === 'seek') {
    if (!video) return noVideo;
    const duration = isFinite(video.duration) ? video.duration : Infinity;
    const target = clamp(p.position != null ? p.position : video.currentTime + p.seconds, 0, duration);
    video.currentTime = target;
    await wait(250);
    return { ...snap(), target, success: Math.abs(video.currentTime - target) <= 1.5 };
  }
  if (action === 'speed') {
    if (!video) return noVideo;
    video.playbackRate = p.rate;
    await wait(50);
    return { ...snap(), success: Math.abs(video.playbackRate - p.rate) < 0.01 };
  }
  if (action === 'volume') {
    if (!video) return noVideo;
    video.muted = false;
    video.volume = clamp(p.level / 100, 0, 1);
    await wait(50);
    return { ...snap(), success: Math.abs(Math.round(video.volume * 100) - p.level) <= 1 && !video.muted };
  }
  if (action === 'mute' || action === 'unmute') {
    if (!video) return noVideo;
    video.muted = action === 'mute';
    await wait(50);
    return { ...snap(), success: video.muted === (action === 'mute') };
  }
  if (action === 'fullscreen') {
    const want = !p.exit;
    try {
      if (want) await (document.querySelector('#movie_player') || video || document.documentElement).requestFullscreen();
      else if (document.fullscreenElement) await document.exitFullscreen();
    } catch {
      return { ...snap(), success: false, error: 'Chrome allows full screen only after a real key press. Press F on the video.' };
    }
    await wait(200);
    return { ...snap(), success: !!document.fullscreenElement === want };
  }
  if (action === 'next') {
    const before = videoId();
    const button = document.querySelector('.ytp-next-button');
    const link = document.querySelector('ytd-compact-video-renderer a[href*="/watch"], ytd-watch-next-secondary-results-renderer a[href*="/watch"]');
    if (button && button.getAttribute('aria-disabled') !== 'true' && !button.hidden) button.click();
    else if (link) link.click();
    else return { success: false, error: 'There is no next video to go to.' };
    for (let i = 0; i < 25 && (!videoId() || videoId() === before); i++) await wait(200);
    return { ...snap(), previous_video_id: before, changed: videoId() !== before, success: !!videoId() && videoId() !== before };
  }
  if (action === 'results') {
    const found = results(p.kind);
    return { ...snap(), success: found.length > 0, results: found.slice(0, 10).map((r) => r.title), error: found.length ? null : 'This is not a YouTube results page.' };
  }
  if (action === 'click_result') {
    const found = results(p.kind);
    if (!found.length) return { success: false, error: 'This is not a YouTube results page. Search first.' };
    const item = found[p.index - 1];
    if (!item) return { success: false, error: `There are only ${found.length} results.` };
    const wanted = new URL(item.href).searchParams.get('v');
    const link = [...document.querySelectorAll('ytd-video-renderer a#video-title')].find((a) => a.href === item.href)
      || [...document.querySelectorAll('a[href*="/watch"], a[href*="list="]')].find((a) => a.href === item.href);
    if (!link) return { success: false, error: 'That result is no longer on the page.' };
    link.click();
    for (let i = 0; i < 50 && (wanted ? videoId() !== wanted : !videoId()); i++) await wait(200);
    // a video is only "playing" when the player says so: wait for the clock to move
    let started = false;
    for (let i = 0; i < 160 && !started; i++) {                                    // up to 40 s: the watch page can be slow to draw its player
      const v = document.querySelector('video');
      if (v) { const t0 = v.currentTime; await wait(250); started = !v.paused && v.currentTime > t0 && v.currentTime > 0; } else { await wait(250); }
    }
    return { ...snap(), clicked_title: item.title, wanted_video_id: wanted, playing: started, success: wanted ? videoId() === wanted : !!videoId() };
  }
  if (action === 'scroll') {
    const before = window.scrollY || 0;
    window.scrollBy(0, p.amount * (window.innerHeight || 600) * 0.8);
    await wait(300);
    const moved = Math.abs((window.scrollY || 0) - before) > 5;
    return { ...snap(), moved, success: moved, error: moved ? null : 'The page did not move (already at the end?).' };
  }
  if (action === 'previous') {
    const before = videoId();
    const button = q('.ytp-prev-button');
    if (button && button.getAttribute('aria-disabled') !== 'true' && !button.hidden && getComputedStyle(button).display !== 'none') button.click();
    else history.back();
    for (let i = 0; i < 75 && (!videoId() || videoId() === before); i++) await wait(200);
    const changedPrev = !!videoId() && videoId() !== before;
    return { ...snap(), previous_video_id: before, changed: changedPrev, success: changedPrev, error: changedPrev ? null : 'There is no previous video to go back to.' };
  }
  if (action === 'theatre') {
    const flexy = document.querySelector('ytd-watch-flexy');
    const button = q('.ytp-size-button');
    if (!button || !flexy) return { success: false, error: 'There is no theatre mode button on this page.' };
    const isOn = () => flexy.hasAttribute('theater');
    if (isOn() !== p.enable) { button.click(); await wait(400); }
    return { ...snap(), theatre: isOn(), success: isOn() === p.enable, error: isOn() === p.enable ? null : 'YouTube did not switch theatre mode.' };
  }
  if (action === 'captions') {
    const button = q('.ytp-subtitles-button');
    if (!button || getComputedStyle(button).display === 'none') return { success: false, error: 'This video has no captions to switch.' };
    const isOn = () => button.getAttribute('aria-pressed') === 'true';
    if (isOn() !== p.enable) { button.click(); await wait(400); }
    return { ...snap(), captions: isOn(), success: isOn() === p.enable, error: isOn() === p.enable ? null : 'YouTube did not switch the captions.' };
  }
  if (action === 'quality') {
    const pl = player();
    if (!pl || typeof pl.getAvailableQualityLevels !== 'function') return { success: false, error: 'The player does not offer quality levels here.' };
    const levels = pl.getAvailableQualityLevels();
    const want = p.level === 'auto' ? 'auto' : p.level;
    if (want !== 'auto' && !levels.includes(want)) return { ...snap(), success: false, available: levels, error: 'That quality is not offered for this video.' };
    if (want === 'auto') { pl.setPlaybackQualityRange('auto', 'auto'); } else { pl.setPlaybackQualityRange(want, want); pl.setPlaybackQuality && pl.setPlaybackQuality(want); }
    let actual = '';
    for (let i = 0; i < 12; i++) {                                           // the player reports "unknown" while it is buffering: ask again for up to 6 s
      await wait(500);
      actual = typeof pl.getPlaybackQuality === 'function' ? pl.getPlaybackQuality() : '';
      if (want === 'auto' || actual === want) break;
    }
    const okQ = want === 'auto' || actual === want;
    return { ...snap(), quality: actual, requested: want, available: levels, success: okQ, error: okQ ? null : `The player kept ${actual || 'its quality'} (it may not allow ${want} on this video).` };
  }
  if (action === 'loop') {
    if (!video) return noVideo;
    video.loop = p.enable;
    await wait(50);
    return { ...snap(), loop: video.loop, success: video.loop === p.enable, error: video.loop === p.enable ? null : 'The player did not change looping.' };
  }
  if (action === 'skip_ad') {
    const button = q('.ytp-skip-ad-button', '.ytp-ad-skip-button-modern', '.ytp-ad-skip-button', '.ytp-ad-skip-button-container button');
    if (!button) return { ...snap(), success: false, error: 'No skippable ad is showing right now.' };
    const before = video ? video.currentTime : 0;
    button.click();
    await wait(700);
    return { ...snap(), ad_gone: !q('.ytp-skip-ad-button', '.ytp-ad-skip-button-modern', '.ytp-ad-skip-button'), success: !q('.ytp-skip-ad-button', '.ytp-ad-skip-button-modern', '.ytp-ad-skip-button') };
  }
  if (action === 'like') {
    const button = q('like-button-view-model button', '#segmented-like-button button', 'ytd-toggle-button-renderer#like-button button', '#like-button button');
    if (!button) return { success: false, error: 'There is no Like button on this page.' };
    const liked = () => button.getAttribute('aria-pressed') === 'true';
    const was = liked();
    if (!was) { button.click(); await wait(600); }
    return { ...snap(), liked: liked(), already_liked: was, success: liked(), error: liked() ? null : 'YouTube did not accept the like (not signed in? it then asks you to sign in).' };
  }
  if (action === 'subscribe') {
    const button = q('#subscribe-button button', 'ytd-subscribe-button-renderer button', 'yt-subscribe-button-view-model button');
    if (!button) return { success: false, error: 'There is no Subscribe button on this page.' };
    const label = () => String(button.textContent || '').trim().toLowerCase();
    const already = label().startsWith('subscribed');
    if (!already) { button.click(); await wait(800); }
    const now = label().startsWith('subscribed');
    return { ...snap(), channel: channelName(), subscribed: now, already_subscribed: already, success: now, error: now ? null : 'YouTube did not subscribe (not signed in? it then asks you to sign in).' };
  }
  if (action === 'now_playing') {
    if (!videoId()) return { success: false, error: 'No video is open in this tab.' };
    return { ...snap(), video_title: videoTitle(), channel: channelName(), success: true };
  }
  return { success: false, error: 'Unsupported page command' };
}

// Runs INSIDE any http(s) page. Reads text (never password / card fields), follows a link by its words, fills a field by its label, scrolls.
async function webControl(action, p) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const visible = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el); return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const norm = (t) => String(t || '').replace(/\s+/g, ' ').trim();
  const info = () => ({ url: location.origin + location.pathname, title: document.title, scroll_y: Math.round(window.scrollY || 0) });
  if (action === 'read_page') {
    const root = document.querySelector('main, article, [role="main"]') || document.body;
    const clone = root.cloneNode(true);
    clone.querySelectorAll('script, style, noscript, svg, input[type="password"], [autocomplete*="cc-"], [autocomplete="one-time-code"], iframe').forEach((n) => n.remove());
    const text = norm(clone.innerText || clone.textContent).slice(0, p.max_chars || 6000);
    const headings = [...document.querySelectorAll('h1, h2')].filter(visible).slice(0, 8).map((h) => norm(h.textContent).slice(0, 100));
    return { ...info(), text, headings, chars: text.length, success: text.length > 0, error: text.length ? null : 'The page has no readable text.' };
  }
  if (action === 'web_results') {
    const host = location.hostname;
    const sel = host.includes('google.') ? '#search a:has(h3), #rso a:has(h3)' : host.includes('bing.com') ? 'li.b_algo h2 a' : host.includes('duckduckgo.com') ? 'a[data-testid="result-title-a"], a.result__a' : '';
    const found = sel ? [...document.querySelectorAll(sel)].filter(visible).map((a) => ({ title: norm((a.querySelector('h3') || a).textContent).slice(0, 120), href: a.href })).filter((r) => r.title) : [];
    return { ...info(), results: found.slice(0, 10).map((r) => r.title), success: found.length > 0, error: found.length ? null : 'This is not a search results page I know (Google, Bing, DuckDuckGo).' };
  }
  if (action === 'web_click_result') {
    const host = location.hostname;
    const sel = host.includes('google.') ? '#search a:has(h3), #rso a:has(h3)' : host.includes('bing.com') ? 'li.b_algo h2 a' : host.includes('duckduckgo.com') ? 'a[data-testid="result-title-a"], a.result__a' : '';
    const found = sel ? [...document.querySelectorAll(sel)].filter(visible) : [];
    if (!found.length) return { success: false, error: 'This is not a search results page I know (Google, Bing, DuckDuckGo).' };
    let link = null;
    if (p.index) link = found[p.index - 1];
    else if (p.name) link = found.find((a) => norm(a.textContent).toLowerCase().includes(p.name.toLowerCase()));
    if (!link) return { success: false, error: p.index ? `There are only ${found.length} results.` : 'No result contains those words.' };
    const target = link.href;
    link.click();
    await wait(800);
    return { ...info(), clicked_title: norm(link.textContent).slice(0, 120), target, success: true };
  }
  if (action === 'click_link') {
    const wanted = p.name.toLowerCase();
    const anchors = [...document.querySelectorAll('a[href], button, [role="link"], [role="button"]')].filter(visible)
      .filter((el) => norm(el.textContent || el.getAttribute('aria-label')).toLowerCase().includes(wanted));
    if (!anchors.length) return { success: false, error: `No visible link or button contains "${p.name}".` };
    if (anchors.length > 1 && !p.first) return { success: false, error: `${anchors.length} links match "${p.name}"; say which one.`, matches: anchors.slice(0, 5).map((a) => norm(a.textContent).slice(0, 60)) };
    const el = anchors[0];
    const text = norm(el.textContent || el.getAttribute('aria-label')).slice(0, 80);
    if (/^(pay|buy|purchase|place order|delete|remove|send|submit|confirm|sign out|log out|install)\b/i.test(text) && !/^(pay|buy|purchase|place order|delete|remove|send|submit|confirm|sign out|log out|install)\b/i.test(p.name)) {
      return { success: false, error: `"${text}" pays, deletes, sends or installs: say its name in the command so it is approved.` };
    }
    const before = location.href;
    el.click();
    await wait(800);
    return { ...info(), clicked: text, navigated: location.href !== before, success: true };
  }
  if (action === 'fill') {
    const wanted = p.field.toLowerCase();
    const fields = [...document.querySelectorAll('input, textarea, [contenteditable="true"]')].filter(visible).filter((el) => {
      const label = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      const text = [el.getAttribute('aria-label'), el.getAttribute('placeholder'), el.getAttribute('name'), el.id, label && label.textContent, el.title].map(norm).join(' ').toLowerCase();
      return text.includes(wanted);
    });
    if (!fields.length) return { success: false, error: `No visible field is labelled "${p.field}".` };
    const el = fields[0];
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (type === 'password' || /^(cc-|one-time-code|new-password|current-password)/.test(ac) || /passw|card|cvv|cvc|otp|pin\b/i.test(`${el.name} ${el.id} ${el.getAttribute('aria-label') || ''}`)) {
      return { success: false, error: 'That is a password, card or one-time-code field: the assistant never fills those. Type it yourself.' };
    }
    el.focus();
    if (el.isContentEditable) { el.textContent = p.text; el.dispatchEvent(new InputEvent('input', { bubbles: true })); }
    else {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, p.text);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    await wait(100);
    const now = el.isContentEditable ? norm(el.textContent) : el.value;
    return { ...info(), field: norm(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || el.id).slice(0, 60), filled_chars: String(now).length, success: now === p.text };
  }
  if (action === 'web_scroll') {
    const before = window.scrollY || 0;
    window.scrollBy(0, p.amount * (window.innerHeight || 600) * 0.8);
    await wait(300);
    const moved = Math.abs((window.scrollY || 0) - before) > 5;
    return { ...info(), moved, success: moved, error: moved ? null : 'The page did not move (already at the end?).' };
  }
  return { success: false, error: 'Unsupported page command' };
}

// The numbers the backend sends are checked again here: nothing outside these ranges reaches the page.
function pageParams(message) {
  const num = (v, lo, hi) => (Number.isFinite(v) && v >= lo && v <= hi ? v : null);
  if (message.action === 'seek') {
    const position = num(message.position, 0, 86400);
    const seconds = num(message.seconds, -3600, 3600);
    if (position === null && seconds === null) throw new Error('seek needs seconds or a position');
    return { position, seconds };
  }
  if (message.action === 'speed') { const rate = num(message.rate, 0.25, 4); if (rate === null) throw new Error('speed must be between 0.25 and 4'); return { rate }; }
  if (message.action === 'volume') { const level = num(message.level, 0, 100); if (level === null) throw new Error('volume must be 0 to 100'); return { level }; }
  if (message.action === 'click_result') {
    const index = num(message.index, 1, 20); if (!Number.isInteger(index)) throw new Error('result number must be 1 to 20');
    return { index, kind: message.kind === 'playlist' ? 'playlist' : 'video' };
  }
  if (message.action === 'results') return { kind: message.kind === 'playlist' ? 'playlist' : 'video' };
  if (['theatre', 'captions', 'loop'].includes(message.action)) return { enable: message.enable !== false };
  if (message.action === 'quality') {
    const level = String(message.level || '');
    if (!['auto', 'tiny', 'small', 'medium', 'large', 'hd720', 'hd1080', 'hd1440', 'hd2160', 'highres'].includes(level)) throw new Error('unknown quality level');
    return { level };
  }
  if (message.action === 'scroll') { const amount = num(message.amount, -10, 10); if (amount === null || amount === 0) throw new Error('scroll amount must be -10 to 10'); return { amount }; }
  if (message.action === 'fullscreen') return { exit: message.exit === true };
  return {};
}

// Parameters of the page actions that run on any website. Text is bounded; nothing the backend sends is run as code.
function webParams(message) {
  const text = (v, max) => (typeof v === 'string' && v.trim().length > 0 && v.length <= max ? v : null);
  if (message.action === 'read_page') return { max_chars: Number.isFinite(message.max_chars) ? Math.min(20000, Math.max(200, message.max_chars)) : 6000 };
  if (message.action === 'web_scroll') { const a = message.amount; if (!Number.isFinite(a) || a === 0 || Math.abs(a) > 10) throw new Error('scroll amount must be -10 to 10'); return { amount: a }; }
  if (message.action === 'web_click_result') {
    const index = Number.isInteger(message.index) && message.index >= 1 && message.index <= 20 ? message.index : null;
    const name = text(message.name, 120);
    if (!index && !name) throw new Error('say the result number (1 to 20) or some words of its title');
    return { index, name };
  }
  if (message.action === 'click_link') { const name = text(message.name, 120); if (!name) throw new Error('say the words on the link or button'); return { name, first: message.first === true }; }
  if (message.action === 'fill') {
    const field = text(message.field, 80); const value = typeof message.text === 'string' && message.text.length <= 2000 ? message.text : null;
    if (!field || value === null) throw new Error('fill needs a field label and the text');
    return { field, text: value };
  }
  return {};
}

// Browsers normalise URLs (https://site -> https://site/); compare the same form on both sides.
function sameUrl(a, b) {
  try { return new URL(a).href === new URL(b).href; } catch { return false; }
}

// The bridge may only be used by an extension the user paired with this app's
// local API token (handed over once from the setup page; never typed or logged).
async function pairedToken() {
  const stored = await chrome.storage.local.get('apiToken');
  return typeof stored.apiToken === 'string' && stored.apiToken.length >= 32 ? stored.apiToken : null;
}

// Auto-pair: the running app gives its local token to this extension (it checks our extension id), so no setup link is needed.
async function autoPair() {
  try {
    const response = await fetch(`${API}/browser/auto-pair`, { headers: { 'X-AgentX-Bridge': '1' } });
    if (!response.ok) return null;
    const { token } = await response.json();
    if (typeof token !== 'string' || token.length < 32) return null;
    await chrome.storage.local.set({ apiToken: token });
    return token;
  } catch { return null; }
}

function acceptPairing(message, sender) {
  return Boolean(
    message && message.type === 'agentx-pair' && typeof message.token === 'string' && message.token.length >= 32 &&
    sender && sender.id === chrome.runtime.id && typeof sender.url === 'string' &&
    sender.url.startsWith(API + '/browser-extension/setup.html'),
  );
}

async function command(message) {
  if (message.action === 'open') {
    const url = new URL(message.url);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Only http(s) website URLs are allowed.');
    const browser = navigator.userAgent.includes('Edg/') ? 'edge' : 'chrome';
    if (message.browser && message.browser !== browser) throw new Error(`Connected profile is ${browser}; connect the requested ${message.browser} profile.`);
    const existing = message.new_tab ? [] : (await chrome.tabs.query({})).filter(t => !t.incognito && sameUrl(t.url || '', message.url));
    const tab = existing.length === 1 ? await chrome.tabs.update(existing[0].id, { active: true }) : await chrome.tabs.create({ url: message.url, active: true });
    if (tab.windowId !== undefined) await chrome.windows.update(tab.windowId, { focused: true });
    const actual = await chrome.tabs.get(tab.id);
    if (![actual.url, actual.pendingUrl].some(u => u && sameUrl(u, message.url))) throw new Error('Browser did not confirm the requested tab navigation.');
    return { success: true, tab_id: tab.id, url: message.url, browser, navigation_requested: true };
  }
  if (message.action === 'ping') return { success: true, version: VERSION, time: Date.now() };
  if (message.action === 'status') return { success: true, ...state };
  if (message.action === 'reopen') {
    // the most recently closed tab or window of this profile
    const recent = chrome.sessions ? await chrome.sessions.getRecentlyClosed({ maxResults: 5 }) : [];
    const entry = recent.find((e) => e.tab);
    if (!entry) return { success: false, error: 'There is no recently closed tab to reopen.' };
    const restored = await chrome.sessions.restore(entry.tab.sessionId);
    return { success: true, reopened: (restored.tab && restored.tab.title) || entry.tab.title || '', url: entry.tab.url || '' };
  }
  if (message.action === 'bookmarks') {
    if (!chrome.bookmarks) return { success: false, error: 'This browser profile did not give the bridge access to bookmarks.' };
    const query = typeof message.query === 'string' ? message.query.slice(0, 100) : '';
    const found = (await chrome.bookmarks.search(query)).filter((b) => b.url).slice(0, 10);
    return { success: found.length > 0, results: found.map((b) => ({ title: String(b.title || '').slice(0, 100), url: b.url })), error: found.length ? null : 'No bookmark matches.' };
  }
  if (message.action === 'history') {
    if (!chrome.history) return { success: false, error: 'This browser profile did not give the bridge access to history.' };
    const query = typeof message.query === 'string' ? message.query.slice(0, 100) : '';
    const days = Number.isFinite(message.days) ? Math.min(365, Math.max(1, message.days)) : 30;
    const found = (await chrome.history.search({ text: query, maxResults: 10, startTime: Date.now() - days * 86400000 })).filter((h) => h.url);
    return { success: found.length > 0, results: found.map((h) => ({ title: String(h.title || '').slice(0, 100), url: h.url, visited: new Date(h.lastVisitTime || 0).toISOString() })),
             error: found.length ? null : 'Nothing in the history matches.' };
  }
  if (message.action === 'reload') {
    // The backend asks an outdated extension to load its updated files (unpacked install).
    setTimeout(() => chrome.runtime.reload(), 200);
    return { success: true, reloading: true, version: VERSION };
  }
  if (message.action === 'inspect') {
    const tabs = await chrome.tabs.query({});
    // A loading tab has only pendingUrl; report it so a later guard compares the same page.
    return { success: true, tabs: tabs.filter(t => !t.incognito).map(t => ({ id: t.id, title: t.title || '', url: t.url || t.pendingUrl || '', active: t.active, audible: t.audible })) };
  }
  if (!['close', 'pause', 'resume', 'switch', 'read', ...PAGE_ACTIONS, ...WEB_ACTIONS].includes(message.action) || !Number.isInteger(message.tab_id)) {
    throw new Error('Unsupported browser command');
  }
  const tab = await chrome.tabs.get(message.tab_id);
  if (tab.incognito || !message.expected_url || !sameUrl(tab.url || tab.pendingUrl || '', message.expected_url)) {
    throw new Error('Tab changed since inspection; nothing was changed. Repeat with the current title.');
  }
  if (message.action === 'read') {
    const parts = new URL(tab.url || tab.pendingUrl || 'about:blank');
    return { success: true, title: tab.title || '', url: parts.origin + parts.pathname, active: !!tab.active };
  }
  if (message.action === 'switch') {
    const updated = await chrome.tabs.update(tab.id, { active: true });
    if (updated.windowId !== undefined) await chrome.windows.update(updated.windowId, { focused: true });
    const now = await chrome.tabs.get(tab.id);
    return { success: !!now.active, active: !!now.active, title: now.title || '' };
  }
  if (WEB_ACTIONS.includes(message.action)) {
    const protocol = new URL(tab.url || tab.pendingUrl || 'about:blank').protocol;
    if (!['http:', 'https:'].includes(protocol)) throw new Error('Page actions work only on http(s) websites.');
    const params = webParams(message);
    const before = tab.url || '';
    let results = null;
    try { results = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: webControl, args: [message.action, params] }); }
    catch (error) { if (!['click_link', 'web_click_result'].includes(message.action)) throw error; }
    if (results && results[0] && results[0].result) return results[0].result;
    if (['click_link', 'web_click_result'].includes(message.action)) {
      // A click that leaves the page destroys the page script before it can answer: the answer is then what the TAB shows now.
      await new Promise((r) => setTimeout(r, 600));
      const now = await chrome.tabs.get(tab.id);
      const moved = !sameUrl(now.url || now.pendingUrl || '', before);
      return { success: moved, navigated: moved, clicked: params.name || ('result ' + params.index), clicked_title: params.name || ('result ' + params.index),
               title: now.title || '', url: (() => { try { const u = new URL(now.url || now.pendingUrl); return u.origin + u.pathname; } catch { return ''; } })(),
               error: moved ? null : 'The click did not change the page.' };
    }
    return { success: false, error: 'No page state returned.' };
  }
  if (message.action === 'search') {
    // Search on the YouTube tab that is already open: the same tab goes to the results page (no new tab, no Google).
    if (!YOUTUBE_HOSTS.includes(new URL(tab.url).hostname)) throw new Error('Search in this tab is limited to YouTube.');
    const query = String(message.query || '').replace(/\s+/g, ' ').trim().slice(0, 100);
    if (!query) throw new Error('Say what to search for.');
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
    await chrome.tabs.update(tab.id, { url, active: true });
    let now = await chrome.tabs.get(tab.id);
    for (let i = 0; i < 50 && !(now.status === 'complete' && (now.url || '').includes('/results')); i++) {      // up to 10 s for the results page
      await new Promise((r) => setTimeout(r, 200));
      now = await chrome.tabs.get(tab.id);
    }
    let searched = '';
    try { searched = new URL(now.url || now.pendingUrl || '').searchParams.get('search_query') || ''; } catch { searched = ''; }
    return { success: searched === query, tab_id: tab.id, searched, url: `https://www.youtube.com/results`, title: now.title || '',
             error: searched === query ? null : 'The tab did not show the search results.' };
  }
  if (PAGE_ACTIONS.includes(message.action)) {
    if (!YOUTUBE_HOSTS.includes(new URL(tab.url).hostname)) throw new Error('Media and page controls are limited to YouTube.');
    const results = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: pageControl, args: [message.action, pageParams(message)], ...(message.action === 'quality' ? { world: 'MAIN' } : {}) });
    return results[0]?.result || { success: false, error: 'No page state returned.' };
  }
  if (message.action === 'close') {
    await chrome.tabs.remove(tab.id);
    let exists = true;
    try { await chrome.tabs.get(tab.id); } catch { exists = false; }
    if (exists) throw new Error('Browser did not confirm that the tab closed.');
    return { success: true, closed: true };
  }
  const host = new URL(tab.url).hostname;
  if (!['www.youtube.com', 'm.youtube.com', 'youtube.com'].includes(host)) throw new Error('Media controls are limited to YouTube.');
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: async (action) => {
      const video = document.querySelector('video');
      if (!video) return { success: false, error: 'Is YouTube tab mein playable video nahi mila.' };
      if (action === 'pause') video.pause();
      else {
        try { await Promise.race([video.play(), new Promise((r) => setTimeout(r, 6000))]); }      // a video that is still buffering must not hang the answer
        catch { return { success: false, error: 'Browser ne playback block ki; video par Play dabayein.' }; }
      }
      const passed = action === 'pause' ? video.paused : !video.paused;
      return { success: passed, paused: video.paused, error: passed ? null : 'Video state did not change.' };
    },
    args: [message.action]
  });
  return results[0]?.result || { success: false, error: 'No media state returned.' };
}

// ---------------------------------------------------------------------------------------------- connection
// What the popup and the backend's /browser/status show: how it is connected, since when, the last answer from the app, and the last problem.
const state = { connected: false, via: null, since: null, last_pong: null, last_error: null, attempts: 0, paired: false, version: VERSION, backend: API,
                browser: (typeof navigator !== 'undefined' && String(navigator.userAgent).includes('Edg/')) ? 'edge' : 'chrome' };
let retryTimer = null;
let watchdog = null;
let nativePort = null;

async function setState(patch) {
  Object.assign(state, patch);
  try { await chrome.storage.local.set({ status: { ...state } }); } catch { /* the popup just shows the last saved state */ }
  try {
    chrome.action.setBadgeText({ text: state.connected ? 'ON' : (state.paired ? 'OFF' : 'PAIR') });
    chrome.action.setBadgeBackgroundColor({ color: state.connected ? '#047857' : '#b45309' });
  } catch { /* no action API in tests */ }
}

// One message from the app: the handshake, a heartbeat answer, or a command. The same code serves the WebSocket and the native-messaging port.
async function onAppMessage(message, send) {
  if (message.ready) { await setState({ connected: true, since: new Date().toISOString(), last_error: null, attempts: 0, last_pong: new Date().toISOString() }); return; }
  if (message.heartbeat) { state.last_pong = new Date().toISOString(); return; }
  if (!message.id) return;
  let result = seen.get(message.id);
  if (!result) {
    try { result = await command(message); }
    catch (error) { result = { success: false, error: String(error.message || error) }; }
    seen.set(message.id, result);
    if (seen.size > 200) seen.delete(seen.keys().next().value);
  }
  send({ id: message.id, result });
}

function scheduleReconnect(why) {
  if (retryTimer) return;
  state.attempts += 1;
  const delay = Math.min(30000, 1000 * 2 ** Math.min(state.attempts, 5));     // 2 s, 4 s ... 30 s
  void setState({ connected: false, via: null, last_error: why || state.last_error });
  retryTimer = setTimeout(() => { retryTimer = null; void connect(); }, delay);
  if (retryTimer && retryTimer.unref) retryTimer.unref();   // Node (tests) only; browsers return a number
}

// The browser the user used last: with Chrome and Edge both connected, the app talks to the one that was focused most recently.
let focusedAt = null;
try { chrome.windows.onFocusChanged.addListener((id) => { if (id !== chrome.windows.WINDOW_ID_NONE) focusedAt = Date.now(); }); } catch { /* not available in tests */ }
try { chrome.tabs.onActivated.addListener(() => { focusedAt = Date.now(); }); } catch { /* not available in tests */ }

function startKeepalive(send, isOpen, close) {
  // The service worker is only kept alive by traffic: a ping every 15 s keeps it awake, and a silent app (no answer for 45 s) is a dead link.
  if (watchdog) clearInterval(watchdog);
  watchdog = setInterval(() => {
    if (!isOpen()) return;
    send({ heartbeat: true, focused_at: focusedAt });
    const quiet = Date.now() - Date.parse(state.last_pong || state.since || new Date().toISOString());
    if (quiet > 45000) { void setState({ last_error: 'The app stopped answering pings; reconnecting.' }); close(); }
  }, 15000);
}

async function connectNative(token) {
  // Primary channel when the native host is installed (scripts/install_native_host.ps1): the browser starts the host, keeps this worker alive while the
  // port is open, and the host relays the same messages to the app. If it is not installed, connectNative fails at once and the WebSocket is used.
  if (!chrome.runtime.connectNative) return false;
  return new Promise((resolve) => {
    let opened = false;
    let port;
    try { port = chrome.runtime.connectNative('com.agentdesk.bridge'); } catch { resolve(false); return; }
    const timer = setTimeout(() => { if (!opened) { try { port.disconnect(); } catch { /* ignore */ } resolve(false); } }, 6000);
    port.onMessage.addListener((message) => {
      if (message && message.ready) { opened = true; clearTimeout(timer); nativePort = port; resolve(true); }
      if (message && message.host_error) { state.last_error = 'Native host: ' + String(message.host_error).slice(0, 120); }
      void onAppMessage(message || {}, (m) => { try { port.postMessage(m); } catch { /* port closed */ } });
    });
    port.onDisconnect.addListener(() => {
      clearTimeout(timer);
      const wasOpen = opened;
      nativePort = null;
      if (!wasOpen) { resolve(false); return; }
      scheduleReconnect((chrome.runtime.lastError && chrome.runtime.lastError.message) || 'Native host closed');
    });
    port.postMessage({ token, version: VERSION, capabilities: CAPABILITIES, browser: state.browser, focused_at: focusedAt });
  });
}

async function connect() {
  if (connecting || nativePort || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  connecting = true;
  try {
    let apiToken = await pairedToken();
    if (!apiToken) apiToken = await autoPair();
    await setState({ paired: !!apiToken });
    if (!apiToken) { scheduleReconnect('Waiting for the Agent X app to start so the extension can pair itself.'); return; }
    let response;
    try { response = await fetch(`${API}/browser/connect-token`, { headers: { 'X-AgentX-Bridge': '1', Authorization: `Bearer ${apiToken}` } }); }
    catch { scheduleReconnect('The Agent X app is not running on 127.0.0.1:8000.'); return; }
    if (response.status === 401 || response.status === 403) {
      // Saved token is old (the app made a new one): pair again automatically.
      await chrome.storage.local.remove('apiToken');
      scheduleReconnect('The app rejected the saved pairing; pairing again automatically.');
      return;
    }
    if (!response.ok) { scheduleReconnect(`The app answered HTTP ${response.status}.`); return; }
    const { token } = await response.json();
    if (await connectNative(token)) {
      await setState({ via: 'native' });
      startKeepalive((m) => nativePort && nativePort.postMessage(m), () => !!nativePort, () => { try { nativePort.disconnect(); } catch { /* ignore */ } nativePort = null; scheduleReconnect('Native link lost'); });
      return;
    }
    const ws = new WebSocket('ws://127.0.0.1:8000/browser/ws');
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ token, version: VERSION, capabilities: CAPABILITIES, browser: state.browser, focused_at: focusedAt }));
    ws.onmessage = async (event) => {
      const message = JSON.parse(event.data);
      if (message.ready) {
        await setState({ via: 'websocket' });
        startKeepalive((m) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(m)); }, () => ws.readyState === WebSocket.OPEN, () => ws.close());
      }
      await onAppMessage(message, (m) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(m)); });
    };
    ws.onclose = () => {
      if (watchdog) clearInterval(watchdog);
      watchdog = null;
      if (socket === ws) socket = null;
      scheduleReconnect(state.last_error || 'The link to the app closed.');
    };
    ws.onerror = () => ws.close();
  } catch (error) {
    scheduleReconnect(String((error && error.message) || error).slice(0, 120));
  } finally { connecting = false; }
}

chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('reconnect', { periodInMinutes: 0.5 }); void connect(); });
chrome.runtime.onStartup.addListener(() => { void connect(); });
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === 'reconnect') void connect(); });   // a watchdog even if every timer was lost with the worker
chrome.action.onClicked.addListener(() => { void connect(); });
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === 'agentx-popup' && sender && sender.id === chrome.runtime.id) {
    // The popup: show the state, or force a new connection attempt.
    if (message.what === 'reconnect') {
      if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
      state.attempts = 0;
      try { socket?.close(); } catch { /* ignore */ }
      socket = null;
      void connect();
    }
    sendResponse({ ...state });
    return false;
  }
  if (!acceptPairing(message, sender)) return false;
  chrome.storage.local.set({ apiToken: message.token }).then(() => { sendResponse({ ok: true }); void connect(); });
  return true;
});
void connect();
