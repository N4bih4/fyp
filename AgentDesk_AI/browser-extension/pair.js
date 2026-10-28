// Runs only on the Agent X setup page. The app opens it as setup.html#token=...
// (a URL fragment is never sent to the server); we hand the token to the extension once.
(function () {
  const status = document.getElementById('pair-status');
  const show = text => { if (status) status.textContent = text; };
  const match = /(?:^#|&)token=([^&]+)/.exec(location.hash);
  if (!match) { show('Not paired yet. Open this page from the "Chrome/Edge setup" link inside the Agent X app.'); return; }
  chrome.runtime.sendMessage({ type: 'agentx-pair', token: decodeURIComponent(match[1]) }, reply => {
    history.replaceState(null, '', location.pathname);
    show(reply && reply.ok ? 'Paired. The extension badge should turn ON.' : 'Pairing failed. Reopen the setup link from the app.');
  });
})();
