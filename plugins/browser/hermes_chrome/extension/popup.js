document.addEventListener('DOMContentLoaded', async () => {
  const $ = id => document.getElementById(id);
  const dot = $('dot');
  const sub = $('sub');
  const err = $('err');

  function sv(el, state, text) { el.textContent = text; el.className = 'val ' + state; }
  function sd(s) { dot.className = 'dot ' + (s === 'ok' ? 'ok' : s === 'bad' ? 'bad' : 'warn'); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  $('ext-id').textContent = chrome.runtime.id || '—';
  $('sock').textContent = '~/.hermes/run/chrome-bridge.sock';

  // Extension is loaded (popup is running)
  sv($('ext-status'), 'ok', 'Loaded ✓');
  sd('ok');
  sub.textContent = 'Connected — OWL is ready';

  // Find the actual active tab. Hermes should not silently switch tabs.
  let tab = null;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    tab = tabs[0] || null;
  } catch (e) {
    err.textContent = 'Tab query failed: ' + e.message;
    err.classList.add('show');
  }

  if (tab) {
    const url = tab.url ? tab.url.replace(/^https?:\/\//, '').replace(/\/$/, '').substring(0, 48) : '';
    $('tab').innerHTML = `<div class="card"><div class="card-title">${esc(tab.title || 'Untitled')}</div><div class="card-url">${esc(url)}</div></div>`;

    if (/^(https?|file):\/\//i.test(tab.url || '')) {
      try {
        const swResponse = await chrome.runtime.sendMessage({ type: 'hermes-cursor-status', tabId: tab.id });
        if (swResponse?.injected) {
          sv($('cs-status'), 'ok', 'Injected ✓');
        } else {
          sv($('cs-status'), swResponse?.blocked ? 'bad' : 'warn', swResponse?.reason || 'Not injected');
        }
      } catch (e) {
        sv($('cs-status'), 'bad', 'Check failed');
        err.textContent = 'Content script check failed: ' + e.message;
        err.classList.add('show');
      }
    } else {
      sv($('cs-status'), 'warn', 'Blocked on this URL');
    }
  } else {
    $('tab').innerHTML = '<div class="empty">No active tab detected</div>';
    sv($('cs-status'), 'warn', 'No tab');
  }
});
