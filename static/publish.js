(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const AUTHOR_KEY = 'zhilvji-publish-author';
  const COMMON_TOPICS = ['旅行日记', '周末旅行', '城市漫步', '自然风光', '美食寻味'];
  let topicComposing = false;
  const state = { snapshot: null, signature: '', previewUrl: '', topics: [], busy: false, post: null, requestKey: '', payloadSignature: '' };
  const size = (text) => Array.from(text).length;
  const topicIdentity = (text) => text.toLowerCase().replace(/ß/g, 'ss').replace(/ς/g, 'σ');

  function preferredAuthor() {
    try { return localStorage.getItem(AUTHOR_KEY) || ''; } catch { return ''; }
  }

  function rememberAuthor() {
    const name = $('publishAuthor').value.trim();
    if (!name || size(name) > 30) return;
    try { localStorage.setItem(AUTHOR_KEY, name); } catch { /* Publishing also works without browser storage. */ }
  }

  function showError(message, field) {
    $('publishError').textContent = message;
    $('publishError').hidden = false;
    if (field) {
      $(field).setAttribute('aria-invalid', 'true');
      $(field).focus();
    }
  }

  function clearError() {
    $('publishError').hidden = true;
    $('publishError').textContent = '';
    ['publishTitle', 'publishCaption', 'publishAuthor', 'publishConfirm'].forEach((id) => $(id).removeAttribute('aria-invalid'));
  }

  function topicError(message) {
    $('publishTopicError').hidden = !message;
    $('publishTopicError').textContent = message || '';
    if (message) $('publishTopicInput').setAttribute('aria-invalid', 'true');
    else $('publishTopicInput').removeAttribute('aria-invalid');
  }

  function parseTopics(input) {
    return String(input || '').normalize('NFKC').split(/[#,，、;；\s]+/u).map((topic) => topic.trim()).filter(Boolean);
  }

  function addTopics(input) {
    if (state.busy || state.post) return false;
    const incoming = parseTopics(input);
    const invalid = incoming.find((topic) => size(topic) > 20 || /[\u0000-\u001f\u007f]/u.test(topic));
    if (invalid) {
      topicError(`话题“${invalid.slice(0, 22)}”不符合要求，每个话题最多 20 字。`);
      return false;
    }
    const topics = [...state.topics];
    const identities = new Set(topics.map(topicIdentity));
    incoming.forEach((topic) => {
      if (!identities.has(topicIdentity(topic))) { topics.push(topic); identities.add(topicIdentity(topic)); }
    });
    if (topics.length > 5) { topicError('最多添加 5 个话题，请先移除一个再添加。'); return false; }
    state.topics = topics;
    $('publishTopicInput').value = '';
    topicError('');
    renderTopics();
    return true;
  }

  function renderTopics() {
    $('publishTopics').replaceChildren();
    state.topics.forEach((topic, index) => {
      const chip = document.createElement('span');
      chip.className = 'topic-chip';
      const label = document.createElement('span');
      label.textContent = `#${topic}`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.dataset.topicIndex = index;
      remove.setAttribute('aria-label', `移除话题 ${topic}`);
      remove.disabled = state.busy || !!state.post;
      chip.append(label, remove);
      $('publishTopics').append(chip);
    });
    $('publishTopicSuggestions').replaceChildren();
    const suggestions = [...new Set([...(state.snapshot?.result.sections.tags || []), ...COMMON_TOPICS].map((topic) => String(topic).normalize('NFKC').replace(/^#+/, '').trim()))].filter((topic) => topic && size(topic) <= 20).slice(0, 8);
    suggestions.forEach((topic) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `#${topic}`;
      button.dataset.topicSuggestion = topic;
      button.disabled = state.busy || !!state.post || state.topics.length >= 5 || state.topics.some((selected) => topicIdentity(selected) === topicIdentity(topic));
      $('publishTopicSuggestions').append(button);
    });
  }

  function updateControls() {
    const locked = state.busy || !!state.post;
    ['publishTitle', 'publishCaption', 'publishAuthor', 'publishTopicInput', 'publishConfirm'].forEach((id) => { $(id).disabled = locked; });
    $('publishSubmitBtn').disabled = locked;
    $('publishSubmitBtn').textContent = state.busy ? '正在发布…' : '确认公开发布';
    $('publishCloseBtn').disabled = state.busy;
    $('publishEditBtn').disabled = state.busy;
    $('publishDoneBtn').disabled = state.busy;
    $('publishForm').setAttribute('aria-busy', String(state.busy));
    renderTopics();
  }

  function renderSuccess() {
    $('publishSuccess').hidden = !state.post;
    $('publishDialog').querySelector('.publish-layout').hidden = !!state.post;
    if (state.post) {
      const fallback = `/hall?post=${encodeURIComponent(state.post.id)}`;
      $('publishedPostLink').href = /^\/hall\?post=[a-zA-Z0-9_-]+$/.test(state.post.detail_url || '') ? state.post.detail_url : fallback;
      $('publishStatus').textContent = '已发布。';
    }
    updateControls();
  }

  function openPublish() {
    if (state.busy) return;
    const snapshot = window.ZhilvjiEditor?.takePublicationSnapshot();
    if (!snapshot) return;
    if (snapshot.signature !== state.signature) {
      if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
      state.snapshot = snapshot;
      state.signature = snapshot.signature;
      state.previewUrl = URL.createObjectURL(snapshot.previewBlob);
      state.topics = [];
      state.post = null;
      state.requestKey = '';
      state.payloadSignature = '';
      $('publishTitle').value = Array.from(snapshot.result.sections.title || '').slice(0, 100).join('');
      $('publishCaption').value = '';
      $('publishAuthor').value = preferredAuthor();
      $('publishTopicInput').value = '';
      $('publishStatus').textContent = '';
      clearError();
      topicError('');
    }
    // A fresh opening always requires the user's explicit public confirmation.
    $('publishConfirm').checked = false;
    $('publishPreview').src = state.previewUrl;
    renderSuccess();
    if (!$('publishDialog').open) $('publishDialog').showModal();
    if (state.post) $('publishedPostLink').focus();
    else $('publishTitle').focus();
  }

  function closePublish(focusEditor = false) {
    if (state.busy) return;
    $('publishDialog').close();
    if (focusEditor) window.ZhilvjiEditor?.focusEditor();
    else $('publishBtn').focus();
  }

  function validatePublication() {
    if (!state.snapshot) { showError('当前成品不可用，请返回编辑区重新打开发布窗口。'); return null; }
    if (size(String(state.snapshot.result.weather || '')) > 50) {
      showError('成品天气超过 50 字，请返回编辑区，在“调整成品风格与信息”中缩短天气后再发布。');
      $('publishEditBtn').focus();
      return null;
    }
    if (!addTopics($('publishTopicInput').value)) { $('publishTopicInput').focus(); return null; }
    const title = $('publishTitle').value.trim();
    const caption = $('publishCaption').value.trim();
    const author = $('publishAuthor').value.trim();
    if (!title || size(title) > 100) { showError('请填写 1 至 100 字的分享标题。', 'publishTitle'); return null; }
    if (size(caption) > 2000) { showError('分享说明最多 2,000 字，请缩短后再发布。', 'publishCaption'); return null; }
    if (!author || size(author) > 30) { showError('请填写 1 至 30 字的发布昵称。', 'publishAuthor'); return null; }
    if (!$('publishConfirm').checked) { showError('请先勾选公开发布确认，再发布到大厅。', 'publishConfirm'); return null; }
    return { title, caption, author_name: author, topics: [...state.topics] };
  }

  async function submitPublication() {
    if (state.busy || state.post) return;
    clearError();
    const publication = validatePublication();
    if (!publication) return;
    const payloadSignature = JSON.stringify([state.signature, publication]);
    if (payloadSignature !== state.payloadSignature || !state.requestKey) {
      state.payloadSignature = payloadSignature;
      state.requestKey = crypto.randomUUID();
    }
    const form = new FormData();
    form.append('title', publication.title);
    form.append('caption', publication.caption);
    form.append('author_name', publication.author_name);
    form.append('topics', JSON.stringify(publication.topics));
    form.append('public_confirm', 'true');
    form.append('idempotency_key', state.requestKey);
    const snapshot = state.snapshot;
    form.append('sections', JSON.stringify(snapshot.result.sections));
    form.append('journal_text', snapshot.journalText);
    ['style', 'date', 'weather', 'address', 'datetime_str'].forEach((field) => form.append(field, snapshot.result[field] || ''));
    form.append('image_filenames', snapshot.result.image_filenames.join(','));
    rememberAuthor();
    state.busy = true;
    $('publishStatus').textContent = '正在把这页手帐发布到大厅，请稍候…';
    updateControls();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch('/api/hall/posts', { method: 'POST', body: form, signal: controller.signal });
      let data;
      try { data = await response.json(); } catch { throw new Error('大厅暂时没有返回有效结果。表单已保留，请重试。'); }
      if (!response.ok) throw new Error(data.error || data.message || '发布没有完成。表单已保留，请重试。');
      if (!data.post?.id) throw new Error('暂时无法确认发布结果。表单已保留，请再次确认发布。');
      state.post = data.post;
      state.busy = false;
      renderSuccess();
      $('publishedPostLink').focus();
    } catch (error) {
      showError(error.name === 'AbortError' ? '发布等待较久。表单已保留，再次点击会继续确认这次发布。' : error.name === 'TypeError' ? '网络连接不稳定。表单已保留，请重试。' : error.message || '网络连接不稳定。表单已保留，请重试。');
      $('publishStatus').textContent = '分享信息已保留，可以重试。';
    } finally {
      clearTimeout(timer);
      state.busy = false;
      updateControls();
    }
  }

  $('publishBtn').addEventListener('click', openPublish);
  $('publishCloseBtn').addEventListener('click', () => closePublish());
  $('publishDoneBtn').addEventListener('click', () => closePublish());
  $('publishEditBtn').addEventListener('click', () => closePublish(true));
  $('publishDialog').addEventListener('cancel', (event) => { if (state.busy) event.preventDefault(); });
  $('publishDialog').addEventListener('close', () => $('publishBtn').focus());
  $('publishForm').addEventListener('submit', (event) => { event.preventDefault(); submitPublication(); });
  $('publishAuthor').addEventListener('blur', rememberAuthor);
  $('publishTopicInput').addEventListener('keydown', (event) => {
    if (topicComposing || event.isComposing || event.keyCode === 229) return;
    if (['Enter', ',', '，', '#', '＃'].includes(event.key)) { event.preventDefault(); addTopics($('publishTopicInput').value); }
  });
  $('publishTopicInput').addEventListener('input', (event) => {
    if (topicComposing || event.isComposing) return;
    if (/[#,，\n]/u.test($('publishTopicInput').value)) addTopics($('publishTopicInput').value);
    else topicError('');
  });
  $('publishTopicInput').addEventListener('compositionstart', () => { topicComposing = true; });
  $('publishTopicInput').addEventListener('compositionend', () => {
    topicComposing = false;
    if (/[#,，\n]/u.test($('publishTopicInput').value)) addTopics($('publishTopicInput').value);
    else topicError('');
  });
  $('publishTopics').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-topic-index]');
    if (!button || state.busy || state.post) return;
    state.topics.splice(Number(button.dataset.topicIndex), 1);
    topicError('');
    renderTopics();
    $('publishTopicInput').focus();
  });
  $('publishTopicSuggestions').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-topic-suggestion]');
    if (button && !button.disabled) addTopics(button.dataset.topicSuggestion);
  });
})();
