/* Offline checks for the publishing dialog. No network or paid model calls. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.className = ''; this.textContent = ''; this.value = ''; this.hidden = false; this.disabled = false; this.checked = false; this.open = false; this.parentElement = null; }
  append(...children) { children.forEach((child) => { child.parentElement = this; this.children.push(child); }); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; for (const listener of this.events.close || []) listener({ target: this }); }
  matches(selector) {
    if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
    const parts = selector.match(/^(\w+)?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/);
    if (!parts) throw new Error(`Unsupported test selector: ${selector}`);
    if (parts[1] && this.tagName !== parts[1].toUpperCase()) return false;
    if (!parts[2]) return true;
    const key = parts[2].replace(/^data-/, '').replace(/-([a-z])/g, (_, char) => char.toUpperCase());
    const value = parts[2].startsWith('data-') ? this.dataset[key] : this.attrs[parts[2]];
    return value !== undefined && (parts[3] === undefined || String(value) === parts[3]);
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector); }
  querySelector(selector) { for (const child of this.children) { if (child.matches(selector)) return child; const found = child.querySelector(selector); if (found) return found; } return null; }
}

const html = fs.readFileSync('templates/index.html', 'utf8');
const els = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map((match) => [match[1], new Element()]));
const layout = new Element(); layout.className = 'publish-layout'; els.publishDialog.append(layout);
const document = { getElementById(id) { assert(els[id], `Missing element ${id}`); return els[id]; }, createElement(tag) { return new Element(tag); } };
const localValues = new Map();
const localStorage = { getItem: (key) => localValues.get(key), setItem: (key, value) => localValues.set(key, value) };
let keyCount = 0;
let sourceSnapshot = { signature: 'snapshot-one', previewBlob: new Blob(['PNG'], { type: 'image/png' }), journalText: '原手帐标题\n\n原手帐正文。\n\n#杭州', result: { sections: { title: '原手帐标题', body: '原手帐正文。', tags: ['杭州'] }, style: 'japanese', date: '2026-10-01', weather: '晴天', address: '杭州西湖', datetime_str: '', image_filenames: ['a.jpg', 'b.jpg'] } };
let editorFocused = false;
const editor = { takePublicationSnapshot() { return sourceSnapshot ? { ...sourceSnapshot, result: JSON.parse(JSON.stringify(sourceSnapshot.result)) } : null; }, focusEditor() { editorFocused = true; } };
const calls = [];
let responseMode = 'error';
let deferredResolve;
async function fetchMock(url, options) {
  calls.push({ url, options });
  assert.equal(url, '/api/hall/posts');
  if (responseMode === 'deferred') return new Promise((resolve) => { deferredResolve = resolve; });
  if (responseMode === 'network') throw new TypeError('Failed to fetch');
  if (responseMode === 'timeout') { const error = new Error('timeout'); error.name = 'AbortError'; throw error; }
  if (responseMode === 'error') return { ok: false, status: 500, json: async () => ({ error: '模拟发布失败，请重试。' }) };
  return { ok: true, status: 201, json: async () => ({ post: { id: 'post-1', detail_url: '/hall?post=post-1', title: options.body.get('title') } }) };
}
let urlCounter = 0;
const context = vm.createContext({ document, window: { ZhilvjiEditor: editor }, localStorage, console, setTimeout, clearTimeout, String,Array,Object, Set, JSON, Error, Blob, FormData, AbortController, crypto: { randomUUID() { keyCount += 1; return randomUUID(); } }, URL: { createObjectURL() { return `blob:publish-${++urlCounter}`; }, revokeObjectURL() {} }, fetch: fetchMock });
let source = fs.readFileSync('static/publish.js', 'utf8');
source = source.replace(/\}\)\(\);\s*$/, 'globalThis.testPublish = { state, openPublish, closePublish, addTopics, submitPublication }; })();');
vm.runInContext(source, context);
const app = context.testPublish;
const keyOf = (index) => calls[index].options.body.get('idempotency_key');

(async () => {
  app.openPublish();
  assert.equal(calls.length, 0, 'Opening must not call any API');
  assert.equal(els.publishDialog.open, true);
  assert.equal(els.publishTitle.value, '原手帐标题');
  assert.equal(els.publishConfirm.checked, false, 'Public confirmation starts unchecked');
  assert.match(els.publishPreview.src, /^blob:publish-/);
  els.publishAuthor.value = '西湖旅人';
  await app.submitPublication();
  assert.equal(calls.length, 0, 'No publish without explicit confirmation');
  assert.match(els.publishError.textContent, /勾选/);

  els.publishTopicInput.value = '#北京';
  els.publishTopicInput.events.compositionstart[0]();
  els.publishTopicInput.events.input[0]({ isComposing: true });
  let compositionEnterPrevented = false;
  els.publishTopicInput.events.keydown[0]({ key: 'Enter', isComposing: true, keyCode: 229, preventDefault() { compositionEnterPrevented = true; } });
  assert.equal(app.state.topics.length, 0, 'IME composition does not create partial topics');
  assert.equal(compositionEnterPrevented, false, 'Enter remains available for IME selection');
  els.publishTopicInput.events.compositionend[0]();
  assert.deepEqual(Array.from(app.state.topics), ['北京']);
  els.publishTopics.events.click[0]({ target: els.publishTopics.children[0].children[1] });
  assert.equal(app.addTopics('#杭州, ＡＢＣ abc #旅行'), true);
  assert.deepEqual(Array.from(app.state.topics), ['杭州', 'ABC', '旅行'], 'NFKC and case insensitive deduplication');
  assert.equal(app.addTopics('风'.repeat(21)), false);
  assert.equal(app.state.topics.length, 3, 'Invalid additions are atomic');
  assert.equal(app.addTopics('周末 自然'), true);
  assert.equal(app.addTopics('美食'), false);
  assert.equal(app.state.topics.length, 5, 'Five topic limit');
  const remove = els.publishTopics.children[1].children[1];
  els.publishTopics.events.click[0]({ target: remove });
  assert.deepEqual(Array.from(app.state.topics), ['杭州', '旅行', '周末', '自然']);
  els.publishTopicInput.value = '新话题';
  let enterPrevented = false;
  els.publishTopicInput.events.keydown[0]({ key: 'Enter', preventDefault() { enterPrevented = true; } });
  assert.equal(enterPrevented, true);
  assert.equal(app.state.topics.at(-1), '新话题');

  els.publishConfirm.checked = true;
  els.publishTitle.value = '分享标题';
  els.publishCaption.value = '把这段旅程分享给大家。';
  // The editor changing after opening cannot alter the captured publication.
  sourceSnapshot.result.sections.body = '弹窗外后来修改的正文';
  await app.submitPublication();
  assert.equal(calls.length, 1);
  const form = calls[0].options.body;
  assert.equal(form.get('public_confirm'), 'true');
  assert.equal(form.get('title'), '分享标题');
  assert.equal(form.get('author_name'), '西湖旅人');
  assert.equal(form.get('image_filenames'), 'a.jpg,b.jpg');
  assert.equal(form.get('address'), '杭州西湖');
  assert.equal(JSON.parse(form.get('sections')).body, '原手帐正文。', 'Publication snapshot is locked');
  assert.equal(JSON.parse(form.get('topics')).length, 5);
  assert.equal(els.publishError.hidden, false);
  assert.equal(els.publishCaption.value, '把这段旅程分享给大家。', 'Errors retain fields');
  assert.equal(app.state.busy, false);
  assert.equal(localValues.get('zhilvji-publish-author'), '西湖旅人');
  await app.submitPublication();
  assert.equal(keyOf(0), keyOf(1), 'Error retries reuse the idempotency key');
  els.publishCaption.value = '修改分享说明';
  await app.submitPublication();
  assert.notEqual(keyOf(2), keyOf(1), 'Payload changes receive a new key');
  responseMode = 'timeout';
  await app.submitPublication();
  assert.match(els.publishError.textContent, /等待较久/);
  assert.equal(keyOf(3), keyOf(2));
  responseMode = 'network';
  await app.submitPublication();
  assert.match(els.publishError.textContent, /网络连接/);
  assert.doesNotMatch(els.publishError.textContent, /Failed to fetch/);

  responseMode = 'deferred';
  const first = app.submitPublication();
  const countBeforeDoubleClick = calls.length;
  await app.submitPublication();
  assert.equal(calls.length, countBeforeDoubleClick, 'Double clicks issue one request');
  assert.equal(els.publishTitle.disabled, true);
  assert.equal(els.publishCloseBtn.disabled, true);
  let cancelPrevented = false;
  els.publishDialog.events.cancel[0]({ preventDefault() { cancelPrevented = true; } });
  assert.equal(cancelPrevented, true);
  app.closePublish();
  assert.equal(els.publishDialog.open, true, 'In-flight publication retains its dialog');
  deferredResolve({ ok: true, status: 200, json: async () => ({ post: { id: 'post-1', detail_url: '/hall?post=post-1' } }) });
  await first;
  assert.equal(els.publishSuccess.hidden, false);
  assert.equal(layout.hidden, true);
  assert.equal(els.publishedPostLink.href, '/hall?post=post-1');
  assert.equal(els.publishCloseBtn.disabled, false);
  const successCount = calls.length;
  await app.submitPublication();
  assert.equal(calls.length, successCount, 'Successful publication does not repeat');
  app.closePublish();
  app.openPublish();
  assert.equal(els.publishSuccess.hidden, false, 'Reopening the same published snapshot shows its link');
  assert.equal(calls.length, successCount);

  sourceSnapshot = { ...sourceSnapshot, signature: 'snapshot-two' };
  app.closePublish(); app.openPublish();
  assert.equal(els.publishSuccess.hidden, true);
  assert.equal(els.publishConfirm.checked, false);
  assert.equal(els.publishAuthor.value, '西湖旅人', 'Nickname preference is restored');
  els.publishConfirm.checked = true;
  els.publishTitle.value = '   ';
  await app.submitPublication(); assert.equal(calls.length, successCount); assert.match(els.publishError.textContent, /分享标题/);
  els.publishTitle.value = '第二页'; els.publishAuthor.value = '旅'.repeat(31);
  await app.submitPublication(); assert.equal(calls.length, successCount); assert.match(els.publishError.textContent, /发布昵称/);
  els.publishAuthor.value = '旅人'; els.publishCaption.value = '字'.repeat(2001);
  await app.submitPublication(); assert.equal(calls.length, successCount); assert.match(els.publishError.textContent, /2,000/);
  app.closePublish(true); assert.equal(editorFocused, true);
  sourceSnapshot = { ...sourceSnapshot, signature: 'old-draft-long-weather', result: { ...sourceSnapshot.result, weather: '晴'.repeat(51) } };
  app.openPublish(); els.publishConfirm.checked = true;
  await app.submitPublication();
  assert.equal(calls.length, successCount, 'Legacy draft weather exceeding the API limit is rejected before publishing');
  assert.match(els.publishError.textContent, /天气超过 50 字/);
  assert.match(els.publishError.textContent, /调整成品风格与信息/);
  app.closePublish();
  sourceSnapshot = null; app.openPublish(); assert.equal(els.publishDialog.open, false, 'Unavailable snapshots cannot open');
  assert.equal(keyCount, 2);
  console.log('PASS: explicit public confirmation; opening without API; normalized topics and limits; frozen artwork snapshot; errors retain form and key; changed payload renews key; timeout/network Chinese feedback; double click protection; success link and duplicate prevention; nickname preference; field validation; editor return; IME composition; legacy weather limit.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
