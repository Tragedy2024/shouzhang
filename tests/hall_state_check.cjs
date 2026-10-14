const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.className = ''; this.textContent = ''; this.value = ''; this.hidden = false; this.disabled = false; this.open = false; this.parentElement = null; this.connected = false; }
  get isConnected() { return this.connected || !!this.parentElement?.isConnected; }
  get classList() { const el = this; return { contains(x) { return el.className.split(/\s+/).includes(x); }, add(...x) { el.className = [...new Set([...el.className.split(/\s+/).filter(Boolean), ...x])].join(' '); }, remove(...x) { el.className = el.className.split(/\s+/).filter(c => !x.includes(c)).join(' '); }, toggle(x, forced) { const yes = forced ?? !this.contains(x); if (yes) this.add(x); else this.remove(x); return yes; } }; }
  append(...elements) { for (const el of elements) { el.parentElement = this; this.children.push(el); } }
  replaceChildren(...elements) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...elements); }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  removeAttribute(name) { delete this.attrs[name]; if (name === 'src') this.src = undefined; }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; for (const handler of this.events.close || []) handler({ target: this }); }
  matches(selector) { if (selector.startsWith('.')) return this.classList.contains(selector.slice(1)); const match = selector.match(/^(\w+)?(?:\[data-([\w-]+)(?:="([^"]*)")?\])?$/); if (!match) throw new Error(`unsupported selector ${selector}`); return (!match[1] || this.tagName === match[1].toUpperCase()) && (!match[2] || this.dataset[match[2].replace(/-([a-z])/g, (_, c) => c.toUpperCase())] !== undefined && (match[3] === undefined || this.dataset[match[2].replace(/-([a-z])/g, (_, c) => c.toUpperCase())] === match[3])); }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector); }
  querySelector(selector) { for (const child of this.children) { if (child.matches(selector)) return child; const nested = child.querySelector(selector); if (nested) return nested; } return null; }
}

const tick = () => new Promise(resolve => setTimeout(resolve, 5));
function testClock() {
  let now = 0;
  let nextId = 0;
  const pending = new Map();
  return {
    setTimeout(callback, ms = 0) { const id = ++nextId; pending.set(id, { callback, at: now + ms }); return id; },
    clearTimeout(id) { pending.delete(id); },
    async advance(ms) {
      const until = now + ms;
      while (true) {
        const next = [...pending.entries()].filter(([, timer]) => timer.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = next[1].at; pending.delete(next[0]); next[1].callback();
        await tick();
      }
      now = until;
      await tick();
    }
  };
}
const response = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
const post = (id, owner = false) => ({ id, title: `标题 ${id}`, caption: '记录一次真实的旅行。', author_name: '旅行作者', topics: ['杭州', '周末'], created_at: '2026-10-10T03:00:00Z', style: 'japanese', image_url: `/api/hall/posts/${id}/image`, thumbnail_url: `/api/hall/posts/${id}/thumbnail`, image_width: 1500, image_height: 3600, is_owner: owner, detail_url: `/hall?post=${id}` });
const page = (posts, number = 1, more = false, total = posts.length) => ({ posts, page: number, page_size: 12, has_more: more, total });

function harness(initialURL = 'http://localhost/hall', environment = {}) {
  const html = fs.readFileSync('templates/hall.html', 'utf8');
  const elements = {};
  for (const match of html.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) { const el = new Element(match[1]); el.hidden = /\bhidden\b/.test(match[2]); el.connected = true; elements[match[3]] = el; }
  for (const id of ['hallThemeToggle', 'hallClearFilters']) if (!elements[id]) elements[id] = new Element('button');
  const doc = { documentElement: new Element('html'), body: new Element('body'), activeElement: null, getElementById(id) { assert(elements[id], id); return elements[id]; }, createElement: tag => new Element(tag) };
  if (environment.noDocumentElement) delete doc.documentElement;
  let current = new URL(initialURL);
  const location = { get origin() { return current.origin; }, get href() { return current.href; }, get pathname() { return current.pathname; }, get search() { return current.search; } };
  const window = { events: {}, addEventListener(name, handler) { (this.events[name] ||= []).push(handler); } };
  const stored = new Map();
  if (environment.appearance) stored.set('zhilvji-hall-appearance', environment.appearance);
  const preference = { matches: !!environment.systemDark, events: [], addEventListener(name, handler) { if (name === 'change') this.events.push(handler); } };
  if ('systemDark' in environment) window.matchMedia = () => preference;
  const entries = [current.href];
  const history = { pushState(data, _, url) { current = new URL(url, current); entries.push(current.href); }, replaceState(data, _, url) { current = new URL(url, current); entries[entries.length - 1] = current.href; } };
  const calls = [];
  const api = { list: () => response(page([post('first')], 1, true, 2)), detail: (id) => response({ post: post(id) }), withdraw: () => response({ message: '已撤回', post_id: 'first' }), topics: () => response({ topics: [{ name: '杭州', count: 2 }] }) };
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/hall/topics') return api.topics();
    if (url.startsWith('/api/hall/posts?')) return api.list(new URL(url, current), options);
    const match = url.match(/^\/api\/hall\/posts\/([^/]+)(\/withdraw)?$/);
    assert(match, url);
    return match[2] ? api.withdraw(match[1], options) : api.detail(match[1], options);
  };
  const context = vm.createContext({ document: doc, window, history, location, URL, URLSearchParams, Intl, Date, Number, String, Array, Object, Set, JSON, Math, Promise, Error, AbortController, setTimeout, clearTimeout, fetch: fetchMock, console });
  if (environment.clock) { context.setTimeout = environment.clock.setTimeout; context.clearTimeout = environment.clock.clearTimeout; }
  if (environment.storage) context.localStorage = { getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value) };
  vm.runInContext(fs.readFileSync('static/app-ui.js', 'utf8'), context);
  let source = fs.readFileSync('static/hall.js', 'utf8');
  source = source.replace(/\}\)\(\);\s*$/, 'globalThis.testHall = { state, setFilters, loadList, openDetail, closeDetail, withdraw, syncLocation, safeMediaUrl, normalizePost }; })();');
  vm.runInContext(source, context);
  return { app: context.testHall, elements, calls, api, entries, location, root: doc.documentElement || doc.body, stored, setSystemDark(value) { preference.matches = value; preference.events.forEach(handler => handler({ matches: value })); }, async pop(url) { current = new URL(url, current); for (const handler of window.events.popstate || []) handler({}); await tick(); } };
}

