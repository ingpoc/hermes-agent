const HOST_NAME = "com.hermes.chrome_bridge";
let port = null;
const attachedTabs = new Set();
const injectedTabs = new Set();

function connectHost() {
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
    port.onMessage.addListener((message) => {
      handleHostMessage(message).catch((error) => {
        post({ id: message?.id, success: false, error: String(error?.message || error) });
      });
    });
    port.onDisconnect.addListener(() => {
      port = null;
      setTimeout(connectHost, 2000);
    });
  } catch {
    port = null;
    setTimeout(connectHost, 5000);
  }
}

function post(message) {
  if (port) {
    try {
      port.postMessage(message);
    } catch (e) {
      console.error("postMessage failed:", e);
    }
  }
}

function isControllableUrl(url) {
  return typeof url === "string" && /^(https?|file):\/\//i.test(url);
}

function unsupportedUrlReason(url) {
  if (!url) return "No tab URL is available";
  if (url.startsWith("file://")) {
    return "File URLs require Chrome extension file access to be enabled";
  }
  return `Chrome does not allow content-script injection on this URL: ${url}`;
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error("No active Chrome tab is available");
  }
  if (!isControllableUrl(tab.url)) {
    throw new Error(unsupportedUrlReason(tab.url));
  }
  return tab;
}

async function ensureAttached(tabId) {
  if (attachedTabs.has(tabId)) return;
  await withTimeout(chrome.debugger.attach({ tabId }, "1.3"), 3000, "debugger.attach");
  attachedTabs.add(tabId);
  await withTimeout(chrome.debugger.sendCommand({ tabId }, "Runtime.enable"), 3000, "Runtime.enable");
  await withTimeout(chrome.debugger.sendCommand({ tabId }, "Page.enable"), 3000, "Page.enable");
}

async function send(tabId, method, params = {}) {
  await ensureAttached(tabId);
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function evaluate(tabId, expression) {
  const result = await send(tabId, "Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true
  });
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(detail || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

async function findPointBySelector(tabId, selectorText) {
  const selector = JSON.stringify(String(selectorText || ""));
  const point = await evaluate(
    tabId,
    `(() => {
      const el = document.querySelector(${selector});
      if (!el) return null;
      el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
      const rect = el.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) return null;
      return {
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
        tag: el.tagName,
        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 160)
      };
    })()`
  );
  if (!point) throw new Error(`No visible element matched selector: ${selectorText}`);
  return point;
}

async function findPointByText(tabId, text) {
  const needle = JSON.stringify(String(text || ""));
  const point = await evaluate(
    tabId,
    `(() => {
      const needle = ${needle}.toLowerCase();
      const els = Array.from(document.querySelectorAll('a,button,[role=button],input[type=button],input[type=submit],label,summary,h1,h2,h3,h4,h5,h6,p,span,li,td,th'));
      const el = els.find((candidate) => (
        (candidate.innerText || candidate.value || candidate.getAttribute('aria-label') || '').toLowerCase().includes(needle)
      ));
      if (!el) return null;
      el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
      const rect = el.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) return null;
      return {
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
        tag: el.tagName,
        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 160)
      };
    })()`
  );
  if (!point) throw new Error(`No visible clickable element matched text: ${text}`);
  return point;
}

async function moveCursorToPoint(tabId, point) {
  const response = await sendToContentScript(tabId, "moveToAndWait", [point.x, point.y, 900]);
  if (!response?.success) {
    throw new Error(response?.error || "Cursor movement failed");
  }
  return response.result || {};
}

async function clickAtPoint(tabId, point) {
  await moveCursorToPoint(tabId, point);
  const response = await sendToContentScript(tabId, "click", []);
  if (!response?.success) {
    throw new Error(response?.error || "Cursor click failed");
  }
}

// ---- Auto-inject content script on page load ----
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://') || tab.url.startsWith('chrome-search://')) return;
  if (injectedTabs.has(tabId)) return;
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content-scripts/cursor-agent.js']
    });
    injectedTabs.add(tabId);
  } catch {
    // Will retry on next interaction
  }
});

// ---- Content Script Injection Tracking ----
// (injectedTabs declared at top of file, line 4)

