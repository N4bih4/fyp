const API = 'http://127.0.0.1:8000';
let socket = null;
let connecting = false;
let heartbeat = null;
const seen = new Map();

async function command(message) {
  if (message.action === 'open') {
    const url = new URL(message.url);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Only http(s) website URLs are allowed.');
    const browser = navigator.userAgent.includes('Edg/') ? 'edge' : 'chrome';
    if (message.browser && message.browser !== browser) throw new Error(`Connected profile is ${browser}; connect the requested ${message.browser} profile.`);
    const existing = (await chrome.tabs.query({})).filter(t => !t.incognito && t.url === message.url);
    const tab = existing.length === 1 ? await chrome.tabs.update(existing[0].id, { active: true }) : await chrome.tabs.create({ url: message.url, active: true });
    if (tab.windowId !== undefined) await chrome.windows.update(tab.windowId, { focused: true });
    const actual = await chrome.tabs.get(tab.id);
    if (![actual.url, actual.pendingUrl].includes(message.url)) throw new Error('Browser did not confirm the requested tab navigation.');
    return { success: true, tab_id: tab.id, url: message.url, browser, navigation_requested: true };
  }
  if (message.action === 'inspect') {
    const tabs = await chrome.tabs.query({});
    return { success: true, tabs: tabs.filter(t => !t.incognito).map(t => ({ id: t.id, title: t.title || '', url: t.url || '', active: t.active, audible: t.audible })) };
  }
  if (!['close', 'pause', 'resume'].includes(message.action) || !Number.isInteger(message.tab_id)) {
    throw new Error('Unsupported browser command');
  }
  const tab = await chrome.tabs.get(message.tab_id);
  if (tab.incognito || !message.expected_url || tab.url !== message.expected_url) {
    throw new Error('Tab changed since inspection; nothing was changed. Repeat with the current title.');
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
        try { await video.play(); }
        catch { return { success: false, error: 'Browser ne playback block ki; video par Play dabayein.' }; }
      }
      const passed = action === 'pause' ? video.paused : !video.paused;
      return { success: passed, paused: video.paused, error: passed ? null : 'Video state did not change.' };
    },
    args: [message.action]
  });
  return results[0]?.result || { success: false, error: 'No media state returned.' };
}

async function connect() {
  if (connecting || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  connecting = true;
  try {
    const response = await fetch(`${API}/browser/connect-token`, { headers: { 'X-AgentX-Bridge': '1' } });
    if (!response.ok) throw new Error('Local backend unavailable');
    const { token } = await response.json();
    const ws = new WebSocket('ws://127.0.0.1:8000/browser/ws');
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ token }));
    ws.onmessage = async event => {
      const message = JSON.parse(event.data);
      if (message.ready) {
        chrome.action.setBadgeText({ text: 'ON' });
        chrome.action.setBadgeBackgroundColor({ color: '#047857' });
        if (heartbeat) clearInterval(heartbeat);
        heartbeat = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ heartbeat: true })); }, 20000);
        return;
      }
      if (!message.id) return;
      let result = seen.get(message.id);
      if (!result) {
        try { result = await command(message); }
        catch (error) { result = { success: false, error: String(error.message || error) }; }
        seen.set(message.id, result);
        if (seen.size > 200) seen.delete(seen.keys().next().value);
      }
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ id: message.id, result }));
    };
    ws.onclose = () => {
      if (heartbeat) clearInterval(heartbeat);
      heartbeat = null;
      if (socket === ws) socket = null;
      chrome.action.setBadgeText({ text: 'OFF' });
    };
    ws.onerror = () => ws.close();
  } catch {
    chrome.action.setBadgeText({ text: 'OFF' });
  } finally { connecting = false; }
}

chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('reconnect', { periodInMinutes: 0.5 }); connect(); });
chrome.runtime.onStartup.addListener(connect);
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'reconnect') connect(); });
chrome.action.onClicked.addListener(connect);
connect();