(async () => {
  const h = harness();
  await tick();
  assert.equal(h.app.state.posts[0].id, 'first');
  assert.equal(h.elements.hallFeed.children.length, 1);
  assert.equal(h.elements.hallEmpty.hidden, true);
  assert.equal(h.elements.hallLoadMore.hidden, false);
  assert.equal(h.elements.hallTopics.children.length, 2);
  assert.equal(h.root.dataset.hallTheme, 'light', 'No matchMedia or storage still yields a readable theme');
  assert.equal(h.root.dataset.hallThemeMode, 'system');
  const firstCard = h.elements.hallFeed.children[0];
  assert.equal(firstCard.querySelector('.hall-author-seal').textContent, '旅', 'Avatar uses the real author first character');
  assert.equal(firstCard.querySelector('.hall-author-seal').attrs['aria-hidden'], 'true');
  assert.equal(firstCard.querySelector('.hall-card-author').textContent, '旅行作者');
  assert(firstCard.querySelector('.hall-cover-frame').querySelector('.hall-cover'));
  assert.equal(h.elements.hallTopics.children[1].children[0].textContent, '2', 'Topic counts remain server supplied');
  assert.equal(h.elements.hallClearFilters.hidden, true);


  h.api.list = url => response(page([post('second')], Number(url.searchParams.get('page')), false, 2));
  await h.app.loadList(true);
  assert.deepEqual(Array.from(h.app.state.posts, p => p.id), ['first', 'second']);
  assert.match(h.calls.at(-1).url, /page=2/);
  assert.equal(h.elements.hallLoadMore.hidden, true);

  h.api.list = () => response(page([], 1, false, 0));
  h.app.setFilters({ topic: '杭州', q: '秋天', mine: true });
  await tick();
  const filtered = new URL(h.calls.filter(call => call.url.startsWith('/api/hall/posts?')).at(-1).url, h.location.origin);
  assert.equal(filtered.searchParams.get('topic'), '杭州');
  assert.equal(filtered.searchParams.get('q'), '秋天');
  assert.equal(filtered.searchParams.get('mine'), '1');
  assert.equal(h.elements.hallEmpty.hidden, false);
  assert.match(h.elements.hallEmptyTitle.textContent, /没有找到/);
  assert.equal(h.elements.hallMineNote.hidden, false);
  assert.equal(new URL(h.location.href).searchParams.get('topic'), '杭州');
  assert.equal(h.elements.hallClearFilters.hidden, false);

  let resolveOld;
  h.api.list = () => new Promise(resolve => { resolveOld = resolve; });
  h.app.setFilters({ q: '旧请求' });
  await tick();
  h.api.list = () => response(page([post('newest')]));
  h.app.setFilters({ q: '新请求' });
  await tick();
  resolveOld(response(page([post('stale')])));
  await tick();
  assert.equal(h.app.state.posts[0].id, 'newest');

  h.api.list = () => response({ error: '列表暂时失败' }, 503);
  await h.app.loadList();
  assert.equal(h.app.state.posts[0].id, 'newest');
  assert.equal(h.elements.hallListError.hidden, false);
  assert.equal(h.elements.hallEmpty.hidden, true);
  h.api.list = () => response(page([post('restored')]));
  await h.app.loadList();
  assert.equal(h.elements.hallListError.hidden, true);
  assert.equal(h.app.state.posts[0].id, 'restored');

  const trigger = h.elements.hallFeed.children[0];
  await h.app.openDetail('restored', { trigger });
  assert.equal(h.elements.hallDetail.open, true);
  assert.equal(h.elements.hallDetailTitle.textContent, '标题 restored');
  assert.equal(new URL(h.location.href).searchParams.get('post'), 'restored');
  assert.equal(h.elements.hallOwnerActions.hidden, true);
  const before = h.calls.length;
  h.elements.hallWithdrawConfirm.hidden = false;
  await h.app.withdraw();
  assert.equal(h.calls.length, before, 'A visitor must not issue a withdraw request.');
  h.app.closeDetail();
  assert.equal(h.elements.hallDetail.open, false);
  assert.equal(new URL(h.location.href).searchParams.get('post'), null);
  assert.equal(trigger.focused, true);

  h.api.detail = id => response({ post: post(id, true) });
  await h.app.openDetail('restored');
  assert.equal(h.elements.hallOwnerActions.hidden, false);
  await h.app.withdraw();
  assert.equal(h.calls.filter(call => call.url.endsWith('/withdraw')).length, 0, 'Withdrawal requires the visible confirmation step.');
  h.elements.hallWithdrawConfirm.hidden = false;
  h.api.withdraw = () => response({ error: '模拟撤回失败' }, 503);
  await h.app.withdraw();
  assert.equal(h.elements.hallDetail.open, true);
  assert.equal(h.app.state.detail.id, 'restored');
  assert.match(h.elements.hallWithdrawStatus.textContent, /未能确认撤回结果.*模拟撤回失败/);
  assert.equal(h.elements.hallWithdrawConfirmBtn.disabled, false);
  h.api.withdraw = () => response({ message: '已撤回', post_id: 'restored' });
  h.api.list = () => response(page([]));
  await h.app.withdraw();
  await tick();
  assert.equal(h.elements.hallDetail.open, false);
  assert.equal(h.app.state.posts.length, 0);

  h.api.detail = () => response({ error: '已撤回' }, 404);
  await h.app.openDetail('withdrawn');
  assert.match(h.elements.hallDetailErrorTitle.textContent, /撤回或不存在/);
  assert.equal(h.elements.hallDetailRetry.hidden, true);
  h.app.closeDetail();

  let resolveDetail;
  h.api.detail = () => new Promise(resolve => { resolveDetail = resolve; });
  const old = h.app.openDetail('older');
  await tick();
  h.api.detail = id => response({ post: post(id) });
  await h.app.openDetail('newer');
  resolveDetail(response({ post: post('older') }));
  await old;
  assert.equal(h.app.state.detail.id, 'newer');
  h.app.closeDetail();

  assert.equal(h.app.safeMediaUrl('https://foreign.example/api/hall/posts/first/image', 'first', 'image'), null);
  assert.equal(h.app.safeMediaUrl('javascript:alert(1)', 'first', 'image'), null);
  assert.equal(h.app.safeMediaUrl('/uploads/private.jpg', 'first', 'image'), null);
  assert.equal(h.app.safeMediaUrl('/api/hall/posts/first/image', 'first', 'image'), '/api/hall/posts/first/image');

  const deep = harness('http://localhost/hall?topic=%E6%9D%AD%E5%B7%9E&post=deep-link');
  await tick();
  assert.equal(deep.app.state.topic, '杭州');
  assert.equal(deep.app.state.detail.id, 'deep-link');
  assert.equal(deep.elements.hallDetail.open, true);
  await deep.pop('/hall?topic=周末');
  assert.equal(deep.elements.hallDetail.open, false);
  assert.equal(deep.app.state.topic, '周末');
  await deep.pop('/hall?topic=杭州&post=deep-link');
  assert.equal(deep.elements.hallDetail.open, true);
  deep.app.closeDetail();
  assert.equal(new URL(deep.location.href).searchParams.get('topic'), '杭州');
  assert.equal(new URL(deep.location.href).searchParams.get('post'), null);

  const legacyDOM = harness('http://localhost/hall', { noDocumentElement: true });
  await tick();
  assert.equal(legacyDOM.root.dataset.hallTheme, 'light', 'Legacy DOM without documentElement also receives a readable theme');
  const appearance = harness('http://localhost/hall', { systemDark: true, storage: true });
  await tick();
  assert.equal(appearance.root.dataset.hallTheme, 'dark');
  assert.equal(appearance.root.dataset.hallThemeMode, 'system');
  assert.equal(appearance.elements.hallThemeToggle.attrs['aria-pressed'], 'mixed');
  assert.match(appearance.elements.hallThemeToggle.attrs['aria-label'], /跟随系统.*深色/);
  const themeCalls = appearance.calls.length;
  appearance.elements.hallThemeToggle.events.click[0]();
  assert.equal(appearance.root.dataset.hallTheme, 'light');
  assert.equal(appearance.stored.get('zhilvji-hall-appearance'), 'light');
  appearance.setSystemDark(false); appearance.setSystemDark(true);
  assert.equal(appearance.root.dataset.hallTheme, 'light', 'A manual choice ignores later system changes');
  appearance.elements.hallThemeToggle.events.click[0]();
  assert.equal(appearance.root.dataset.hallTheme, 'dark');
  assert.equal(appearance.elements.hallThemeToggle.attrs['aria-pressed'], 'true');
  appearance.elements.hallThemeToggle.events.click[0]();
  assert.equal(appearance.root.dataset.hallThemeMode, 'system');
  appearance.setSystemDark(false);
  assert.equal(appearance.root.dataset.hallTheme, 'light');
  assert.equal(appearance.calls.length, themeCalls, 'Theme changes do not call APIs');
  const persisted = harness('http://localhost/hall', { systemDark: true, storage: true, appearance: 'light' });
  await tick();
  assert.equal(persisted.root.dataset.hallTheme, 'light');
  assert.equal(persisted.root.dataset.hallThemeMode, 'light');
  const unknownPreference = harness('http://localhost/hall', { systemDark: true, storage: true, appearance: 'unknown' });
  await tick();
  assert.equal(unknownPreference.root.dataset.hallTheme, 'dark');
  assert.equal(unknownPreference.root.dataset.hallThemeMode, 'system');
  appearance.app.setFilters({ topic: '杭州', q: '周末', mine: true });
  await tick();
  appearance.elements.hallClearFilters.events.click[0]();
  await tick();
  assert.equal(appearance.app.state.topic, '');
  assert.equal(appearance.app.state.q, '');
  assert.equal(appearance.app.state.mine, true, 'Clearing search keeps the current browse range');
  assert.equal(appearance.elements.hallClearFilters.hidden, true);
  const unicodeAuthor = { ...post('unicode-author'), author_name: '🌿行者', title: '<b>作者自己的文字</b>', topics: ['第一话题', '第二话题', '第三话题', '第四话题'] };
  appearance.api.list = () => response(page([unicodeAuthor]));
  await appearance.app.loadList();
  const unicodeCard = appearance.elements.hallFeed.children[0];
  assert.equal(unicodeCard.querySelector('.hall-author-seal').textContent, '🌿', 'The first Unicode character is never split into surrogates');
  assert.equal(unicodeCard.querySelector('.hall-card-author').textContent, '🌿行者');
  assert.equal(unicodeCard.querySelector('.hall-card-copy').querySelector('h2').textContent, '<b>作者自己的文字</b>', 'Author content remains plain text');
  assert.equal(unicodeCard.querySelector('.hall-card-topics').children.length, 3, 'Card topic hierarchy stays concise while detail data is preserved');
  assert.equal(appearance.app.state.posts[0].topics.length, 4);

  const clock = testClock();
  const searching = harness('http://localhost/hall', { clock });
  await tick();
  const input = searching.elements.hallSearchInput;
  const queryCalls = () => searching.calls.filter(call => call.url.startsWith('/api/hall/posts?'));
  let searchCount = queryCalls().length;
  input.value = '杭'; input.events.input[0]({ isComposing: false });
  await clock.advance(299);
  assert.equal(queryCalls().length, searchCount, 'Search waits for the complete 300 ms debounce');
  input.value = '杭州'; input.events.input[0]({ isComposing: false });
  await clock.advance(299);
  assert.equal(queryCalls().length, searchCount, 'Typing again cancels the superseded search timer');
  await clock.advance(1);
  assert.equal(queryCalls().length, ++searchCount);
  assert.equal(new URL(queryCalls().at(-1).url, searching.location.origin).searchParams.get('q'), '杭州');
  assert.equal(new URL(searching.location.href).searchParams.get('q'), '杭州');

  input.value = '旧的输入'; input.events.input[0]({ isComposing: false });
  await clock.advance(100);
  input.events.compositionstart[0]();
  input.value = '西'; input.events.input[0]({ isComposing: true });
  await clock.advance(1000);
  assert.equal(queryCalls().length, searchCount, 'Composition cancels a pending query and never sends partial text');
  let imeSubmitPrevented = false;
  searching.elements.hallSearchForm.events.submit[0]({ preventDefault() { imeSubmitPrevented = true; } });
  assert.equal(imeSubmitPrevented, true);
  assert.equal(queryCalls().length, searchCount, 'IME Enter does not commit a query');
  input.value = '西湖'; input.events.compositionend[0]();
  await clock.advance(299); assert.equal(queryCalls().length, searchCount);
  await clock.advance(1); assert.equal(queryCalls().length, ++searchCount);
  assert.equal(new URL(queryCalls().at(-1).url, searching.location.origin).searchParams.get('q'), '西湖');
  await clock.advance(600); assert.equal(queryCalls().length, searchCount, 'Composition end produces one completed query');

  input.value = '海边'; input.events.input[0]({ isComposing: false });
  await clock.advance(25); assert.equal(queryCalls().length, searchCount);
  searching.elements.hallSearchForm.events.submit[0]({ preventDefault() {} });
  await tick();
  assert.equal(queryCalls().length, ++searchCount, 'Explicit Enter commits immediately');
  assert.equal(new URL(queryCalls().at(-1).url, searching.location.origin).searchParams.get('q'), '海边');
  await clock.advance(600); assert.equal(queryCalls().length, searchCount, 'Immediate submit clears its debounce and never repeats');

  input.value = '不应发送的旧搜索'; input.events.input[0]({ isComposing: false });
  await clock.advance(50);
  assert.equal(searching.elements.hallSearchClear.hidden, false);
  searching.elements.hallSearchClear.events.click[0]();
  await tick();
  assert.equal(queryCalls().length, ++searchCount, 'Custom clear fetches the unfiltered query immediately');
  assert.equal(new URL(queryCalls().at(-1).url, searching.location.origin).searchParams.has('q'), false);
  assert.equal(new URL(searching.location.href).searchParams.has('q'), false);
  assert.equal(input.value, '');
  assert.equal(input.focused, true);
  assert.equal(searching.elements.hallSearchClear.hidden, true);
  await clock.advance(1000); assert.equal(queryCalls().length, searchCount, 'Clear cancels previously queued text');
  console.log('PASS: initial list/topics; filtering/search/mine; pagination; stale list/detail suppression; list failure retention/retry; detail deep links and history; close focus return; visitor ownership check; withdrawal confirmation/failure/success; withdrawn detail; safe image URLs; real author seals; cover framing; topic counts and filter reset; system/manual/persisted themes without API calls; 300ms search debounce; IME composition; immediate Enter without duplicate; custom clear with refetch and input focus.');
})().catch(error => { console.error(error); process.exitCode = 1; });
