(() => {
  'use strict';
  const modes = ['system', 'light', 'dark'];
  const labels = { system: '系统', light: '浅色', dark: '深色' };
  const themeKey = 'zhilvji-hall-appearance';
  let confirming = false;
  function installTheme(scope, button) {
    const root = document.documentElement || document.body;
    let mode = 'system';
    let preference;
    const read = () => { try { const saved = localStorage.getItem(themeKey); if (modes.includes(saved)) mode = saved; } catch { /* Use system appearance. */ } };
    read();
    try { preference = window.matchMedia?.('(prefers-color-scheme: dark)'); } catch { /* Light fallback. */ }
    const render = () => {
      const effective = mode === 'system' ? (preference?.matches ? 'dark' : 'light') : mode;
      root.dataset[`${scope}Theme`] = effective;
      root.dataset[`${scope}ThemeMode`] = mode;
      if (!button) return;
      const next = modes[(modes.indexOf(mode) + 1) % modes.length];
      button.textContent = `外观 · ${labels[mode]}`;
      button.setAttribute('aria-pressed', mode === 'system' ? 'mixed' : String(mode === 'dark'));
      button.setAttribute('aria-label', `当前${mode === 'system' ? `跟随系统（${labels[effective]}）` : `${labels[effective]}外观`}，切换为${next === 'system' ? '跟随系统' : labels[next]}`);
    };
    button?.addEventListener('click', () => {
      mode = modes[(modes.indexOf(mode) + 1) % modes.length];
      try { localStorage.setItem(themeKey, mode); } catch { /* Still apply for this visit. */ }
      render();
    });
    const followSystem = () => { if (mode === 'system') render(); };
    if (preference?.addEventListener) preference.addEventListener('change', followSystem);
    else preference?.addListener?.(followSystem);
    window.addEventListener('pageshow', () => { read(); render(); });
    window.addEventListener('storage', (event) => { if (event.key === themeKey) { read(); render(); } });
    render();
  }
  function confirmAction({ title, message, confirmLabel = '确认', destructive = false }) {
    if (confirming) return Promise.resolve(false);
    confirming = true;
    const trigger = document.activeElement;
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'app-confirm-dialog';
      dialog.setAttribute('aria-labelledby', 'appConfirmTitle');
      dialog.setAttribute('aria-describedby', 'appConfirmMessage');
      const heading = document.createElement('h2'); heading.id = 'appConfirmTitle'; heading.textContent = title;
      const description = document.createElement('p'); description.id = 'appConfirmMessage'; description.textContent = message;
      const actions = document.createElement('div'); actions.className = 'app-confirm-actions';
      const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn-secondary'; cancel.textContent = '取消';
      const accept = document.createElement('button'); accept.type = 'button'; accept.className = 'app-confirm-primary'; accept.textContent = confirmLabel; accept.dataset.intent = destructive ? 'danger' : 'primary';
      let accepted = false;
      cancel.addEventListener('click', () => dialog.close());
      accept.addEventListener('click', () => { accepted = true; dialog.close(); });
      dialog.addEventListener('cancel', (event) => { event.preventDefault(); dialog.close(); });
      dialog.addEventListener('close', () => { confirming = false; dialog.remove(); trigger?.focus?.({ preventScroll: true }); resolve(accepted); });
      actions.append(cancel, accept); dialog.append(heading, description, actions); document.body.append(dialog);
      dialog.showModal(); cancel.focus();
    });
  }
  function resizeTextarea(element) {
    if (!element || !element.offsetWidth) return;
    const baseline = element.id === 'journalBody' ? 280 : 112;
    element.style.height = 'auto';
    element.style.height = `${Math.max(baseline, Math.min(640, element.scrollHeight + 2))}px`;
  }
  document.querySelectorAll?.('textarea').forEach((element) => {
    element.addEventListener('input', () => resizeTextarea(element));
    element.addEventListener('compositionend', () => resizeTextarea(element));
    resizeTextarea(element);
  });
  window.ZhilvjiUI = { confirm: confirmAction, installTheme, resizeTextarea };
})();
