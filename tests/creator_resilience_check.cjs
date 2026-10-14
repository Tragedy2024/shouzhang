/* Offline browser-lifecycle regressions. No real storage or network is used. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { File } = require('node:buffer');
const { randomUUID } = require('node:crypto');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attrs = {};
    this.events = {}; this.className = ''; this.textContent = ''; this.value = ''; this.hidden = false;
    this.disabled = false; this.style = {}; this.parentElement = null; this.clickCount = 0;
  }
  get classList() {
    const element = this;
    return {
      contains(name) { return element.className.split(/\s+/).includes(name); },
      add(...names) { element.className = [...new Set([...element.className.split(/\s+/).filter(Boolean), ...names])].join(' '); },
      remove(...names) { element.className = element.className.split(/\s+/).filter(name => !names.includes(name)).join(' '); },
      toggle(name, force) { const active = force ?? !this.contains(name); active ? this.add(name) : this.remove(name); return active; }
    };
  }
  append(...elements) { for (const element of elements) { element.parentElement = this; this.children.push(element); } }
  replaceChildren(...elements) { for (const element of this.children) element.parentElement = null; this.children = []; this.append(...elements); }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  removeEventListener(name, handler) { this.events[name] = (this.events[name] || []).filter(value => value !== handler); }
  dispatchEvent(event) { for (const handler of this.events[event.type] || []) handler(event); return !event.defaultPrevented; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name]; }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() { this.focused = true; }
  select() {}
  scrollIntoView() {}
  click() {
    if (this.disabled) return;
    this.clickCount += 1;
    this.dispatchEvent({ type: 'click', target: this, preventDefault() {} });
  }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(value => value !== this); }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    const match = selector.match(/^(\w+)?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/);
    if (!match) throw new Error(`Unsupported offline selector: ${selector}`);
    if (match[1] && this.tagName !== match[1].toUpperCase()) return false;
    if (match[2]) {
      const key = match[2].replace(/^data-/, '').replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      const value = match[2].startsWith('data-') ? this.dataset[key] : this.attrs[match[2]];
      if (value === undefined || (match[3] !== undefined && value !== match[3])) return false;
    }
    return true;
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector); }
  querySelectorAll(selector) {
    if (selector.includes(',')) return [...new Set(selector.split(',').flatMap(value => this.querySelectorAll(value)))];
    const parts = selector.split(' ');
    const result = [];
    const visit = element => {
      for (const child of element.children) {
        if (child.matches(parts.at(-1)) && (parts.length === 1 || child.parentElement?.closest(parts[0]))) result.push(child);
        visit(child);
      }
    };
    visit(this); return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message, timeout = 280) {
  const start = Date.now();
  while (Date.now() - start < timeout) { if (predicate()) return; await sleep(3); }
  assert(predicate(), message);
}
async function bounded(promise, message, timeout = 320) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), timeout); })]);
  } finally { clearTimeout(timer); }
}
const clone = value => JSON.parse(JSON.stringify(value));
// IndexedDB returns independent structured records while preserving File data.
// Keep that boundary when a completely new VM opens the same simulated store.
function storageClone(value) {
  if (value instanceof File) return new File([value], value.name, { type: value.type, lastModified: value.lastModified });
  if (value instanceof Blob) return new Blob([value], { type: value.type });
  if (Array.isArray(value)) return Array.from(value, storageClone);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, storageClone(item)]));
  return value;
}
const result = title => ({
  journal: `${title}\n\n离线测试正文。`, sections: { title, body: '离线测试正文。', tags: [] },
  style: 'xiaohongshu', date: '', weather: '', address: '', datetime_str: '',
  image_filenames: [], image_urls: [], image_metadata: [], warnings: []
});
const draft = title => ({
  schema: 2, savedAt: 1, style: 'xiaohongshu', form: {}, result: title ? result(title) : null,
  history: [], future: [], pendingJob: null, notices: [], fileCount: 0, fileManifest: [], files: [], preview: null
});

function harness(initial = {}) {
  const config = { openHang: false, getHang: false, putHang: false, getDelay: 0, putDelay: 0, ...initial };
  const timers = new Set();
  const calls = [];
  const stats = { events: [], aborts: 0, closes: 0, preventedCommits: 0, openCalls: 0 };
  let alive = true;
  const persistence = initial.persistence || { stored: storageClone(initial.stored), values: new Map() };
  const scheduled = (fn, milliseconds) => {
    const id = setTimeout(() => { timers.delete(id); if (alive) fn(); }, milliseconds);
    timers.add(id); return id;
  };
  const fastTimer = (fn, milliseconds = 0, ...args) => {
    const delay = milliseconds >= 25000 ? 75 : milliseconds === 5000 ? 40 : milliseconds === 1800 ? 25
      : milliseconds === 1250 ? 15 : milliseconds === 2000 ? 20 : milliseconds === 450 ? 12
        : milliseconds === 650 || milliseconds === 700 ? 15 : milliseconds;
    return scheduled(() => fn(...args), delay);
  };
  const cancelTimer = id => { clearTimeout(id); timers.delete(id); };
  const html = fs.readFileSync('templates/index.html', 'utf8');
  const elements = {};
  for (const match of html.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const element = new Element(match[1]);
    element.hidden = /\bhidden\b/.test(match[2]); element.disabled = /\bdisabled\b/.test(match[2]);
    elements[match[3]] = element;
  }
  const styles = ['xiaohongshu', 'ins', 'japanese', 'film', 'muji'].map(style => { const element = new Element('button'); element.className = 'style-card'; element.dataset.style = style; return element; });
  const stages = ['upload', 'vision', 'location', 'writing'].map(stage => { const element = new Element('li'); element.dataset.stage = stage; return element; });
  const tones = ['literary', 'girly', 'healing', 'moments', 'magazine'].map(tone => { const element = new Element('button'); element.className = 'btn-regen'; element.dataset.tone = tone; return element; });
  const document = {
    body: new Element('body'), visibilityState: 'visible', events: {},
    get hidden() { return this.visibilityState !== 'visible'; },
    getElementById(id) { assert(elements[id], `Missing template element ${id}`); return elements[id]; },
    createElement: tag => new Element(tag),
    querySelectorAll(selector) { if (selector === '.style-card') return styles; if (selector === '.stage-list li') return stages; if (selector === '.btn-regen') return tones; throw new Error(selector); },
    addEventListener(name, handler) { (this.events[name] ||= []).push(handler); },
    removeEventListener(name, handler) { this.events[name] = (this.events[name] || []).filter(value => value !== handler); },
    dispatchEvent(event) { for (const handler of this.events[event.type] || []) handler(event); },
    execCommand() { return true; }, hasFocus() { return true; }
  };
  const window = {
    events: {}, ZhilvjiUI: { confirm: async () => true, alert: async () => {} },
    addEventListener(name, handler) { (this.events[name] ||= []).push(handler); },
    removeEventListener(name, handler) { this.events[name] = (this.events[name] || []).filter(value => value !== handler); },
    dispatchEvent(event) { for (const handler of this.events[event.type] || []) handler(event); }
  };
  const values = persistence.values;
  if (initial.fallback) values.set('zhilvji-draft-v2', JSON.stringify(initial.fallback));
  const localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  const indexedDB = {
    open() {
      stats.openCalls += 1;
      const request = {};
      if (config.openHang) return request;
      const connection = {
        closed: false, objectStoreNames: { contains: () => true }, createObjectStore() {},
        close() { this.closed = true; stats.closes += 1; },
        transaction() {
          if (this.closed) throw new Error('InvalidStateError: closed offline database');
          const tx = {
            aborted: false, error: null, kind: '',
            abort() {
              if (this.aborted) return;
              this.aborted = true; stats.aborts += 1; stats.events.push(`tx-abort:${this.kind}`);
              this.error = new Error('AbortError: offline transaction cancelled');
              scheduled(() => this.onabort?.(), 0);
            },
            objectStore() {
              const operation = (kind, value) => {
                tx.kind = kind;
                stats.events.push(`tx-start:${kind}`);
                const snapshot = storageClone(value);
                const req = { result: kind === 'get' ? storageClone(persistence.stored) : undefined };
                const complete = () => {
                  if (tx.aborted) { stats.preventedCommits += 1; return; }
                  if (kind === 'put') persistence.stored = snapshot;
                  if (kind === 'delete') persistence.stored = undefined;
                  stats.events.push(`tx-complete:${kind}`);
                  tx.oncomplete?.();
                };
                if ((kind === 'get' && config.getHang) || (kind === 'put' && config.putHang)) return req;
                scheduled(complete, kind === 'get' ? config.getDelay : kind === 'put' ? config.putDelay : 0);
                return req;
              };
              return { get: () => operation('get'), put: value => operation('put', value), delete: () => operation('delete') };
            }
          };
          return tx;
        }
      };
      request.result = connection;
      scheduled(() => request.onsuccess?.(), 0);
      return request;
    }
  };
  const abortError = () => { const error = new Error('Offline aborted request'); error.name = 'AbortError'; return error; };
  const bodyWait = signal => new Promise((_, reject) => {
    if (signal?.aborted) { reject(abortError()); return; }
    signal?.addEventListener('abort', () => reject(abortError()), { once: true });
  });
  const response = (data, options = {}) => ({
    ok: (options.status || 200) < 400, status: options.status || 200,
    headers: { get: () => options.blob ? 'image/png' : 'application/json' },
    async json() { if (options.jsonHang) return bodyWait(options.signal); return data; },
    async blob() { if (options.blobHang) return bodyWait(options.signal); return new Blob(['offline-png'], { type: 'image/png' }); },
    async text() { if (options.jsonHang) return bodyWait(options.signal); return JSON.stringify(data); },
    body: { cancel: async () => {} }
  });
  const api = {
    create: () => response({ job_id: 'offline-job', status: 'queued', stage: 'upload' }),
    poll: (_, options) => response({ job_id: 'offline-job', status: 'completed', stage: 'done', result: result('已完成的测试作品') }, { signal: options.signal }),
    export: options => response(null, { blob: true, signal: options.signal }),
    head: () => response(null)
  };
  const fetch = async (url, options = {}) => {
    assert(alive, 'The disposed offline page must not send new requests.');
    calls.push({ url, options });
    if (url === '/api/jobs') { stats.events.push('create-request'); return api.create(options); }
    if (url.startsWith('/api/jobs/')) { stats.events.push('poll-request'); return api.poll(url, options); }
    if (url === '/api/export-image') return api.export(options);
    if (url.startsWith('/uploads/')) return api.head(url, options);
    if (url === '/api/regenerate') return response({ journal: '离线改写\n\n正文', sections: { title: '离线改写', body: '正文', tags: [] } });
    throw new Error(`Unexpected offline route ${url}`);
  };
  let objectCounter = 0;
  const objectURLs = new Map();
  const URL = { createObjectURL(blob) { const url = `blob:offline-${++objectCounter}`; objectURLs.set(url, blob); return url; }, revokeObjectURL(url) { objectURLs.delete(url); } };
  class CustomEvent { constructor(type, options = {}) { this.type = type; this.detail = options.detail; } }
  const context = vm.createContext({ document, window, localStorage, indexedDB, URL, console, Date, Math, Object, JSON, String, Array, Set, Map, Promise, Error, Blob, File, FormData, AbortController, CustomEvent, crypto: { randomUUID }, setTimeout: fastTimer, clearTimeout: cancelTimer, fetch, confirm: () => true, navigator: { clipboard: { writeText: async () => {} } } });
  let source = fs.readFileSync('static/app.js', 'utf8');
  source = source.replace(/\}\)\(\);\s*$/, 'globalThis.testApp = { state, addPhotos, generate, restoreDraft, runPolling, clearDraft, saveDraft, editResult, flushEditor, schedulePreview, checkUploadedPhotos, changeResultPhotos }; })();');
  vm.runInContext(source, context);
  const makeFile = name => new File(['synthetic-photo'], `${name}.jpg`, { type: 'image/jpeg', lastModified: 1 });
  return {
    app: context.testApp, elements, document, window, config, api, calls, stats, values, response, persistence,
    get stored() { return persistence.stored; },
    async ready() { await until(() => !elements.uploadArea.disabled && !elements.imageInput.disabled && !elements.submitBtn.disabled, 'Draft recovery must release creator controls within its deadline.'); },
    choose(name) {
      const before = elements.imageInput.clickCount;
      elements.uploadArea.click();
      if (elements.imageInput.clickCount === before || elements.imageInput.disabled) return false;
      elements.imageInput.files = [makeFile(name)]; elements.imageInput.value = name;
      elements.imageInput.dispatchEvent({ type: 'change', target: elements.imageInput });
      assert.equal(elements.imageInput.value, '', 'The file input must reset to allow another selection.');
      return true;
    },
    drop(name) {
      if (elements.uploadArea.disabled) return false;
      let prevented = false;
      elements.uploadArea.dispatchEvent({ type: 'drop', target: elements.uploadArea, dataTransfer: { files: [makeFile(name)] }, preventDefault() { prevented = true; } });
      return prevented;
    },
    hide(persisted = true) { document.visibilityState = 'hidden'; document.dispatchEvent({ type: 'visibilitychange' }); window.dispatchEvent({ type: 'pagehide', persisted }); },
    show(persisted = true) { document.visibilityState = 'visible'; window.dispatchEvent({ type: 'pageshow', persisted }); document.dispatchEvent({ type: 'visibilitychange' }); },
    dispose() { alive = false; for (const timer of timers) clearTimeout(timer); timers.clear(); }
  };
}

const scenarios = [];
const test = (name, run) => scenarios.push({ name, run });

test('hung database open falls back to text draft and enables real file controls', async h => {
  await h.ready();
  assert.equal(h.app.state.result.sections.title, '文字后备');
  assert(h.choose('open-fallback-choice'));
  assert(h.drop('open-fallback-drop'));
  assert.equal(h.app.state.files.length, 2);
});
scenarios.at(-1).initial = { openHang: true, fallback: draft('文字后备') };

test('hung database read is aborted and cannot lock photo selection', async h => {
  await h.ready();
  assert(h.stats.aborts > 0, 'A timed-out read transaction must be aborted.');
  assert(h.choose('read-fallback-choice'));
  assert(h.drop('read-fallback-drop'));
  assert.equal(h.app.state.files.length, 2);
});
scenarios.at(-1).initial = { getHang: true, fallback: draft('读取后备') };

test('late old draft cannot overwrite new input or newly selected photos', async h => {
  await h.ready();
  h.app.editResult('title', '新编辑标题'); h.app.flushEditor();
  h.elements.location.value = '新的测试地点';
  assert(h.choose('new-after-read-deadline'));
  await sleep(145);
  assert.equal(h.app.state.result.sections.title, '新编辑标题');
  assert.equal(h.elements.location.value, '新的测试地点');
  assert.equal(h.app.state.files[0].file.name, 'new-after-read-deadline.jpg');
  assert(h.stats.aborts > 0);
});
scenarios.at(-1).initial = { getDelay: 115, stored: { ...draft('过时的数据库标题'), savedAt: 2 }, fallback: draft('及时恢复的标题') };

test('an expired HEAD response removes its original photo after the user reorders the result', async h => {
  await h.ready();
  const expiredName = `${'a'.repeat(32)}.jpg`;
  const validName = `${'b'.repeat(32)}.jpg`;
  h.app.state.result = {
    ...result('重排后仍然保留的正文'), image_filenames: [expiredName, validName],
    image_urls: [`/uploads/${expiredName}`, `/uploads/${validName}`],
    image_metadata: [{ filename: expiredName }, { filename: validName }]
  };
  let resolveExpired;
  h.api.head = url => url.endsWith(expiredName)
    ? new Promise(resolve => { resolveExpired = resolve; }) : h.response(null);
  const checking = h.app.checkUploadedPhotos();
  await until(() => !!resolveExpired, 'The expired photo HEAD request must actually be in flight.');
  h.app.changeResultPhotos(0, 1, 'move');
  assert.deepEqual([...h.app.state.result.image_filenames], [validName, expiredName]);
  resolveExpired(h.response(null, { status: 404 }));
  await bounded(checking, 'The delayed photo check must finish.');
  assert.deepEqual([...h.app.state.result.image_filenames], [validName], 'Reordering must not make an expired photo response delete a different, valid photo.');
  assert.deepEqual([...h.app.state.result.image_urls], [`/uploads/${validName}`]);
  assert.deepEqual(h.app.state.result.image_metadata.map(item => item.filename), [validName]);
  assert.equal(h.app.state.result.sections.title, '重排后仍然保留的正文');
  assert(h.app.state.history.every(snapshot => !snapshot.image_filenames.includes(expiredName)), 'Undo history must not restore the expired photo.');
});

test('photos selected immediately before pagehide restore in a completely new page VM', async h => {
  await h.ready();
  assert.equal(h.stored, undefined, 'This scenario must start without any previously persisted photos.');
  h.elements.location.value = '离开前刚填写的测试地点';
  h.elements.location.dispatchEvent({ type: 'input', target: h.elements.location });
  assert(h.choose('immediate-before-navigation'));
  assert(h.drop('immediate-drop-before-navigation'));
  const oldState = h.app.state;
  const ids = [...oldState.files].map(entry => entry.id);
  // Do not wait for a debounce, a save promise, or a microtask before leaving.
  const startedWrites = h.stats.events.filter(event => event === 'tx-start:put').length;
  h.hide(false);
  assert(h.stats.events.filter(event => event === 'tx-start:put').length > startedWrites,
    'Departure must synchronously start the newest full photo snapshot on the already open DB.');
  await until(() => h.stored?.files.length === 2, 'The departure photo snapshot must commit without a page resume.');
  await until(() => h.stats.closes > 0, 'The departure write must release its database connection.');
  const persistence = h.persistence;
  h.dispose();
  oldState.files.splice(0);
  const returned = harness({ persistence });
  try {
    await returned.ready();
    assert.notEqual(returned.app.state, oldState, 'Recovery must use a new app closure, rather than a bfcache resume.');
    assert.deepEqual([...returned.app.state.files].map(entry => entry.id), ids);
    assert.deepEqual([...returned.app.state.files].map(entry => entry.file.name),
      ['immediate-before-navigation.jpg', 'immediate-drop-before-navigation.jpg']);
    assert.equal(await returned.app.state.files[0].file.text(), 'synthetic-photo', 'IndexedDB recovery must restore the real File bytes.');
    assert.equal(returned.elements.location.value, '离开前刚填写的测试地点');
    assert(returned.choose('choice-after-new-page-recovery'));
    assert(returned.drop('drop-after-new-page-recovery'));
    assert.equal(returned.app.state.files.length, 4);
    assert.equal(returned.elements.submitBtn.disabled, false);
  } finally { returned.dispose(); }
});

test('job polling starts independently of a never-completing draft write', async h => {
  await h.ready();
  h.config.putHang = true;
  assert(h.choose('generate-with-slow-save'));
  await bounded(h.app.generate(), 'Generation must not wait forever for a draft write.');
  assert.equal(h.app.state.result.sections.title, '已完成的测试作品');
  const poll = h.stats.events.indexOf('poll-request');
  const abort = h.stats.events.indexOf('tx-abort:put');
  assert(poll >= 0 && (abort < 0 || poll < abort), 'Progress polling must begin before the background draft write times out.');
  assert.equal(h.app.state.generating, false);
  assert.equal(h.elements.uploadArea.disabled, false);
  await until(() => h.stats.aborts > 0, 'A stalled background write must eventually be aborted.');
});

test('timed-out writes cannot commit later or resurrect a cleared draft', async h => {
  await h.ready();
  h.config.putDelay = 125;
  assert(h.choose('late-write-photo'));
  await bounded(h.app.saveDraft(), 'Saving must finish its timeout fallback.');
  assert(h.stats.aborts > 0, 'Timed-out writes must abort their transaction.');
  await bounded(h.app.clearDraft(), 'Clearing must not wait forever for the write queue.');
  await sleep(155);
  assert.equal(h.stored, undefined, 'An aborted late write must not recreate the cleared draft.');
  assert.equal(h.values.size, 0);
  assert(h.stats.preventedCommits > 0, 'The mock must actually attempt and prevent the late commit.');
});

test('hidden old poll responses are ignored; resume fetches fresh state and two returns allow change/drop', async h => {
  await h.ready();
  assert(h.choose('before-hall')); assert(h.drop('before-hall-drop'));
  h.app.state.result = result('返回前保留的作品');
  h.app.state.pendingJob = { job_id: 'offline-job', status: 'running', stage: 'writing' };
  let resolveOld;
  h.api.poll = () => new Promise(resolve => { resolveOld = resolve; });
  const oldPolling = h.app.runPolling('offline-job');
  await until(() => !!resolveOld, 'The old poll must actually be in flight.');
  const previous = h.app.state.result;
  h.hide(true);
  resolveOld(h.response({ job_id: 'offline-job', status: 'completed', stage: 'done', result: result('隐藏时的旧响应') }));
  await bounded(oldPolling, 'The hidden poll must be stopped or ignored.');
  assert.equal(h.app.state.result, previous, 'A response arriving after pagehide must not replace the visible work.');
  const pollCount = h.calls.filter(call => call.url.startsWith('/api/jobs/')).length;
  h.api.poll = (_, options) => h.response({ job_id: 'offline-job', status: 'completed', stage: 'done', result: result('返回后的最新作品') }, { signal: options.signal });
  h.show(true);
  await until(() => h.app.state.result.sections.title === '返回后的最新作品', 'Returning from hall must fetch actual task status.');
  assert.equal(h.calls.filter(call => call.url.startsWith('/api/jobs/')).length, pollCount + 1,
    'pageshow plus visibilitychange must resume one polling chain, not duplicate progress requests.');
  await h.ready();
  assert(h.choose('first-return-choice')); assert(h.drop('first-return-drop'));
  h.hide(true); h.show(true);
  await h.ready();
  assert(h.choose('second-return-choice')); assert(h.drop('second-return-drop'));
  assert.equal(h.app.state.files.length, 6);
  assert.equal(h.elements.submitBtn.disabled, false);
  assert.equal(h.app.state.generating, false);
  assert(h.stats.closes > 0, 'Navigating away must close the old IndexedDB connection.');
});

test('queued and running phases keep observing the same job until completion', async h => {
  await h.ready();
  assert(h.choose('staged-generation'));
  h.app.state.result = result('生成期间保留的旧作品');
  let observed = 0;
  h.api.poll = (_, options) => {
    observed += 1;
    return h.response(observed === 1 ? { job_id: 'offline-job', status: 'queued', stage: 'upload' }
      : observed === 2 ? { job_id: 'offline-job', status: 'running', stage: 'writing' }
        : { job_id: 'offline-job', status: 'completed', stage: 'done', result: result('三次查询后完成的作品') },
    { signal: options.signal });
  };
  const generation = h.app.generate();
  await until(() => observed === 1, 'The first real progress query must observe the queued phase.');
  assert.equal(h.app.state.result.sections.title, '生成期间保留的旧作品');
  assert.equal(h.app.state.generating, true);
  assert.equal(h.elements.uploadArea.disabled, true);
  await bounded(generation, 'Queued/running states must keep polling instead of waiting for a refresh.');
  assert.equal(observed, 3);
  assert.equal(h.app.state.result.sections.title, '三次查询后完成的作品');
  assert.equal(h.app.state.pendingJob, null);
  assert.equal(h.app.state.generating, false);
  assert.equal(h.calls.filter(call => call.url === '/api/jobs').length, 1);
});

test('progress response headers do not cancel the JSON body timeout', async h => {
  await h.ready();
  h.app.state.pendingJob = { job_id: 'offline-job', status: 'running', stage: 'writing' };
  h.api.poll = (_, options) => h.response(null, { jsonHang: true, signal: options.signal });
  await bounded(h.app.runPolling('offline-job'), 'A hanging progress JSON body must be bounded.');
  assert.equal(h.app.state.generating, false);
  assert.equal(h.elements.continueJobBtn.hidden, false);
  assert.equal(h.elements.uploadArea.disabled, false);
  assert.equal(h.app.state.pendingJob.job_id, 'offline-job');
});

test('preview response headers do not cancel the PNG body timeout', async h => {
  await h.ready();
  h.app.state.result = result('预览超时仍保留的正文');
  h.api.export = options => h.response(null, { blob: true, blobHang: true, signal: options.signal });
  h.app.schedulePreview(true);
  await until(() => !h.elements.retryPreviewBtn.hidden, 'A hanging PNG body must expose a retry action.');
  assert.equal(h.app.state.result.sections.title, '预览超时仍保留的正文');
  assert.equal(h.elements.exportBtn.disabled, true);
  assert.equal(h.elements.previewStage.getAttribute('aria-busy'), 'false');
});

(async () => {
  let failures = 0;
  for (const scenario of scenarios) {
    const h = harness(scenario.initial);
    try { await scenario.run(h); console.log(`PASS: ${scenario.name}`); }
    catch (error) { failures += 1; console.error(`FAIL: ${scenario.name}\n  ${error.message}`); }
    finally { h.dispose(); }
  }
  if (failures) { console.error(`${failures} creator resilience scenario(s) failed.`); process.exitCode = 1; }
  else console.log('PASS: all creator storage, lifecycle, polling and response-body regressions.');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
