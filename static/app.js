(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const STYLES = { xiaohongshu: '小红书风', ins: 'INS 风', japanese: '日杂风', film: '胶片风', muji: '极简风' };
  const FORM_FIELDS = ['date', 'weather', 'location', 'mood', 'feelings'];
  const MAX_FILE = 16 * 1024 * 1024;
  const MAX_TOTAL = 50 * 1024 * 1024;
  const DRAFT_KEY = 'zhilvji-draft-v2';
  const MAX_JOURNAL = 12000;
  const STAGES = ['upload', 'vision', 'location', 'writing'];
  const state = { style: 'xiaohongshu', files: [], result: null, history: [], future: [], pendingJob: null, generating: false, regenerating: false };
  let dbPromise;
  let draftDB;
  let storageEpoch = 0;
  let saveRevision = 0;
  const storageOperations = new Set();
  let cancelDBOpen;
  let pageActive = true;
  let pollController;
  let polling = false;
  let creatingJob = false;
  let retryingJob = false;
  let clearingDraft = false;
  let saveTimer;
  let saveSequence = Promise.resolve();
  let editorTimer;
  let editorBefore = null;
  let previewTimer;
  let previewVersion = 0;
  let previewController;
  let previewCache = null;
  let pollVersion = 0;
  let draggedPhoto = null;
  let draggedResultPhoto = null;
  let restoring = true;
  let noticeMessages = [];
  let draftPhotoWarningShown = false;

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const uid = () => (globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

  function showError(message, focus = false) {
    $('errorMsg').textContent = message;
    $('errorMsg').hidden = false;
    if (focus) {
      $('errorMsg').tabIndex = -1;
      $('errorMsg').focus({ preventScroll: true });
      $('errorMsg').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function clearError() {
    $('errorMsg').hidden = true;
    $('errorMsg').textContent = '';
  }

  function switchPanel(panel) {
    document.body.dataset.mobilePanel = panel;
    ['materials', 'work'].forEach((name) => {
      const tab = $(`${name}Tab`);
      tab.classList.toggle('active', name === panel);
      if (name === panel) tab.setAttribute('aria-current', 'true');
      else tab.removeAttribute('aria-current');
    });
    if (panel === 'work') window.ZhilvjiUI?.resizeTextarea?.($('journalBody'));
  }

  async function fetchTimed(url, options = {}, timeout = 30000) {
    const controller = new AbortController();
    const upstream = options.signal;
    const started = Date.now();
    // Headers and the JSON/PNG body share one deadline. A stalled body must
    // release the editor just like a stalled connection.
    const bounded = (work) => new Promise((resolve, reject) => {
      const expired = () => {
        const error = new Error('请求等待超时');
        error.name = 'AbortError';
        controller.abort();
        finish(reject, error);
      };
      const onAbort = () => expired();
      let settled = false;
      const finish = (settle, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        upstream?.removeEventListener('abort', onAbort);
        settle(value);
      };
      const timer = setTimeout(expired, Math.max(1, timeout - (Date.now() - started)));
      upstream?.addEventListener('abort', onAbort, { once: true });
      if (upstream?.aborted || controller.signal.aborted) { expired(); return; }
      Promise.resolve().then(work).then((value) => finish(resolve, value), (error) => finish(reject, error));
    });
    const response = await bounded(() => fetch(url, { ...options, signal: controller.signal }));
    return { ok: response.ok, status: response.status, headers: response.headers,
      json: () => bounded(() => response.json()), blob: () => bounded(() => response.blob()) };
  }

  async function readResponse(response) {
    let data;
    try { data = await response.json(); }
    catch (error) { if (error.name === 'AbortError') throw error; throw new Error('服务暂时没有返回有效结果，请稍后重试。'); }
    if (!response.ok) throw new Error(data.error || data.message || '操作没有完成，请稍后重试。');
    return data;
  }

  function selectStyle(style) {
    state.style = Object.hasOwn(STYLES, style) ? style : 'xiaohongshu';
    document.querySelectorAll('.style-card').forEach((card) => {
      const selected = card.dataset.style === state.style;
      card.classList.toggle('selected', selected);
      card.setAttribute('aria-pressed', String(selected));
    });
    $('samplePreview').src = `/api/sample/${state.style}`;
    $('samplePreview').alt = `${STYLES[state.style]}旅行手帐示例`;
    $('sampleStyleName').textContent = STYLES[state.style];
    scheduleSave();
  }

  function photoFileAllowed(file) {
    return /^image\/(jpeg|png|webp)$/i.test(file.type) || (!file.type && /\.(jpe?g|png|webp)$/i.test(file.name));
  }

  function addPhotos(incoming) {
    if (restoring || clearingDraft || state.generating) return;
    const files = Array.from(incoming);
    if (!files.length) return;
    clearError();
    if (state.files.length + files.length > 9) { showError('最多选择 9 张照片。请先移除一些照片，再添加。', true); return; }
    const invalid = files.find((file) => !photoFileAllowed(file));
    if (invalid) { showError(`“${invalid.name}”不是支持的图片，请选择 JPG、PNG 或 WebP；HEIC 照片请先转换格式。`, true); return; }
    const large = files.find((file) => file.size > MAX_FILE);
    if (large) { showError(`“${large.name}”超过 16 MB，请换一张较小的照片。`, true); return; }
    if ([...state.files.map((entry) => entry.file), ...files].reduce((sum, file) => sum + file.size, 0) > MAX_TOTAL) {
      showError('照片总大小超过 50 MB，请减少照片或使用较小的图片。', true); return;
    }
    files.forEach((file) => state.files.push({ id: uid(), file, url: URL.createObjectURL(file) }));
    renderPhotos();
    saveDraft();
  }

  function renderPhotos(focusId, focusAction) {
    const grid = $('previewGrid');
    grid.replaceChildren();
    state.files.forEach((entry, index) => {
      const item = document.createElement('div');
      item.className = 'preview-item';
      item.dataset.photoId = entry.id;
      item.draggable = !state.generating;
      const img = document.createElement('img');
      img.src = entry.url;
      img.alt = `第 ${index + 1} 张照片：${entry.file.name}`;
      const controls = document.createElement('div');
      controls.className = 'photo-controls';
      const count = document.createElement('span');
      count.textContent = index + 1;
      controls.append(count);
      [['up', '←', '前移'], ['down', '→', '后移'], ['remove', '×', '移除']].forEach(([action, text, label]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = text;
        btn.dataset.action = action;
        btn.className = action === 'remove' ? 'preview-remove' : 'photo-move';
        btn.setAttribute('aria-label', `${label}第 ${index + 1} 张照片：${entry.file.name}`);
        btn.disabled = state.generating || (action === 'up' && index === 0) || (action === 'down' && index === state.files.length - 1);
        controls.append(btn);
      });
      item.append(img, controls);
      grid.append(item);
    });
    $('photoSection').hidden = !state.files.length;
    $('photoCount').textContent = `(${state.files.length}/9)`;
    $('uploadText').textContent = state.files.length ? `已选择 ${state.files.length} 张，继续添加照片` : '选择或拖入旅行照片';
    if (focusId && focusAction) grid.querySelector(`[data-photo-id="${focusId}"] [data-action="${focusAction}"]`)?.focus();
  }

  function movePhoto(from, to, focusAction) {
    if (state.generating || from < 0 || to < 0 || from === to || to >= state.files.length) return;
    const [entry] = state.files.splice(from, 1);
    state.files.splice(to, 0, entry);
    renderPhotos(entry.id, focusAction);
    scheduleSave();
  }

  function getForm() {
    return Object.fromEntries(FORM_FIELDS.map((field) => [field, $(field).value]));
  }

  function parseTags(tags) {
    const source = Array.isArray(tags) ? tags.join(' ') : String(tags || '');
    return [...new Set(source.split(/[\s,，]+/).map((tag) => tag.replace(/^#+/, '').trim()).filter(Boolean))];
  }

  function fallbackSections(journal) {
    const lines = String(journal || '').trim().split('\n');
    const title = (lines.shift() || '').replace(/^#{1,6}\s*/, '').replace(/^\*\*|\*\*$/g, '');
    const tags = [];
    while (lines.length && (!lines[lines.length - 1].trim() || /^#\S+(?:[\s,，]+#\S+)*\s*$/.test(lines[lines.length - 1].trim()))) {
      const last = lines.pop().trim();
      if (last) tags.unshift(...parseTags(last));
    }
    return { title, body: lines.join('\n').trim(), tags };
  }

  function normalizeResult(data) {
    const sections = data.sections || fallbackSections(data.journal);
    return {
      ...data,
      sections: { title: String(sections.title || ''), body: String(sections.body || ''), tags: parseTags(sections.tags) },
      style: Object.hasOwn(STYLES, data.style) ? data.style : 'xiaohongshu',
      date: String(data.date || (/^\d{4}-\d{2}-\d{2}/.test(data.datetime_str || '') ? data.datetime_str.slice(0, 10) : '')), weather: String(data.weather || ''), address: String(data.address || data.location || ''),
      datetime_str: String(data.datetime_str || ''), image_filenames: Array.isArray(data.image_filenames) ? data.image_filenames : [],
      image_urls: Array.isArray(data.image_urls) ? data.image_urls : [], image_metadata: Array.isArray(data.image_metadata) ? data.image_metadata : [],
      warnings: Array.isArray(data.warnings) ? data.warnings : []
    };
  }

  function journalText(result = state.result) {
    if (!result) return '';
    return [result.sections.title.trim(), result.sections.body.trim(), result.sections.tags.map((tag) => `#${tag}`).join(' ')].filter(Boolean).join('\n\n');
  }

  function previewKey(result = state.result) {
    if (!result) return '';
    return JSON.stringify([result.sections, journalText(result), result.style, result.date, result.weather, result.address, result.datetime_str, result.image_filenames]);
  }

  function pushHistory(previous) {
    if (!previous || JSON.stringify(previous) === JSON.stringify(state.result)) return;
    state.history.push(previous);
    if (state.history.length > 50) state.history.shift();
    state.future = [];
    updateControls();
  }

  function flushEditor() {
    clearTimeout(editorTimer);
    if (editorBefore) {
      pushHistory(editorBefore);
      editorBefore = null;
      scheduleSave();
    }
  }

  function editResult(field, value) {
    if (!state.result || state.regenerating) return;
    if (!editorBefore) editorBefore = clone(state.result);
    if (field === 'title' || field === 'body') state.result.sections[field] = value;
    else if (field === 'tags') state.result.sections.tags = parseTags(value);
    else {
      state.result[field] = value;
      if (field === 'date') state.result.datetime_str = value;
    }
    state.result.journal = journalText();
    state.result.style_name = STYLES[state.result.style];
    clearTimeout(editorTimer);
    editorTimer = setTimeout(flushEditor, 650);
    updateControls();
    schedulePreview();
    scheduleSave();
  }

  function applyResult(data, { record = true, focus = false } = {}) {
    flushEditor();
    const previous = state.result ? clone(state.result) : null;
    state.result = normalizeResult(data);
    if (record) pushHistory(previous);
    renderResult();
    schedulePreview();
    scheduleSave();
    if (focus) {
      switchPanel('work');
      $('workHeading').tabIndex = -1;
      $('workHeading').focus({ preventScroll: true });
      $('workPanel').scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }

  function renderWarnings() {
    const warnings = [...new Set([...(state.result?.warnings || []).map(String), ...noticeMessages])];
    $('resultWarnings').replaceChildren();
    warnings.forEach((text) => {
      const p = document.createElement('p');
      p.textContent = text;
      $('resultWarnings').append(p);
    });
    $('resultWarnings').hidden = !warnings.length;
  }

  function renderResult() {
    $('resultContent').hidden = !state.result;
    $('emptyState').hidden = !!state.result;
    renderResultPhotos();
    if (!state.result) { updateControls(); return; }
    const result = state.result;
    $('journalTitle').value = result.sections.title;
    $('journalBody').value = result.sections.body;
    window.ZhilvjiUI?.resizeTextarea?.($('journalBody'));
    $('journalTags').value = result.sections.tags.map((tag) => `#${tag}`).join(' ');
    $('resultStyle').value = result.style;
    $('resultDate').value = /^\d{4}-\d{2}-\d{2}$/.test(result.date) ? result.date : '';
    $('resultWeather').value = result.weather;
    $('resultAddress').value = result.address;
    $('imageMeta').replaceChildren();
    result.image_metadata.forEach((meta, index) => {
      const li = document.createElement('li');
      li.textContent = `照片 ${index + 1}：${[meta.datetime_str, meta.address].filter(Boolean).join(' · ') || '没有可用的拍摄时间或地点，可在上方补充。'}`;
      $('imageMeta').append(li);
    });
    $('metadataDetails').hidden = !result.image_metadata.length;
    renderWarnings();
    updateControls();
  }

  function renderResultPhotos(focusName, focusAction) {
    const grid = $('resultPhotoGrid');
    grid.replaceChildren();
    const result = state.result;
    $('resultPhotoSection').hidden = !result?.image_filenames.length;
    if (!result) return;
    result.image_filenames.forEach((filename, index) => {
      const item = document.createElement('div');
      item.className = 'preview-item';
      item.dataset.resultPhoto = filename;
      item.draggable = !state.regenerating;
      const img = document.createElement('img');
      img.src = result.image_urls[index] || `/uploads/${encodeURIComponent(filename)}`;
      img.alt = `成品第 ${index + 1} 张照片`;
      const controls = document.createElement('div');
      controls.className = 'photo-controls';
      const count = document.createElement('span');
      count.textContent = index + 1;
      controls.append(count);
      [['up', '←', '前移'], ['down', '→', '后移'], ['remove', '×', '移除']].forEach(([action, text, label]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = text;
        button.dataset.action = action;
        button.className = action === 'remove' ? 'preview-remove' : 'photo-move';
        button.setAttribute('aria-label', `${label}成品第 ${index + 1} 张照片`);
        button.disabled = state.regenerating || (action === 'up' && index === 0) || (action === 'down' && index === result.image_filenames.length - 1);
        controls.append(button);
      });
      item.append(img, controls);
      grid.append(item);
      if (focusName === filename) controls.querySelector(`[data-action="${focusAction}"]`)?.focus();
    });
  }

  function changeResultPhotos(from, to, action) {
    if (!state.result || state.regenerating || from < 0 || from >= state.result.image_filenames.length) return;
    if (action !== 'remove' && (to < 0 || to >= state.result.image_filenames.length || to === from)) return;
    flushEditor();
    const previous = clone(state.result);
    const entries = state.result.image_filenames.map((filename, index) => ({ filename, url: state.result.image_urls[index] }));
    const [entry] = entries.splice(from, 1);
    if (action !== 'remove') entries.splice(to, 0, entry);
    const metadata = new Map(state.result.image_metadata.map((meta) => [meta.filename, meta]));
    state.result.image_filenames = entries.map((photo) => photo.filename);
    state.result.image_urls = entries.map((photo) => photo.url || `/uploads/${encodeURIComponent(photo.filename)}`);
    state.result.image_metadata = entries.map((photo) => metadata.get(photo.filename)).filter(Boolean);
    pushHistory(previous);
    renderResult();
    const focusName = action === 'remove' ? entries[Math.min(from, entries.length - 1)]?.filename : entry.filename;
    renderResultPhotos(focusName, action);
    schedulePreview();
    scheduleSave();
  }

  function handleExpiredJob(response) {
    if (![403, 404, 410].includes(response.status)) return false;
    state.pendingJob = null;
    $('jobStatus').hidden = true;
    $('continueJobBtn').hidden = true;
    $('retryJobBtn').hidden = true;
    showError('之前的生成任务已过期，可重新生成。现有素材和作品已保留。');
    scheduleSave();
    return true;
  }

  function updateControls() {
    $('submitBtn').setAttribute('aria-busy', String(state.generating));
    $('submitBtn').disabled = restoring || clearingDraft || state.generating || state.regenerating;
    $('submitLabel').textContent = state.generating ? '正在生成手帐…' : (['queued', 'running'].includes(state.pendingJob?.status) ? '继续查看生成状态' : state.result ? '用素材重新生成' : '生成旅行手帐');
    $('uploadArea').disabled = restoring || clearingDraft || state.generating;
    $('imageInput').disabled = restoring || clearingDraft || state.generating;
    $('clearDraftBtn').disabled = restoring || clearingDraft || state.generating || state.regenerating;
    $('undoBtn').disabled = state.regenerating || (!state.history.length && !editorBefore);
    $('redoBtn').disabled = state.regenerating || !state.future.length || !!editorBefore;
    const length = journalText().length;
    $('journalLength').textContent = `标题、正文与标签共 ${length.toLocaleString()} 字，最多 12,000 字。`;
    $('journalLength').classList.toggle('invalid', length > MAX_JOURNAL);
    $('exportBtn').disabled = !state.result || length > MAX_JOURNAL || !previewCache || previewCache.key !== previewKey();
    $('copyBtn').disabled = !state.result || !journalText();
    $('publishBtn').disabled = !isPublicationReady();
    $('continueJobBtn').disabled = state.generating;
    $('resultPhotoGrid').querySelectorAll('[data-result-photo]').forEach((item, index) => {
      item.draggable = !state.regenerating;
      item.querySelectorAll('button[data-action]').forEach((button) => {
        button.disabled = state.regenerating || (button.dataset.action === 'up' && index === 0) || (button.dataset.action === 'down' && index === state.result.image_filenames.length - 1);
      });
    });
    document.querySelectorAll('.btn-regen').forEach((button) => { button.disabled = state.generating || state.regenerating || !state.result || !journalText() || length > MAX_JOURNAL; });
    ['journalTitle', 'journalBody', 'journalTags', 'resultStyle', 'resultDate', 'resultWeather', 'resultAddress'].forEach((id) => { $(id).disabled = state.regenerating; });
  }

  function undo() {
    if (state.regenerating) return;
    flushEditor();
    if (!state.history.length) return;
    state.future.push(clone(state.result));
    state.result = state.history.pop();
    renderResult();
    schedulePreview();
    scheduleSave();
  }

  function redo() {
    if (state.regenerating) return;
    flushEditor();
    if (!state.future.length) return;
    state.history.push(clone(state.result));
    state.result = state.future.pop();
    renderResult();
    schedulePreview();
    scheduleSave();
  }

  function schedulePreview(immediate = false) {
    clearTimeout(previewTimer);
    previewVersion += 1;
    previewController?.abort();
    if (!state.result || !pageActive) return;
    const key = previewKey();
    if (previewCache?.key === key) {
      $('finishedPreview').src = previewCache.url;
      $('finishedPreview').hidden = false;
      $('previewPlaceholder').hidden = true;
      $('previewStage').setAttribute('aria-busy', 'false');
      $('previewStatus').textContent = '成品已更新，下载的长图与预览一致。';
      $('retryPreviewBtn').hidden = true;
      updateControls();
      return;
    }
    $('previewStage').setAttribute('aria-busy', 'true');
    $('previewStatus').textContent = '正在更新成品…';
    $('retryPreviewBtn').hidden = true;
    updateControls();
    const version = previewVersion;
    previewTimer = setTimeout(() => renderPreview(version), immediate ? 0 : 700);
  }

  async function renderPreview(version) {
    if (!state.result || version !== previewVersion) return;
    const snapshot = clone(state.result);
    const key = previewKey(snapshot);
    if (journalText(snapshot).length > MAX_JOURNAL) {
      $('previewStatus').textContent = '文案超过 12,000 字，请缩短正文或标签后再生成成品。';
      $('previewStage').setAttribute('aria-busy', 'false');
      updateControls();
      return;
    }
    if (!journalText(snapshot)) {
      $('previewStatus').textContent = '写下标题或正文后，就可以生成成品。';
      $('previewStage').setAttribute('aria-busy', 'false');
      return;
    }
    previewController = new AbortController();
    const form = new FormData();
    form.append('journal_text', journalText(snapshot));
    form.append('sections', JSON.stringify(snapshot.sections));
    ['style', 'date', 'weather', 'address', 'datetime_str'].forEach((field) => form.append(field, snapshot[field] || ''));
    form.append('image_filenames', snapshot.image_filenames.join(','));
    form.append('scale', '2');
    try {
      const response = await fetchTimed('/api/export-image', { method: 'POST', body: form, signal: previewController.signal }, 90000);
      if (!response.ok) {
        let message = '成品预览没有生成成功，文字和照片已保留。';
        try { message = (await response.json()).error || message; } catch { /* Retain readable fallback. */ }
        throw new Error(message);
      }
      const blob = await response.blob();
      if (!blob.size || (blob.type && !blob.type.startsWith('image/'))) throw new Error('预览图片暂时不可用，请重试。');
      if (version !== previewVersion || previewKey() !== key) return;
      const oldCache = previewCache;
      previewCache = { key, blob, url: URL.createObjectURL(blob) };
      $('finishedPreview').src = previewCache.url;
      $('finishedPreview').hidden = false;
      $('previewPlaceholder').hidden = true;
      $('previewStage').setAttribute('aria-busy', 'false');
      $('previewStatus').textContent = '成品已更新，下载的长图与预览一致。';
      $('retryPreviewBtn').hidden = true;
      if (oldCache) URL.revokeObjectURL(oldCache.url);
      updateControls();
      scheduleSave();
    } catch (error) {
      if (version !== previewVersion) return;
      $('previewStage').setAttribute('aria-busy', 'false');
      $('previewStatus').textContent = error.name === 'AbortError' ? '排版等待较久，文字已保留。可以重新生成预览。' : error.message;
      $('retryPreviewBtn').hidden = false;
      if (!previewCache) $('previewPlaceholder').textContent = '文字已保留，可以继续编辑并重试预览。';
      updateControls();
    }
  }

  function renderJob(job) {
    $('jobStatus').hidden = false;
    $('jobMessage').textContent = job.message || ({ queued: '照片已收到，正在等待处理…', running: '正在整理旅程…', completed: '手帐已经完成。', failed: '这一步没有完成，已有内容已保留。' }[job.status] || '正在查看进度…');
    const index = job.stage === 'done' ? STAGES.length : STAGES.indexOf(job.stage);
    document.querySelectorAll('.stage-list li').forEach((item, i) => {
      item.classList.toggle('complete', job.status === 'completed' || i < index);
      item.classList.toggle('current', job.status !== 'completed' && i === Math.max(0, index));
    });
    $('retryJobBtn').hidden = job.status !== 'failed' || job.retryable === false;
    $('continueJobBtn').hidden = true;
    $('retryJobBtn').disabled = state.generating;
  }

  async function pollJob(jobId, version, focusOnComplete) {
    const start = Date.now();
    let count = 0;
    while (version === pollVersion && Date.now() - start < 5 * 60 * 1000) {
      const response = await fetchTimed(`/api/jobs/${encodeURIComponent(jobId)}`, { signal: pollController?.signal }, 25000);
      if (version !== pollVersion) return;
      if (handleExpiredJob(response)) return;
      const job = await readResponse(response);
      if (version !== pollVersion) return;
      state.pendingJob = { ...job, result: undefined };
      renderJob(job);
      scheduleSave();
      if (job.status === 'completed') {
        if (!job.result?.journal && !job.result?.sections) throw new Error('手帐内容暂时不可用，请重试。');
        noticeMessages = [];
        applyResult(job.result, { focus: focusOnComplete });
        state.pendingJob = null;
        $('jobStatus').hidden = true;
        scheduleSave();
        return;
      }
      if (job.status === 'failed') {
        showError(job.error || job.message || '生成没有完成。可以重试失败步骤，现有作品已保留。');
        return;
      }
      await delay(count++ > 10 ? 2000 : 1250);
    }
    if (version === pollVersion) {
      $('jobMessage').textContent = '这次生成比平时久。任务仍在处理中，稍后可继续查看；现有作品已保留。';
      $('continueJobBtn').hidden = false;
    }
  }

  async function runPolling(jobId, { focusOnComplete = false } = {}) {
    if (!pageActive || (polling && state.pendingJob?.job_id === jobId)) return;
    const version = ++pollVersion;
    pollController?.abort();
    pollController = new AbortController();
    polling = true;
    state.generating = true;
    updateControls();
    renderPhotos();
    try { await pollJob(jobId, version, focusOnComplete); }
    catch (error) {
      if (version !== pollVersion) return;
      showError(error.name === 'AbortError' ? '查看进度超时，任务可能仍在处理中。可继续查看状态。' : error.message);
      $('continueJobBtn').hidden = !state.pendingJob;
    } finally {
      if (version === pollVersion) {
        polling = false;
        state.generating = false;
        updateControls();
        renderPhotos();
        $('retryJobBtn').disabled = false;
      }
    }
  }

  async function generate() {
    if (restoring || clearingDraft || state.generating || state.regenerating) return;
    flushEditor();
    clearError();
    if (!state.files.length) { showError('先选择至少一张旅行照片，再生成手帐。', true); return; }
    if (state.pendingJob && ['queued', 'running'].includes(state.pendingJob.status)) {
      switchPanel('work');
      await runPolling(state.pendingJob.job_id, { focusOnComplete: true });
      return;
    }
    state.pendingJob = null;
    const form = new FormData();
    state.files.forEach((entry) => form.append('image', entry.file, entry.file.name));
    const formValues = getForm();
    FORM_FIELDS.forEach((field) => form.append(field, formValues[field].trim()));
    form.append('style', state.style);
    state.generating = true;
    creatingJob = true;
    updateControls();
    renderPhotos();
    switchPanel('work');
    renderJob({ status: 'running', stage: 'upload', message: '正在上传照片…' });
    $('workPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const response = await fetchTimed('/api/jobs', { method: 'POST', body: form }, 90000);
      const job = await readResponse(response);
      if (!job.job_id) throw new Error('任务没有建立成功，请重试。');
      state.pendingJob = job;
      creatingJob = false;
      // Remember the job synchronously, but never gate polling on photo storage.
      saveDraft();
      await runPolling(job.job_id, { focusOnComplete: true });
    } catch (error) {
      showError(error.name === 'AbortError' ? '上传等待较久，请检查网络后重试。现有作品已保留。' : error.message);
      if (!state.pendingJob) $('jobStatus').hidden = true;
    } finally {
      creatingJob = false;
      if (!polling) state.generating = false;
      updateControls();
      renderPhotos();
    }
  }

  async function retryJob() {
    if (!state.pendingJob || state.generating) return;
    clearError();
    state.generating = true;
    retryingJob = true;
    updateControls();
    $('retryJobBtn').disabled = true;
    try {
      const response = await fetchTimed(`/api/jobs/${encodeURIComponent(state.pendingJob.job_id)}/retry`, { method: 'POST' });
      if (handleExpiredJob(response)) return;
      const job = await readResponse(response);
      state.pendingJob = job;
      retryingJob = false;
      renderJob(job);
      scheduleSave();
      await runPolling(job.job_id, { focusOnComplete: true });
    } catch (error) {
      showError(error.name === 'AbortError' ? '重试请求超时。可以稍后继续查看状态。' : error.message);
      $('continueJobBtn').hidden = !state.pendingJob;
    } finally {
      retryingJob = false;
      if (!polling) state.generating = false;
      updateControls();
      $('retryJobBtn').disabled = false;
    }
  }

  async function regenerate(tone, label) {
    if (!state.result || state.regenerating || state.generating) return;
    flushEditor();
    clearError();
    const original = clone(state.result);
    state.regenerating = true;
    updateControls();
    $('regenStatus').textContent = `正在改写为“${label}”…`;
    try {
      const response = await fetchTimed('/api/regenerate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_text: journalText(original), tone, style: original.style }) }, 120000);
      const data = await readResponse(response);
      if (!data.journal?.trim() && !data.sections) throw new Error('这次改写没有返回正文，请重试。');
      applyResult({ ...original, journal: data.journal, sections: data.sections || fallbackSections(data.journal) });
      $('regenStatus').textContent = '语气已更新，可以撤销回上一版。';
    } catch (error) {
      showError(error.name === 'AbortError' ? '改写等待较久，上一版内容已保留。可以稍后重试。' : error.message);
      $('regenStatus').textContent = '上一版内容已保留。';
    } finally {
      state.regenerating = false;
      updateControls();
    }
  }

  function download() {
    flushEditor();
    if (!state.result || !previewCache || previewCache.key !== previewKey()) return;
    const a = document.createElement('a');
    a.href = previewCache.url;
    const safeTitle = state.result.sections.title.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '').slice(0, 60).trim() || '旅行手帐';
    a.download = `${safeTitle}.png`;
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function copyText() {
    flushEditor();
    const text = journalText();
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const input = document.createElement('textarea');
        input.value = text;
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.append(input);
        input.select();
        const success = document.execCommand('copy');
        input.remove();
        if (!success) throw new Error('copy');
      }
      $('copyBtn').textContent = '已复制';
      setTimeout(() => { $('copyBtn').textContent = '复制文案'; }, 1800);
    } catch {
      showError('浏览器没有允许复制。可以在下方正文编辑区选择文字并复制。');
      $('journalBody').focus();
    }
  }

  function openDraftDB() {
    if (dbPromise) return dbPromise;
    const epoch = storageEpoch;
    const promise = new Promise((resolve, reject) => {
      if (!globalThis.indexedDB) { reject(new Error('unavailable')); return; }
      let settled = false;
      const finish = (error, db) => {
        if (settled) { db?.close?.(); return; }
        settled = true;
        clearTimeout(timer);
        cancelDBOpen = null;
        if (error) { db?.close?.(); reject(error); }
        else { draftDB = db; db.onversionchange = () => closeDraftStorage(); resolve(db); }
      };
      const timer = setTimeout(() => finish(new Error('草稿存储连接超时。')), 1800);
      cancelDBOpen = () => finish(new Error('草稿存储连接已暂停。'));
      const request = indexedDB.open('zhilvji-drafts', 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('drafts')) request.result.createObjectStore('drafts'); };
      request.onsuccess = () => finish(epoch === storageEpoch ? null : new Error('草稿连接已过期。'), request.result);
      request.onerror = () => finish(request.error || new Error('草稿存储不可用。'));
      request.onblocked = () => finish(new Error('草稿存储正在被另一个页面使用。'));
    });
    dbPromise = promise;
    promise.catch(() => { if (dbPromise === promise) dbPromise = null; });
    return dbPromise;
  }

  function closeDraftStorage(flushDraft) {
    storageEpoch += 1;
    saveRevision += 1;
    cancelDBOpen?.();
    [...storageOperations].forEach((cancel) => cancel());
    const leavingDB = draftDB;
    draftDB = null;
    dbPromise = null;
    // Commit the newest photo snapshot on departure when the connection is
    // already ready. Never wait for it to navigate or retain a stale read.
    if (flushDraft && leavingDB) {
      writeDraftTransaction(leavingDB, 'put', flushDraft, storageEpoch).catch(() => {}).finally(() => leavingDB.close?.());
    } else leavingDB?.close?.();
  }

  async function storeDraft(operation, value) {
    const epoch = storageEpoch;
    const db = draftDB || await openDraftDB();
    if (epoch !== storageEpoch) throw new Error('草稿存储已暂停。');
    return writeDraftTransaction(db, operation, value, epoch);
  }

  function writeDraftTransaction(db, operation, value, epoch) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction('drafts', operation === 'get' ? 'readonly' : 'readwrite');
      const store = transaction.objectStore('drafts');
      const request = operation === 'get' ? store.get('active') : operation === 'delete' ? store.delete('active') : store.put(value, 'active');
      let settled = false;
      const finish = (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        storageOperations.delete(cancel);
        if (error) reject(error); else resolve(request.result);
      };
      const cancel = () => {
        try { transaction.abort?.(); } catch { /* Already completed. */ }
        finish(new Error('草稿存储等待超时。'));
      };
      const timer = setTimeout(cancel, operation === 'get' ? 1800 : 5000);
      storageOperations.add(cancel);
      transaction.oncomplete = () => finish(epoch === storageEpoch ? null : new Error('草稿存储已暂停。'));
      transaction.onerror = () => finish(transaction.error || new Error('草稿存储不可用。'));
      transaction.onabort = () => finish(transaction.error || new Error('草稿没有保存成功。'));
    });
  }

  function draftData(includeFiles = true) {
    return {
      schema: 2, savedAt: Date.now(), mobilePanel: document.body.dataset.mobilePanel || 'materials', style: state.style, form: getForm(), result: state.result ? clone(state.result) : null,
      history: [...state.history, ...(editorBefore ? [editorBefore] : [])].slice(-50).map(clone), future: editorBefore ? [] : state.future.map(clone),
      pendingJob: state.pendingJob ? clone(state.pendingJob) : null, notices: [...noticeMessages], fileCount: state.files.length,
      fileManifest: state.files.map(({ id, file }) => ({ id, name: file.name, size: file.size, lastModified: file.lastModified })),
      files: includeFiles ? state.files.map(({ id, file }) => ({ id, file })) : [],
      preview: includeFiles && previewCache?.key === previewKey() ? { key: previewCache.key, blob: previewCache.blob } : null
    };
  }

  function saveTextFallback() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draftData(false))); return true; }
    catch { return false; }
  }

  function scheduleSave() {
    if (restoring || !pageActive) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 450);
  }

  async function saveDraft() {
    if (restoring) return;
    clearTimeout(saveTimer);
    const draft = draftData();
    const textSaved = saveTextFallback();
    if (!pageActive) return;
    const revision = ++saveRevision;
    const epoch = storageEpoch;
    $('draftStatus').textContent = '正在保存草稿…';
    saveSequence = saveSequence.catch(() => {}).then(async () => {
      if (epoch !== storageEpoch || revision !== saveRevision) return;
      try {
        await storeDraft('put', draft);
        if (pageActive && revision === saveRevision) $('draftStatus').textContent = '草稿已自动保存';
      } catch {
        if (!pageActive || epoch !== storageEpoch || revision !== saveRevision) return;
        $('draftStatus').textContent = textSaved ? '文字草稿已保存' : '草稿未保存';
        if (!draftPhotoWarningShown) {
          draftPhotoWarningShown = true;
          showError(textSaved ? '当前浏览器无法保存照片草稿。文字已保存，刷新后需要重新选择照片。' : '当前浏览器无法保存草稿，请先下载作品或复制文案。');
        }
      }
    });
    return saveSequence;
  }

  async function checkUploadedPhotos() {
    if (!state.result?.image_urls.length) return;
    const originalResult = state.result;
    const results = await Promise.allSettled(originalResult.image_urls.map(async (url, index) => {
      if (typeof url !== 'string' || !url.startsWith('/uploads/')) return null;
      const filename = originalResult.image_filenames[index];
      const response = await fetchTimed(url, { method: 'HEAD' }, 15000);
      return response.status === 404 || response.status === 403 ? filename : null;
    }));
    if (state.result !== originalResult) return;
    const expired = new Set(results.filter((result) => result.status === 'fulfilled' && result.value).map((result) => result.value));
    if (!expired.size) return;
    const cleanImages = (result) => {
      if (!result) return result;
      const keep = result.image_filenames.map((name, index) => ({ name, index })).filter(({ name }) => !expired.has(name));
      result.image_filenames = keep.map(({ name }) => name);
      result.image_urls = keep.map(({ index }) => result.image_urls[index]).filter(Boolean);
      result.image_metadata = result.image_metadata.filter((meta) => !expired.has(meta.filename));
      return result;
    };
    cleanImages(state.result);
    state.history.forEach(cleanImages);
    state.future.forEach(cleanImages);
    noticeMessages.push('之前上传的照片副本已过期。文字已保留，可以导出文字版；要恢复图片，请用素材区的照片重新生成。');
    renderResult();
    schedulePreview(true);
    scheduleSave();
  }

  async function restoreDraft() {
    let draft;
    let textDraft;
    try { textDraft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch { /* Storage may be unavailable. */ }
    try { draft = await storeDraft('get'); } catch { /* Use text fallback. */ }
    if (textDraft?.savedAt > (draft?.savedAt || 0)) {
      const savedFiles = new Map((draft?.files || []).map((entry) => [entry.id, entry]));
      const orderedFiles = (textDraft.fileManifest || []).map((meta) => {
        const entry = savedFiles.get(meta.id);
        return entry && entry.file.name === meta.name && entry.file.size === meta.size && entry.file.lastModified === meta.lastModified ? entry : null;
      }).filter(Boolean);
      draft = { ...textDraft, files: orderedFiles, preview: null };
    }
    draft ||= textDraft;
    if (draft?.schema === 2) {
      FORM_FIELDS.forEach((field) => { $(field).value = String(draft.form?.[field] || ''); });
      selectStyle(draft.style);
      state.files = (draft.files || []).filter((entry) => entry.file instanceof Blob).slice(0, 9).map((entry) => {
        const file = entry.file instanceof File ? entry.file : new File([entry.file], entry.file.name || '旅行照片.jpg', { type: entry.file.type });
        return { id: entry.id || uid(), file, url: URL.createObjectURL(file) };
      });
      state.result = draft.result ? normalizeResult(draft.result) : null;
      state.history = (draft.history || []).slice(-50).map(normalizeResult);
      state.future = (draft.future || []).slice(-50).map(normalizeResult);
      state.pendingJob = draft.pendingJob || null;
      noticeMessages = Array.isArray(draft.notices) ? draft.notices : [];
      if (draft.preview?.blob instanceof Blob && draft.preview.key === previewKey()) previewCache = { ...draft.preview, url: URL.createObjectURL(draft.preview.blob) };
      if (draft.fileCount > state.files.length) showError('文字草稿已恢复。部分照片未能保存在此设备，请重新选择照片。');
      $('draftStatus').textContent = '已恢复上次的草稿';
      if (FORM_FIELDS.some((field) => $(field).value)) $('supplementaryInfo').open = true;
      switchPanel(draft.mobilePanel === 'work' ? 'work' : 'materials');
    }
    restoring = false;
    renderPhotos();
    renderResult();
    if (state.result) {
      schedulePreview(true);
      checkUploadedPhotos();
    }
    if (state.pendingJob) {
      renderJob(state.pendingJob);
      if (['queued', 'running'].includes(state.pendingJob.status)) runPolling(state.pendingJob.job_id);
    }
  }

  async function clearDraft() {
    if (clearingDraft || state.generating || state.regenerating) return;
    if (!await window.ZhilvjiUI.confirm({ title: '清空这台设备上的草稿？', message: '这会移除草稿照片、文字和编辑历史。已下载的作品会保留。', confirmLabel: '清空草稿', destructive: true })) return;
    if (state.generating || state.regenerating) return;
    clearingDraft = true;
    closeDraftStorage();
    clearTimeout(saveTimer);
    clearTimeout(editorTimer);
    clearTimeout(previewTimer);
    editorBefore = null;
    previewVersion += 1;
    pollVersion += 1;
    previewController?.abort();
    state.files.forEach((entry) => URL.revokeObjectURL(entry.url));
    if (previewCache) URL.revokeObjectURL(previewCache.url);
    previewCache = null;
    Object.assign(state, { files: [], result: null, history: [], future: [], pendingJob: null });
    noticeMessages = [];
    FORM_FIELDS.forEach((field) => { $(field).value = ''; });
    selectStyle('xiaohongshu');
    clearTimeout(saveTimer);
    $('supplementaryInfo').open = true;
    $('finishedPreview').removeAttribute('src');
    $('finishedPreview').hidden = true;
    $('previewPlaceholder').hidden = false;
    $('previewPlaceholder').textContent = '正在把文字与照片排成一页手帐…';
    $('jobStatus').hidden = true;
    $('regenStatus').textContent = '';
    clearError();
    renderPhotos();
    renderResult();
    try { localStorage.removeItem(DRAFT_KEY); } catch { /* Storage may be unavailable. */ }
    await saveSequence.catch(() => {});
    try { await storeDraft('delete'); } catch { /* Text fallback is removed below. */ }
    try { localStorage.removeItem(DRAFT_KEY); } catch { /* Storage may be unavailable. */ }
    $('draftStatus').textContent = '草稿已清空';
    clearingDraft = false;
    updateControls();
    switchPanel('materials');
    $('uploadArea').focus();
  }

  function isPublicationReady() {
    return !restoring && !state.generating && !state.regenerating && !!state.result && !!journalText() && journalText().length <= MAX_JOURNAL && !!previewCache && previewCache.key === previewKey();
  }

  window.ZhilvjiEditor = {
    takePublicationSnapshot() {
      flushEditor();
      if (!isPublicationReady()) return null;
      return { result: clone(state.result), journalText: journalText(), previewBlob: previewCache.blob, signature: previewKey() };
    },
    isPublicationReady,
    focusEditor() {
      switchPanel('work');
      $('journalTitle').focus();
      $('editorHeading').scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  };

  $('materialsTab').addEventListener('click', () => switchPanel('materials'));
  $('workTab').addEventListener('click', () => switchPanel('work'));
  $('uploadArea').addEventListener('click', () => $('imageInput').click());
  $('imageInput').addEventListener('change', (event) => { addPhotos(event.target.files); event.target.value = ''; });
  ['dragenter', 'dragover'].forEach((event) => $('uploadArea').addEventListener(event, (e) => { e.preventDefault(); if (!state.generating) $('uploadArea').classList.add('drag-over'); }));
  ['dragleave', 'drop'].forEach((event) => $('uploadArea').addEventListener(event, () => $('uploadArea').classList.remove('drag-over')));
  $('uploadArea').addEventListener('drop', (event) => { event.preventDefault(); addPhotos(event.dataTransfer.files); });
  $('previewGrid').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    const item = button?.closest('[data-photo-id]');
    if (!item || state.generating) return;
    const index = state.files.findIndex((entry) => entry.id === item.dataset.photoId);
    if (index < 0) return;
    const action = button.dataset.action;
    if (action === 'remove') {
      const [removed] = state.files.splice(index, 1);
      URL.revokeObjectURL(removed.url);
      const next = state.files[Math.min(index, state.files.length - 1)];
      renderPhotos(next?.id, 'remove');
      if (!next) $('uploadArea').focus();
      scheduleSave();
    } else movePhoto(index, index + (action === 'up' ? -1 : 1), action);
  });
  $('previewGrid').addEventListener('dragstart', (event) => {
    const item = event.target.closest('[data-photo-id]');
    if (!item || state.generating || event.target.closest('button')) { event.preventDefault(); return; }
    draggedPhoto = item.dataset.photoId;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', draggedPhoto);
    item.classList.add('dragging');
  });
  $('previewGrid').addEventListener('dragover', (event) => {
    if (!draggedPhoto) return;
    const item = event.target.closest('[data-photo-id]');
    if (item) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; item.classList.add('drag-target'); }
  });
  $('previewGrid').addEventListener('dragleave', (event) => event.target.closest('[data-photo-id]')?.classList.remove('drag-target'));
  $('previewGrid').addEventListener('drop', (event) => {
    if (!draggedPhoto) return;
    event.preventDefault();
    const target = event.target.closest('[data-photo-id]')?.dataset.photoId;
    movePhoto(state.files.findIndex((entry) => entry.id === draggedPhoto), state.files.findIndex((entry) => entry.id === target));
    draggedPhoto = null;
  });
  $('previewGrid').addEventListener('dragend', () => {
    draggedPhoto = null;
    $('previewGrid').querySelectorAll('.dragging,.drag-target').forEach((item) => item.classList.remove('dragging', 'drag-target'));
  });
  $('resultPhotoGrid').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    const item = button?.closest('[data-result-photo]');
    if (!item || state.regenerating || button.disabled) return;
    const index = state.result?.image_filenames.indexOf(item.dataset.resultPhoto) ?? -1;
    const action = button.dataset.action;
    changeResultPhotos(index, index + (action === 'up' ? -1 : 1), action);
  });
  $('resultPhotoGrid').addEventListener('dragstart', (event) => {
    const item = event.target.closest('[data-result-photo]');
    if (!item || state.regenerating || event.target.closest('button')) { event.preventDefault(); return; }
    draggedResultPhoto = item.dataset.resultPhoto;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', draggedResultPhoto);
    item.classList.add('dragging');
  });
  $('resultPhotoGrid').addEventListener('dragover', (event) => {
    if (!draggedResultPhoto) return;
    const item = event.target.closest('[data-result-photo]');
    if (item) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; item.classList.add('drag-target'); }
  });
  $('resultPhotoGrid').addEventListener('dragleave', (event) => event.target.closest('[data-result-photo]')?.classList.remove('drag-target'));
  $('resultPhotoGrid').addEventListener('drop', (event) => {
    if (!draggedResultPhoto || !state.result) return;
    event.preventDefault();
    const filename = event.target.closest('[data-result-photo]')?.dataset.resultPhoto;
    changeResultPhotos(state.result.image_filenames.indexOf(draggedResultPhoto), state.result.image_filenames.indexOf(filename), 'move');
    draggedResultPhoto = null;
  });
  $('resultPhotoGrid').addEventListener('dragend', () => {
    draggedResultPhoto = null;
    $('resultPhotoGrid').querySelectorAll('.dragging,.drag-target').forEach((item) => item.classList.remove('dragging', 'drag-target'));
  });
  $('styleGrid').addEventListener('click', (event) => { const card = event.target.closest('[data-style]'); if (card) selectStyle(card.dataset.style); });
  FORM_FIELDS.forEach((field) => $(field).addEventListener('input', scheduleSave));
  $('journalForm').addEventListener('submit', (event) => { event.preventDefault(); generate(); });
  [['journalTitle', 'title'], ['journalBody', 'body'], ['journalTags', 'tags'], ['resultStyle', 'style'], ['resultDate', 'date'], ['resultWeather', 'weather'], ['resultAddress', 'address']].forEach(([id, field]) => {
    $(id).addEventListener(id === 'resultStyle' ? 'change' : 'input', () => editResult(field, $(id).value));
    $(id).addEventListener('blur', flushEditor);
  });
  $('undoBtn').addEventListener('click', undo);
  $('redoBtn').addEventListener('click', redo);
  $('copyBtn').addEventListener('click', copyText);
  $('exportBtn').addEventListener('click', download);
  $('retryPreviewBtn').addEventListener('click', () => schedulePreview(true));
  $('retryJobBtn').addEventListener('click', retryJob);
  $('continueJobBtn').addEventListener('click', () => { if (state.pendingJob) { clearError(); runPolling(state.pendingJob.job_id, { focusOnComplete: true }); } });
  $('regenButtons').addEventListener('click', (event) => { const button = event.target.closest('[data-tone]'); if (button && !button.disabled) regenerate(button.dataset.tone, button.textContent); });
  $('clearDraftBtn').addEventListener('click', clearDraft);
  function suspendPage() {
    if (!pageActive) return;
    const leavingDraft = !restoring ? draftData() : null;
    if (!restoring) saveTextFallback();
    pageActive = false;
    clearTimeout(saveTimer);
    clearTimeout(previewTimer);
    pollVersion += 1;
    previewVersion += 1;
    pollController?.abort();
    previewController?.abort();
    polling = false;
    if (!creatingJob && !retryingJob) state.generating = false;
    closeDraftStorage(leavingDraft);
  }

  function resumePage() {
    const wasInactive = !pageActive;
    pageActive = true;
    if (restoring) return;
    if (!creatingJob && !retryingJob && !polling) state.generating = false;
    renderPhotos();
    updateControls();
    if (!wasInactive) return;
    if (state.result) schedulePreview(true);
    // A returning page observes the existing task; it never creates another job.
    if (state.pendingJob?.job_id && !creatingJob && !retryingJob) runPolling(state.pendingJob.job_id);
    scheduleSave();
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') suspendPage(); else resumePage();
  });
  window.addEventListener('pagehide', suspendPage);
  window.addEventListener('pageshow', resumePage);
  updateControls();
  restoreDraft().catch(() => { restoring = false; renderPhotos(); renderResult(); showError('草稿恢复遇到问题，可以重新选择照片继续创作。'); });
})();
