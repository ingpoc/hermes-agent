/**
 * Hermes Chrome Bridge — Floating Cursor Agent Overlay
 * 
 * Renders a visible floating cursor on every page that shows where
 * the AI agent is interacting. The cursor:
 * - Is a non-interfering overlay (pointerEvents: none on base layer)
 * - Animates smoothly between positions
 * - Passes real clicks through to the underlying page at the cursor position
 */
(() => {
  // Prevent double-injection
  if (document.documentElement.dataset.hermesAgentCursorInjected) return;
  document.documentElement.dataset.hermesAgentCursorInjected = "true";
  window.__hermesAgentCursorInjected = true; // for content script's own reference

  // ---- State ----
  let cursorX = -100;
  let cursorY = -100;
  let targetX = -100;
  let targetY = -100;
  let cursorEl = null;
  let pointerEl = null;
  let animationFrame = null;
  let isVisible = false;
  let cursorPhase = 'idle'; // idle | moving | clicking | arrived

  const HERMES_CURSOR_ID = 'hermes-agent-cursor-overlay';
  const POINTER_SVG = chrome.runtime.getURL('images/pointer-shape-animated.svg') + '?v=codex-like-2';

  // ---- Styles ----
  const css = `
    #${HERMES_CURSOR_ID} {
      position: fixed;
      z-index: 2147483647;
      pointer-events: none;
      left: 0;
      top: 0;
      will-change: transform;
      transition: opacity 0.2s ease;
      opacity: 0;
    }
    #${HERMES_CURSOR_ID}.hermes-visible {
      opacity: 1;
    }
    #${HERMES_CURSOR_ID} .hermes-cursor-pointer {
      width: 18px;
      height: 18px;
      display: block;
      transform: translate(-1px, -1px);
      transform-origin: 1px 1px;
      filter:
        drop-shadow(0 0 8px rgba(73, 182, 255, 0.55))
        drop-shadow(0 2px 3px rgba(0,0,0,0.32));
      transition: transform 0.12s ease;
      animation: hermes-pointer-idle 1.7s ease-in-out infinite;
      user-select: none;
      -webkit-user-drag: none;
    }
    #${HERMES_CURSOR_ID}.hermes-moving .hermes-cursor-pointer {
      animation: hermes-pointer-moving 0.48s ease-in-out infinite;
    }
    #${HERMES_CURSOR_ID} .hermes-cursor-pointer.hermes-clicking {
      transform: translate(-1px, -1px) scale(0.86);
      animation: none;
    }
    @keyframes hermes-pointer-idle {
      0%, 100% { transform: translate(-1px, -1px) rotate(0deg); }
      50% { transform: translate(0, -2px) rotate(0.35deg); }
    }
    @keyframes hermes-pointer-moving {
      0%, 100% { transform: translate(-1px, -1px) rotate(-2deg); }
      50% { transform: translate(1px, -3px) rotate(2deg); }
    }
  `;

  // ---- DOM Setup ----
  function createOverlay() {
    // Remove stale
    const old = document.getElementById(HERMES_CURSOR_ID);
    if (old) old.remove();

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    cursorEl = document.createElement('div');
    cursorEl.id = HERMES_CURSOR_ID;

    const pointerImg = document.createElement('img');
    pointerImg.className = 'hermes-cursor-pointer';
    pointerImg.src = POINTER_SVG;
    pointerImg.alt = '';
    pointerImg.decoding = 'async';
    pointerEl = pointerImg;

    cursorEl.appendChild(pointerImg);
    document.documentElement.appendChild(cursorEl);

    isVisible = false;
  }

  // ---- Animation Loop ----
  function animate() {
    const lerp = 0.25;
    cursorX += (targetX - cursorX) * lerp;
    cursorY += (targetY - cursorY) * lerp;

    if (cursorEl) {
      cursorEl.style.transform = `translate(${cursorX}px, ${cursorY}px)`;
    }

    // Arrival detection
    if (cursorPhase === 'moving') {
      const dist = Math.hypot(targetX - cursorX, targetY - cursorY);
      if (dist < 2) {
        cursorPhase = 'arrived';
        cursorEl?.classList.remove('hermes-moving');
        setTimeout(() => {
          if (cursorPhase === 'arrived') {
            cursorPhase = 'idle';
          }
        }, 2000);
      }
    }

    animationFrame = requestAnimationFrame(animate);
  }

  // ---- Actions ----
  function moveTo(x, y) {
    if (!cursorEl) createOverlay();
    targetX = x;
    targetY = y;
    if (!isVisible) {
      cursorEl.classList.add('hermes-visible');
      isVisible = true;
    }
    cursorPhase = 'moving';
    cursorEl.classList.add('hermes-moving');
  }

  function moveToAndWait(x, y, timeoutMs = 900) {
    moveTo(x, y);
    return new Promise((resolve) => {
      const started = performance.now();
      function check(now) {
        const dist = Math.hypot(targetX - cursorX, targetY - cursorY);
        if (dist < 3 || now - started >= timeoutMs) {
          resolve(getStatus());
          return;
        }
        requestAnimationFrame(check);
      }
      requestAnimationFrame(check);
    });
  }

  function click() {
    if (!cursorEl) return;
    pointerEl?.classList.add('hermes-clicking');
    setTimeout(() => pointerEl?.classList.remove('hermes-clicking'), 140);

    // Hide cursor momentarily so elementFromPoint gets the real page element
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');

    if (el) {
      const scrollX = window.scrollX || 0;
      const scrollY = window.scrollY || 0;
      const opts = { bubbles: true, cancelable: true, view: window };
      el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
      el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
      el.dispatchEvent(new MouseEvent('click', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
    }
    flashLabel('click');
  }

  function tripleClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      const opts = { bubbles: true, cancelable: true, view: window };
      [1, 2, 3].forEach(() => {
        el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY }));
        el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY }));
        el.dispatchEvent(new MouseEvent('click', { ...opts, clientX: cursorX, clientY: cursorY }));
      });
    }
    flashLabel('triple-click');
  }

  function rightClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      el.dispatchEvent(new MouseEvent('contextmenu', {
        bubbles: true, cancelable: true, view: window,
        clientX: cursorX, clientY: cursorY
      }));
    }
    flashLabel('right-click');
  }

  function dblClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      const opts = { bubbles: true, cancelable: true, view: window };
      el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY }));
      el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY }));
      el.dispatchEvent(new MouseEvent('dblclick', { ...opts, clientX: cursorX, clientY: cursorY }));
    }
    flashLabel('double-click');
  }

  function focusAndType(text, opts = {}) {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (!el) return;
    el.focus();
    if (opts.append && el.value !== undefined) {
      // Insert text at cursor / append
      const start = el.selectionStart || el.value.length;
      const end = el.selectionEnd || el.value.length;
      el.value = el.value.slice(0, start) + text + el.value.slice(end);
      el.selectionStart = el.selectionEnd = start + text.length;
    } else if (el.value !== undefined) {
      el.value = text;
    } else if ('innerText' in el) {
      el.innerText = text;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    flashLabel('type');
  }

  function keyPress(key, modifiers = []) {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY) || document.activeElement || document.body;
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    const opts = {
      bubbles: true, cancelable: true, view: window,
      key, code: key,
      ctrlKey: modifiers.includes('control') || modifiers.includes('ctrl'),
      shiftKey: modifiers.includes('shift'),
      altKey: modifiers.includes('alt') || modifiers.includes('option'),
      metaKey: modifiers.includes('command') || modifiers.includes('cmd'),
    };
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keypress', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
    flashLabel(`⌨ ${key}`);
  }

  function dragTo(endX, endY, duration = 500) {
    return new Promise((resolve) => {
      const startX = cursorX;
      const startY = cursorY;
      const startTime = performance.now();
      const wasVisible = isVisible;
      if (wasVisible) cursorEl.classList.remove('hermes-visible');
      const el = document.elementFromPoint(cursorX, cursorY);
      if (wasVisible) cursorEl.classList.add('hermes-visible');
      if (el) {
        el.dispatchEvent(new MouseEvent('mousedown', {
          bubbles: true, cancelable: true, view: window,
          clientX: cursorX, clientY: cursorY
        }));
      }
      function step(now) {
        const t = Math.min(1, (now - startTime) / duration);
        const x = startX + (endX - startX) * t;
        const y = startY + (endY - startY) * t;
        moveTo(x, y);
        if (el) {
          el.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
          }));
        }
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          if (el) {
            el.dispatchEvent(new MouseEvent('mouseup', {
              bubbles: true, cancelable: true, view: window,
              clientX: endX, clientY: endY
            }));
          }
          flashLabel('drag');
          resolve();
        }
      }
      requestAnimationFrame(step);
    });
  }

  function scroll(deltaX, deltaY) {
    const el = document.elementFromPoint(cursorX, cursorY) || document.documentElement;
    el.scrollBy(deltaX, deltaY);
    const we = new WheelEvent('wheel', {
      bubbles: true, cancelable: true, view: window,
      clientX: cursorX, clientY: cursorY,
      deltaX, deltaY
    });
    el.dispatchEvent(we);
    flashLabel('scroll');
  }

  function getVisibleText(maxChars) {
    const text = (document.body?.innerText || '').trim();
    return text.slice(0, maxChars);
  }

  function getDOMSnapshot() {
    return Array.from(
      document.querySelectorAll('a,button,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,p,li,div,span,td,th')
    ).slice(0, 250).map((el, i) => ({
      i,
      tag: el.tagName,
      role: el.getAttribute('role') || '',
      text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 200),
      href: el.href || ''
    }));
  }

  function flashLabel(label) {
    return label;
  }

  function getStatus() {
    return {
      visible: isVisible,
      x: Math.round(cursorX),
      y: Math.round(cursorY),
      phase: cursorPhase,
      url: location.href,
      title: document.title
    };
  }

  function hide() {
    if (cursorEl) cursorEl.classList.remove('hermes-visible');
    if (cursorEl) cursorEl.classList.remove('hermes-moving');
    isVisible = false;
    cursorPhase = 'idle';
  }

  function destroy() {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    const old = document.getElementById(HERMES_CURSOR_ID);
    if (old) old.remove();
    window.__hermesAgentCursorInjected = false;
  }

  // ---- Message Listener (from service worker) ----
  const actions = {
    moveTo, moveToAndWait, click, tripleClick, rightClick, dblClick,
    focusAndType, keyPress, dragTo, scroll,
    getVisibleText, getDOMSnapshot,
    getStatus, hide, destroy
  };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const fn = actions[msg.action];
    if (!fn) {
      sendResponse({ success: false, error: `Unknown action: ${msg.action}` });
      return true;
    }
    try {
      const result = fn(...(msg.args || []));
      if (result instanceof Promise) {
        result.then(r => sendResponse({ success: true, result: r }))
              .catch(e => sendResponse({ success: false, error: String(e) }));
        return true;
      }
      sendResponse({ success: true, result });
    } catch (err) {
      sendResponse({ success: false, error: String(err) });
    }
    return true;
  });

  // ---- Init ----
  createOverlay();
  animate();

  // Notify service worker that content script is ready
  try { chrome.runtime.sendMessage('hermes-cursor-ready'); } catch {}
})();
