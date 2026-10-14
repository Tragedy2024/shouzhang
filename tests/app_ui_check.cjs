/* Shared dialog and theme behavior; no network, model calls or user storage. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

function harness(saved = 'system') {
  let doc;
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.events = {}; this.attrs = {}; this.dataset = {}; this.className = ''; this.textContent = ''; this.parent = null; this.open = false; }
    addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    append(...children) { children.forEach(child => { child.parent = this; this.children.push(child); }); }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); this.parent = null; }
    focus() { doc.activeElement = this; }
    showModal() { this.open = true; }
    close() { this.open = false; this.emit('close'); }
    emit(name, event = {}) { for (const handler of this.events[name] || []) handler(event); }
  }
  doc = { documentElement: new Element('html'), body: new Element('body'), activeElement: null, createElement: tag => new Element(tag), querySelectorAll: () => [] };
  const events = {};
  const stored = new Map([['zhilvji-hall-appearance', saved]]);
  const reads = [];
  const writes = [];
  const preference = { matches: true, events: [], addEventListener(name, handler) { if (name === 'change') this.events.push(handler); } };
  const win = { matchMedia: () => preference, addEventListener(name, handler) { (events[name] ||= []).push(handler); } };
  const localStorage = { getItem(key) { reads.push(key); return stored.get(key); }, setItem(key, value) { writes.push(key); stored.set(key, value); } };
  const context = vm.createContext({ document: doc, window: win, localStorage, Promise, Math, console });
  vm.runInContext(fs.readFileSync('static/app-ui.js', 'utf8'), context);
  return { ui: win.ZhilvjiUI, doc, stored, reads, writes, element: tag => new Element(tag), emitWindow(name, event = {}) { for (const handler of events[name] || []) handler(event); }, setSystemDark(value) { preference.matches = value; preference.events.forEach(handler => handler()); } };
}

(async () => {
  const h = harness();
  const trigger = h.element('button'); trigger.focus();
  const cancelled = h.ui.confirm({ title: '清空草稿', message: '清空这台设备上的草稿。', confirmLabel: '清空草稿', destructive: true });
  const dialog = h.doc.body.children[0];
  assert.equal(dialog.open, true);
  assert.equal(dialog.attrs['aria-labelledby'], 'appConfirmTitle');
  assert.equal(dialog.children[0].textContent, '清空草稿');
  const [cancel, accept] = dialog.children[2].children;
  assert.equal(h.doc.activeElement, cancel, 'Cancel receives initial focus for a destructive decision');
  assert.equal(accept.textContent, '清空草稿');
  assert.equal(accept.dataset.intent, 'danger');
  assert.equal(await h.ui.confirm({ title: '第二次确认', message: '不可叠加' }), false, 'Duplicate opens are rejected');
  assert.equal(h.doc.body.children.length, 1);
  let escapePrevented = false;
  dialog.emit('cancel', { preventDefault() { escapePrevented = true; } });
  assert.equal(escapePrevented, true);
  assert.equal(await cancelled, false, 'Escape cancels the operation');
  assert.equal(h.doc.body.children.length, 0);
  assert.equal(h.doc.activeElement, trigger, 'Dismissal returns focus to the original trigger');

  const explicitCancel = h.ui.confirm({ title: '取消验证', message: '可以取消。' });
  h.doc.body.children[0].children[2].children[0].emit('click');
  assert.equal(await explicitCancel, false);
  const confirmed = h.ui.confirm({ title: '确认验证', message: '只有点击确认才执行。', confirmLabel: '确认公开' });
  h.doc.body.children[0].children[2].children[1].emit('click');
  assert.equal(await confirmed, true, 'Only explicit confirmation accepts the operation');
  assert.equal(h.doc.body.children.length, 0);
  assert.equal(h.doc.activeElement, trigger);

  const creatorButton = h.element('button');
  const hallButton = h.element('button');
  h.ui.installTheme('creator', creatorButton);
  h.ui.installTheme('hall', hallButton);
  assert.equal(h.doc.documentElement.dataset.creatorTheme, 'dark');
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'dark');
  assert.equal(creatorButton.attrs['aria-pressed'], 'mixed');
  creatorButton.emit('click');
  assert.equal(h.stored.get('zhilvji-hall-appearance'), 'light');
  assert.equal(h.doc.documentElement.dataset.creatorTheme, 'light');
  h.emitWindow('pageshow');
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'light', 'Returning to a page reads the shared preference again');
  h.stored.set('zhilvji-hall-appearance', 'dark');
  h.emitWindow('storage', { key: 'zhilvji-hall-appearance' });
  assert.equal(h.doc.documentElement.dataset.creatorTheme, 'dark');
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'dark');
  assert.equal(hallButton.attrs['aria-pressed'], 'true');
  assert.match(hallButton.attrs['aria-label'], /深色外观/);
  h.stored.set('zhilvji-hall-appearance', 'light');
  h.emitWindow('storage', { key: 'unrelated-draft-key' });
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'dark', 'Unrelated storage events cannot change appearance');
  h.emitWindow('pageshow');
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'light');
  h.stored.set('zhilvji-hall-appearance', 'system'); h.emitWindow('pageshow'); h.setSystemDark(false);
  assert.equal(h.doc.documentElement.dataset.creatorTheme, 'light');
  assert.equal(h.doc.documentElement.dataset.hallTheme, 'light');
  assert(h.reads.length >= 8, 'Both scopes re-read persistent preferences on page/storage events');
  assert(h.reads.every(key => key === 'zhilvji-hall-appearance'));
  assert(h.writes.every(key => key === 'zhilvji-hall-appearance'));
  console.log('PASS: shared confirmation Cancel focus, Escape/cancel false, explicit confirm true, duplicate open prevention, trigger focus return; two-scope shared theme key and storage/pageshow/system refresh.');
})().catch(error => { console.error(error); process.exitCode = 1; });