// Listen for content script ready pings and status queries
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg === 'hermes-cursor-ready' && sender.tab?.id) {
    injectedTabs.add(sender.tab.id);
  }
  if (msg && msg.type === 'hermes-cursor-status') {
    ensureContentScript(msg.tabId)
      .then((status) => sendResponse(status))
      .catch((error) => sendResponse({ injected: false, blocked: true, reason: String(error?.message || error) }));
    return true;
  }
});

// ---- Content Script Messaging ----
async function probeContentScript(tabId) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, { action: "getStatus", args: [] });
    if (response?.success) {
      injectedTabs.add(tabId);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

async function ensureContentScript(tabId) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id) {
    return { injected: false, blocked: true, reason: "Tab is no longer available" };
  }
  if (!isControllableUrl(tab.url)) {
    return { injected: false, blocked: true, reason: unsupportedUrlReason(tab.url), url: tab.url };
  }
  if (await probeContentScript(tabId)) {
    return { injected: true, url: tab.url };
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content-scripts/cursor-agent.js']
    });
    await new Promise(r => setTimeout(r, 150));
  } catch (error) {
    return { injected: false, blocked: true, reason: String(error?.message || error), url: tab.url };
  }
  if (await probeContentScript(tabId)) {
    return { injected: true, url: tab.url };
  }
  return { injected: false, blocked: true, reason: "Content script did not respond after injection", url: tab.url };
}

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms))
  ]);
}

async function sendToContentScript(tabId, action, args = []) {
  console.error(`sendToContentScript: starting ${action}`);
  const status = await withTimeout(
    ensureContentScript(tabId), 3000, `ensureContentScript(${action})`
  );
  console.error(`sendToContentScript: ensureContentScript done, injected=${status.injected}`);
  if (!status.injected) {
    throw new Error(status.reason || "Content script is not available");
  }
  const result = await withTimeout(
    chrome.tabs.sendMessage(tabId, { action, args }), 3000, `sendMessage(${action})`
  );
  console.error(`sendToContentScript: sendMessage done`);
  return result;
}

