const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { File } = require('node:buffer');
const { randomUUID } = require('node:crypto');

class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.className = ''; this.textContent = ''; this.value = ''; this.hidden = false; this.disabled = false; this.style = {}; this.parentElement = null; }
  get classList() { const el = this; return { contains(x) { return el.className.split(/\s+/).includes(x); }, add(...x) { el.className = [...new Set([...el.className.split(/\s+/).filter(Boolean), ...x])].join(' '); }, remove(...x) { el.className = el.className.split(/\s+/).filter(c => !x.includes(c)).join(' '); }, toggle(x, forced) { const yes = forced ?? !this.contains(x); if (yes) this.add(x); else this.remove(x); return yes; } }; }
  append(...elements) { for (const el of elements) { el.parentElement = this; this.children.push(el); } }
  replaceChildren(...elements) { this.children = []; this.append(...elements); }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  removeAttribute(name) { delete this.attrs[name]; }
  getAttribute(name) { return this.attrs[name]; }
  focus() { this.focused = true; }
  select() {}
  click() { for (const f of this.events.click || []) f({ target: this, preventDefault() {} }); this.clicked = true; }
  scrollIntoView() {}
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(x => x !== this); }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    const parts = selector.match(/^(\w+)?(?:\[([\w-]+)(?:="([^"]*)")?\])?$/);
    if (!parts) throw new Error(`unsupported selector ${selector}`);
    if (parts[1] && this.tagName !== parts[1].toUpperCase()) return false;
    if (parts[2]) { const key = parts[2].replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase()); const value = parts[2].startsWith('data-') ? this.dataset[key] : this.attrs[parts[2]]; if (value === undefined || (parts[3] !== undefined && value !== parts[3])) return false; }
    return true;
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector); }
  querySelectorAll(selector) {
    if (selector.includes(',')) return [...new Set(selector.split(',').flatMap(x => this.querySelectorAll(x)))];
    const segments = selector.split(' ');
    const all = []; const visit = el => { for (const child of el.children) { if (child.matches(segments.at(-1)) && (segments.length === 1 || child.parentElement?.closest(segments[0]))) all.push(child); visit(child); } }; visit(this); return all;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const ids = [...fs.readFileSync('templates/index.html', 'utf8').matchAll(/id="([^"]+)"/g)].map(x => x[1]);
const els = Object.fromEntries(ids.map(x => [x, new Element()]));
const styles = ['xiaohongshu', 'ins', 'japanese', 'film', 'muji'].map(style => { const el = new Element('button'); el.dataset.style = style; el.className = 'style-card'; return el; });
const stages = ['upload', 'vision', 'location', 'writing'].map(stage => { const el = new Element('li'); el.dataset.stage = stage; return el; });
const tones = ['literary', 'girly', 'healing', 'moments', 'magazine'].map(tone => { const el = new Element('button'); el.dataset.tone = tone; el.className = 'btn-regen'; return el; });
const doc = { body: new Element('body'), visibilityState: 'visible', events: {}, getElementById(id) { assert(els[id], id); return els[id]; }, createElement: tag => new Element(tag), querySelectorAll(selector) { if (selector === '.style-card') return styles; if (selector === '.stage-list li') return stages; if (selector === '.btn-regen') return tones; throw new Error(selector); }, addEventListener(name, f) { this.events[name] = f; }, execCommand() { return true; } };
let draft;
let failStore = false;
const db = { objectStoreNames: { contains: () => true }, transaction() { const tx = { objectStore() { return { get() { const req = { result: draft }; setTimeout(() => tx.oncomplete?.(), 0); return req; }, put(value) { const req = { result: 'active' }; if (!failStore) draft = value; setTimeout(() => failStore ? tx.onerror?.() : tx.oncomplete?.(), 0); return req; }, delete() { draft = undefined; const req = {}; setTimeout(() => tx.oncomplete?.(), 0); return req; } }; } }; return tx; } };
const indexedDB = { open() { const req = { result: db }; setTimeout(() => req.onsuccess(), 0); return req; } };
const localValues = new Map();
const localStorage = { getItem: k => localValues.get(k), setItem: (k, v) => localValues.set(k, v), removeItem: k => localValues.delete(k) };
const calls = [];
let jobResponse = { status: 'completed', stage: 'done', result: { journal: '苏州小记\n\n走过石桥。\n\n#旅行', sections: { title: '苏州小记', body: '走过石桥。', tags: ['旅行'] }, style: 'film', date: '2026-10-01', weather: '晴天', address: '苏州', datetime_str: '', image_filenames: ['a.jpg', 'b.jpg', 'c.jpg'], image_urls: ['/uploads/a.jpg', '/uploads/b.jpg', '/uploads/c.jpg'], image_metadata: [{filename:'a.jpg',datetime_str:'2026-10-01'}, {filename:'b.jpg',datetime_str:'2026-10-02'}, {filename:'c.jpg',datetime_str:'2026-10-03'}], warnings: [] } };
let jobHTTP = 200;
let exportFail = false;
let regenFail = false;
let uploadedExpired = new Set();
let deferredPreview = null;
async function fetchMock(url, options = {}) {
  calls.push({url, options});
  if (url === '/api/jobs') return {ok:true,status:202,json:async()=>({job_id:'demo',status:'queued',stage:'upload'})};
  if (url.startsWith('/api/jobs/')) return {ok:jobHTTP===200,status:jobHTTP,json:async()=> jobHTTP===200 ? {...jobResponse,job_id:'demo'} : {error:'expired'}};
  if (url.startsWith('/uploads/')) return {ok:true,status:uploadedExpired.has(url)?404:200};
  if (url === '/api/regenerate') return {ok:!regenFail,status:regenFail?500:200,json:async()=>regenFail?{error:'模拟改写失败'}:{journal:'新语气\n\n温柔的正文。',sections:{title:'新语气',body:'温柔的正文。',tags:[]}}};
  if (url === '/api/export-image') {
    if (deferredPreview) { const deferred = deferredPreview; deferredPreview = null; return deferred.promise; }
    return {ok:!exportFail,status:exportFail?500:200,json:async()=>({error:'模拟排版失败'}),blob:async()=>new Blob(['PNG'],{type:'image/png'})};
  }
  throw new Error(`unexpected fetch ${url}`);
}
let objectCounter = 0;
const urls = new Map();
const urlAPI = {createObjectURL(blob){const url=`blob:${++objectCounter}`;urls.set(url,blob);return url;},revokeObjectURL(url){urls.delete(url);}};
const context = vm.createContext({ document:doc, window:{addEventListener(){}, ZhilvjiUI:{confirm:async()=>true}}, console, setTimeout,clearTimeout, Date,Math, Object,JSON, String,Array,Set,Map,Promise, Error,Blob,File,FormData,AbortController, crypto:{randomUUID}, URL:urlAPI, indexedDB,localStorage,navigator:{clipboard:{async writeText(text){context.copied=text;}}}, fetch:fetchMock, confirm:()=>true });
let source = fs.readFileSync('static/app.js','utf8');
source=source.replace(/\}\)\(\);\s*$/, 'globalThis.testApp = { state, addPhotos, movePhoto, generate, editResult, flushEditor, undo, redo, regenerate, changeResultPhotos, previewKey, journalText, schedulePreview, renderPreview, saveDraft, restoreDraft, runPolling, retryJob, checkUploadedPhotos, clearDraft, download, copyText }; })();');
vm.runInContext(source, context);
const tick=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  await tick(10);
  const app=context.testApp;
  const photos=['a','b','c'].map(name=>new File([name],`${name}.jpg`,{type:'image/jpeg',lastModified:1}));
  app.addPhotos(photos);
  assert.equal(app.state.files.length,3); assert.equal(els.previewGrid.children.length,3);
  app.movePhoto(0,2); assert.deepEqual(Array.from(app.state.files,x=>x.file.name),['b.jpg','c.jpg','a.jpg']);
  const second=els.previewGrid.children[1]; const remove=second.querySelector('[data-action="remove"]');
  els.previewGrid.events.click[0]({target:remove}); assert.deepEqual(Array.from(app.state.files,x=>x.file.name),['b.jpg','a.jpg']);
  app.addPhotos([new File(['bad'],'photo.heic',{type:'image/heic'})]); assert.equal(app.state.files.length,2); assert.match(els.errorMsg.textContent,/HEIC/);
  app.addPhotos([new File(['c'],'c.jpg',{type:'image/jpeg'})]);
  await app.generate();
  assert.equal(app.state.result.sections.title,'苏州小记'); assert.equal(app.state.pendingJob,null); assert.equal(app.state.generating,false);
  const upload=calls.find(x=>x.url==='/api/jobs'); assert.deepEqual(upload.options.body.getAll('image').map(x=>x.name),['b.jpg','a.jpg','c.jpg']);
  await tick(750);
  let previews=calls.filter(x=>x.url==='/api/export-image'); assert.equal(previews.length,1); assert.equal(els.exportBtn.disabled,false);
  assert.equal(previews[0].options.body.get('style'),'film'); assert.deepEqual(JSON.parse(previews[0].options.body.get('sections')),{title:'苏州小记',body:'走过石桥。',tags:['旅行']});
  styles[4].click(); // Delegated style listener is exercised separately below.
  els.styleGrid.events.click[0]({target:styles[4]});
  assert.equal(app.state.style,'muji'); assert.equal(app.state.result.style,'film');
  app.editResult('title','手动标题'); app.flushEditor(); assert.equal(els.exportBtn.disabled,true);
  app.undo(); assert.equal(app.state.result.sections.title,'苏州小记'); app.redo(); assert.equal(app.state.result.sections.title,'手动标题');
  app.changeResultPhotos(0,2,'move'); assert.deepEqual(Array.from(app.state.result.image_filenames),['b.jpg','c.jpg','a.jpg']); assert.deepEqual(Array.from(app.state.result.image_metadata,x=>x.filename),['b.jpg','c.jpg','a.jpg']);
  app.changeResultPhotos(1,1,'remove'); assert.deepEqual(Array.from(app.state.result.image_filenames),['b.jpg','a.jpg']); app.undo(); assert.deepEqual(Array.from(app.state.result.image_filenames),['b.jpg','c.jpg','a.jpg']);
  await tick(750); previews=calls.filter(x=>x.url==='/api/export-image'); assert.equal(previews.at(-1).options.body.get('image_filenames'),'b.jpg,c.jpg,a.jpg');
  const previewUrl=els.finishedPreview.src; const exportCount=previews.length; app.download(); assert.equal(calls.filter(x=>x.url==='/api/export-image').length,exportCount); assert(urls.has(previewUrl));
  regenFail=true; await app.regenerate('literary','更文艺'); assert.equal(app.state.result.sections.title,'手动标题'); assert.match(els.errorMsg.textContent,/模拟改写失败/);
  regenFail=false; await app.regenerate('literary','更文艺'); assert.equal(app.state.result.sections.title,'新语气'); app.undo(); assert.equal(app.state.result.sections.title,'手动标题');
  const oldBody=app.state.result.sections.body; jobResponse={status:'failed',stage:'writing',error:'模拟生成失败',retryable:true}; await app.generate(); assert.equal(app.state.result.sections.body,oldBody); assert.equal(els.retryJobBtn.hidden,false); assert.equal(app.state.generating,false);
  jobHTTP=404; await app.retryJob(); assert.equal(app.state.pendingJob,null); assert.equal(els.continueJobBtn.hidden,true); assert.equal(els.jobStatus.hidden,true); assert.equal(app.state.result.sections.body,oldBody);
  uploadedExpired=new Set(['/uploads/a.jpg']); await app.checkUploadedPhotos(); assert(!app.state.result.image_filenames.includes('a.jpg')); assert(app.state.history.every(x=>!x.image_filenames.includes('a.jpg'))); assert.equal(els.resultWarnings.hidden,false);
  app.editResult('title',''); app.flushEditor(); await tick(750); assert.equal(JSON.parse(calls.filter(x=>x.url==='/api/export-image').at(-1).options.body.get('sections')).title,'');
  let resolveOldPreview; const oldPreviewPromise=new Promise(resolve=>{resolveOldPreview=resolve;});
  deferredPreview={promise:oldPreviewPromise}; app.editResult('title','旧请求'); app.flushEditor(); app.schedulePreview(true); await tick(20);
  app.editResult('title','新请求'); app.flushEditor(); app.schedulePreview(true); await tick(20); const newestUrl=els.finishedPreview.src;
  resolveOldPreview({ok:true,status:200,blob:async()=>new Blob(['OLD'],{type:'image/png'})}); await tick(20); assert.equal(els.finishedPreview.src,newestUrl);
  exportFail=true; app.editResult('body','失败时保留的正文'); app.flushEditor(); app.schedulePreview(true); await tick(20); assert.equal(els.finishedPreview.src,newestUrl); assert.equal(els.exportBtn.disabled,true); assert.equal(els.retryPreviewBtn.hidden,false);
  exportFail=false; app.schedulePreview(true); await tick(20); assert.equal(els.exportBtn.disabled,false);
  app.editResult('title',''); app.flushEditor();
  const savedFiles=Array.from(app.state.files,x=>x.file.name); await app.saveDraft(); assert.equal(draft.files.length,3); app.state.files=[];app.state.result=null;await app.restoreDraft(); assert.deepEqual(Array.from(app.state.files,x=>x.file.name),savedFiles); assert.equal(app.state.result.sections.title,'');
  const previousSavedFile=draft.files[0].file.name; failStore=true; app.state.files=[]; app.addPhotos([new File(['new'],'new.jpg',{type:'image/jpeg',lastModified:22})]); await app.saveDraft(); app.state.files=[]; await app.restoreDraft(); assert.equal(app.state.files.length,0); assert.match(els.errorMsg.textContent,/重新选择照片/); assert.equal(draft.files[0].file.name,previousSavedFile); failStore=false;
  app.state.pendingJob={job_id:'expired',status:'running',stage:'writing'}; await app.runPolling('expired'); assert.equal(app.state.pendingJob,null); assert.equal(els.continueJobBtn.hidden,true);
  app.editResult('body','x'.repeat(12001)); app.flushEditor(); await tick(750); assert.equal(els.exportBtn.disabled,true); assert.match(els.previewStatus.textContent,/12,000/);
  await app.copyText(); assert.equal(context.copied,app.journalText());
  els.supplementaryInfo.open = false;
  await app.clearDraft(); assert.equal(app.state.files.length,0);assert.equal(app.state.result,null);assert.equal(draft,undefined);assert.equal(localValues.size,0);assert.equal(els.supplementaryInfo.open,true);
  console.log('PASS: photo append/remove/order/validation; job upload ordering and completion; PNG sections/cache/download; separate form and result styles; text/photo undo-redo; generation/regeneration failure preservation; expired jobs/photos; empty title; draft restore; stale PNG response suppression; failed preview retention/retry; fallback photo identity mismatch; character limit; copy; clear.');
})().catch(error=>{console.error(error);process.exitCode=1;});