// ---- Browser Actions ----
async function runBrowserAction(action, state) {
  const type = action.type;
  console.error(`runBrowserAction: ${type}, tabId=${state.tabId}`);
  if (action.tabId) {
    state.tabId = action.tabId;
  }

  if (type === "goto") {
    let tab;
    if (state.tabId) {
      const current = await chrome.tabs.get(state.tabId);
      if (current.url === action.url && !action.reload) {
        tab = current;
      } else {
        tab = await chrome.tabs.update(state.tabId, { url: action.url, active: true });
      }
    } else {
      tab = await chrome.tabs.create({ url: action.url, active: true });
    }
    state.tabId = tab.id;
    state.lastUrl = tab.url || action.url;
    await new Promise((resolve) => setTimeout(resolve, action.waitMs || 2000));
    return { type, tabId: state.tabId, url: tab.url || action.url };
  }

  if (!state.tabId) {
    const tab = await currentTab();
    state.tabId = tab.id;
  }

  if (type === "wait") {
    await new Promise((resolve) => setTimeout(resolve, action.ms || 1000));
    return { type, ms: action.ms || 1000 };
  }

  if (type === "text") {
    const limit = action.maxChars || state.maxTextChars || 20000;
    const resp = await sendToContentScript(state.tabId, "getVisibleText", [limit]);
    return { type, text: String(resp?.result || "") };
  }

  if (type === "snapshot") {
    const resp = await sendToContentScript(state.tabId, "getDOMSnapshot");
    return { type, snapshot: resp?.result || [] };
  }

  if (type === "screenshot") {
    await ensureAttached(state.tabId);
    const capture = await chrome.debugger.sendCommand(
      { tabId: state.tabId },
      "Page.captureScreenshot",
      { format: "png", captureBeyondViewport: Boolean(action.full) }
    );
    return { type, base64: capture.data };
  }

  if (type === "close_tab") {
    const tab = await chrome.tabs.get(state.tabId).catch(() => null);
    if (tab?.url) state.lastUrl = tab.url;
    await chrome.tabs.remove(state.tabId);
    const closed = state.tabId;
    state.tabId = undefined;
    return { type, tabId: closed, url: state.lastUrl };
  }

  // ---- Cursor overlay actions (visible to user) ----
  if (type === "cursor_move") {
    const { x, y } = action;
    await sendToContentScript(state.tabId, "moveTo", [x, y]);
    return { type, x, y };
  }

  if (type === "cursor_click") {
    await sendToContentScript(state.tabId, "click", []);
    return { type };
  }

  if (type === "cursor_right_click") {
    await sendToContentScript(state.tabId, "rightClick", []);
    return { type };
  }

  if (type === "cursor_double_click") {
    await sendToContentScript(state.tabId, "dblClick", []);
    return { type };
  }

  if (type === "cursor_triple_click") {
    await sendToContentScript(state.tabId, "tripleClick", []);
    return { type };
  }

  if (type === "cursor_type") {
    const { text, append } = action;
    await sendToContentScript(state.tabId, "focusAndType", [text, { append: !!append }]);
    return { type, text };
  }

  if (type === "cursor_key") {
    const { key, modifiers } = action;
    await sendToContentScript(state.tabId, "keyPress", [key, modifiers || []]);
    return { type, key };
  }

  if (type === "cursor_drag") {
    const { x, y, duration } = action;
    await sendToContentScript(state.tabId, "dragTo", [x, y, duration || 500]);
    return { type, x, y };
  }

  if (type === "cursor_scroll") {
    const { deltaX, deltaY } = action;
    await sendToContentScript(state.tabId, "scroll", [deltaX || 0, deltaY || 0]);
    return { type, deltaX, deltaY };
  }

  if (type === "cursor_status") {
    const resp = await sendToContentScript(state.tabId, "getStatus");
    return { type, ...(resp?.result || {}) };
  }

  if (type === "cursor_hide") {
    await sendToContentScript(state.tabId, "hide", []);
    return { type };
  }

  // ---- CDP-based fallback actions ----
  if (type === "click_text") {
    const point = await findPointByText(state.tabId, action.text);
    await clickAtPoint(state.tabId, point);
    return { type, text: action.text, point };
  }

  if (type === "fill_selector") {
    const point = await findPointBySelector(state.tabId, action.selector);
    await clickAtPoint(state.tabId, point);
    const response = await sendToContentScript(state.tabId, "focusAndType", [
      String(action.value || ""),
      { append: Boolean(action.append) }
    ]);
    if (!response?.success) {
      throw new Error(response?.error || `Could not fill selector: ${action.selector}`);
    }
    return { type, selector: action.selector, point };
  }

  if (type === "click_selector") {
    const point = await findPointBySelector(state.tabId, action.selector);
    await clickAtPoint(state.tabId, point);
    return { type, selector: action.selector, point };
  }

  if (type === "evaluate") {
    const result = await evaluate(state.tabId, action.expression);
    return { type, result };
  }

  throw new Error(`Unsupported action type: ${type}`);
}

async function handleHostMessage(message) {
  const state = {
    maxTextChars: message.maxTextChars || 20000,
    tabId: message.useSelectedTab ? (await currentTab()).id : undefined
  };
  if (message?.type === "status") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const activeTab = tabs[0] || null;
    const contentScript = activeTab?.id
      ? await ensureContentScript(activeTab.id)
      : { injected: false, blocked: true, reason: "No active tab" };
    post({
      id: message.id,
      success: true,
      extension: "Hermes Chrome Bridge",
      active_tab: activeTab ? { id: activeTab.id, title: activeTab.title, url: activeTab.url } : null,
      content_script: contentScript
    });
    return;
  }
  if (message?.type !== "run") {
    throw new Error(`Unsupported host message type: ${message?.type}`);
  }
  const results = [];
  for (const action of message.actions || []) {
    const result = await runBrowserAction(action, state);
    if (result?.url) state.lastUrl = result.url;
    results.push(result);
  }
  const tab = state.tabId ? await chrome.tabs.get(state.tabId).catch(() => null) : null;
  post({ id: message.id, success: true, final_url: tab?.url || state.lastUrl, results });
}

connectHost();
