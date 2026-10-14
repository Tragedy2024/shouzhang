(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { topic: '', q: '', mine: false, page: 0, posts: [], total: 0, hasMore: false, loading: false, detail: null, detailId: null, withdrawing: false };
  let listVersion = 0;
  let detailVersion = 0;
  let topicsVersion = 0;
  let listController;
  let detailController;
  let topicsController;
  let topicOptions = [];
  let lastFocus;
  let lastListKey = '';
  let lastLoadWasMore = false;
  let closingDialog = false;
  let searchTimer;
  let searchComposing = false;

  const validId = (id) => typeof id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(id);
  const listKey = () => JSON.stringify([state.topic, state.q, state.mine]);

  function initializeTheme() { window.ZhilvjiUI.installTheme('hall', $('hallThemeToggle')); }

  function safeMediaUrl(value, id, kind) {
    if (!validId(id) || typeof value !== 'string') return null;
    try {
      const url = new URL(value, location.origin);
      const expected = `/api/hall/posts/${encodeURIComponent(id)}/${kind}`;
      return url.origin === location.origin && url.pathname === expected && !url.search && !url.hash ? url.pathname : null;
    } catch { return null; }
  }

  function normalizePost(post) {
    if (!post || !validId(post.id)) throw new Error('作品信息暂时不完整，请重新加载。');
    const image = safeMediaUrl(post.image_url, post.id, 'image');
    const thumbnail = safeMediaUrl(post.thumbnail_url, post.id, 'thumbnail');
    if (!image || !thumbnail) throw new Error('作品图片暂时不可用，请重新加载。');
    return {
      ...post, title: typeof post.title === 'string' ? post.title : '未填写标题的手帐',
      caption: typeof post.caption === 'string' ? post.caption : '',
      author_name: typeof post.author_name === 'string' && post.author_name.trim() ? post.author_name : '未署名',
      topics: [...new Set((Array.isArray(post.topics) ? post.topics : []).filter((topic) => typeof topic === 'string' && topic.trim()).map((topic) => topic.trim()))].slice(0, 20),
      image_url: image, thumbnail_url: thumbnail, is_owner: post.is_owner === true,
      image_width: Number.isFinite(post.image_width) && post.image_width > 0 ? post.image_width : 750,
      image_height: Number.isFinite(post.image_height) && post.image_height > 0 ? post.image_height : 1000
    };
  }

  async function requestJSON(url, options = {}, timeout = 25000) {
    const controller = new AbortController();
    const upstream = options.signal;
    const abort = () => controller.abort();
    if (upstream?.aborted) controller.abort();
    upstream?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      let data;
      try { data = await response.json(); }
      catch { throw new Error('服务暂时没有返回有效结果，请重试。'); }
      if (!response.ok) {
        const error = new Error(data.error || data.message || '操作没有完成，请重试。');
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError' && !upstream?.aborted) throw new Error('请求等待较久，请检查网络后重试。');
      throw error;
    } finally {
      clearTimeout(timer);
      upstream?.removeEventListener('abort', abort);
    }
  }

  function formatTime(value, detail = false) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return '日期未记录';
    return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', ...(detail ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}) }).format(date);
  }

  function currentURL(postId = state.detailId) {
    const url = new URL('/hall', location.origin);
    if (state.topic) url.searchParams.set('topic', state.topic);
    if (state.q) url.searchParams.set('q', state.q);
    if (state.mine) url.searchParams.set('mine', '1');
    if (validId(postId)) url.searchParams.set('post', postId);
    return url.pathname + url.search;
  }

  function writeURL(postId, replace = false) {
    const url = currentURL(postId);
    if (url === location.pathname + location.search) return;
    history[replace ? 'replaceState' : 'pushState']({ hall: true }, '', url);
  }

  function renderTopics() {
    const container = $('hallTopics');
    container.replaceChildren();
    const topics = [{ name: '', count: null }, ...topicOptions];
    if (state.topic && !topicOptions.some((topic) => topic.name === state.topic)) topics.push({ name: state.topic, count: null });
    topics.forEach((topic) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.topic = topic.name;
      button.textContent = topic.name ? `#${topic.name}` : '全部话题';
      button.setAttribute('aria-pressed', String(state.topic === topic.name));
      button.classList.toggle('selected', state.topic === topic.name);
      if (topic.count !== null) {
        const count = document.createElement('span');
        count.className = 'hall-topic-count';
        count.textContent = String(topic.count);
        button.append(count);
      }
      container.append(button);
    });
  }

  async function loadTopics() {
    const version = ++topicsVersion;
    topicsController?.abort();
    topicsController = new AbortController();
    $('hallTopicsRetry').hidden = true;
    try {
      const data = await requestJSON('/api/hall/topics', { signal: topicsController.signal });
      if (version !== topicsVersion) return;
      if (!Array.isArray(data.topics)) throw new Error('话题暂时不可用。');
      topicOptions = data.topics.filter((topic) => topic && typeof topic.name === 'string' && topic.name.trim()).map((topic) => ({ name: topic.name.trim(), count: Math.max(0, Number(topic.count) || 0) }));
      renderTopics();
    } catch (error) {
      if (version !== topicsVersion || error.name === 'AbortError') return;
      $('hallTopicsRetry').hidden = false;
      $('hallTopicsRetry').title = error.message;
    }
  }

  function renderFilters() {
    $('hallSearchInput').value = state.q;
    $('hallSearchClear').hidden = !state.q;
    $('hallLatestTab').classList.toggle('active', !state.mine);
    $('hallMineTab').classList.toggle('active', state.mine);
    $('hallLatestTab').setAttribute('aria-pressed', String(!state.mine));
    $('hallMineTab').setAttribute('aria-pressed', String(state.mine));
    $('hallMineNote').hidden = !state.mine;
    if ($('hallClearFilters')) $('hallClearFilters').hidden = !(state.topic || state.q);
    renderTopics();
  }

  function card(post) {
    const link = document.createElement('a');
    link.className = 'hall-card';
    link.dataset.postId = post.id;
    link.href = currentURL(post.id);
    link.setAttribute('aria-label', `查看${post.author_name}的手帐：${post.title}`);
    const frame = document.createElement('div');
    frame.className = 'hall-cover-frame';
    const image = document.createElement('img');
    image.className = 'hall-cover';
    image.src = post.thumbnail_url;
    image.alt = `${post.title}，手帐封面`;
    image.loading = 'lazy';
    image.decoding = 'async';
    image.width = 750;
    image.height = 1000;
    image.addEventListener('error', () => {
      if (link.classList.contains('hall-card-image-failed')) return;
      link.classList.add('hall-card-image-failed');
      const note = document.createElement('span');
      note.className = 'hall-cover-failure';
      note.textContent = '封面暂未加载，点开查看';
      frame.append(note);
    });
    const copy = document.createElement('div');
    copy.className = 'hall-card-copy';
    const title = document.createElement('h2');
    title.textContent = post.title;
    copy.append(title);
    if (post.topics.length) {
      const topics = document.createElement('div');
      topics.className = 'hall-card-topics';
      post.topics.slice(0, 3).forEach((topic) => { const label = document.createElement('span'); label.textContent = `#${topic}`; topics.append(label); });
      copy.append(topics);
    }
    const byline = document.createElement('div');
    byline.className = 'hall-card-byline';
    const authorInfo = document.createElement('div');
    authorInfo.className = 'hall-card-author-info';
    const seal = document.createElement('span');
    seal.className = 'hall-author-seal';
    seal.setAttribute('aria-hidden', 'true');
    seal.textContent = Array.from(post.author_name.trim())[0] || '';
    const author = document.createElement('span');
    author.className = 'hall-card-author';
    author.textContent = post.author_name;
    const time = document.createElement('time');
    time.className = 'hall-card-date';
    time.textContent = formatTime(post.created_at);
    time.dateTime = post.created_at;
    authorInfo.append(seal, author);
    byline.append(authorInfo, time);
    copy.append(byline);
    frame.append(image);
    link.append(frame, copy);
    return link;
  }

  function renderList() {
    $('hallFeed').replaceChildren(...state.posts.map(card));
    $('hallFeed').setAttribute('aria-busy', String(state.loading));
    $('hallLoading').hidden = !state.loading || !!state.posts.length;
    $('hallLoadMore').hidden = !state.hasMore || !state.posts.length;
    $('hallLoadMore').disabled = state.loading;
    $('hallLoadMore').textContent = state.loading ? '正在翻下一页…' : '再看看更多';
    $('hallEndNote').hidden = state.loading || !state.posts.length || state.hasMore;
    const failed = !$('hallListError').hidden;
    $('hallEmpty').hidden = state.loading || !!state.posts.length || failed;
    const filtered = !!(state.topic || state.q);
    $('hallResetFilters').hidden = !filtered && !state.mine;
    $('hallEmptyTitle').textContent = filtered ? '还没有找到这样的手帐' : state.mine ? '你还没有公开分享手帐' : '这里还没有公开手帐';
    $('hallEmptyCopy').textContent = filtered ? '换一个话题或关键词，看看别人的旅程。' : state.mine ? '在创作页完成一页手帐后，就可以主动分享。' : '把喜欢的一页旅程，分享给经过这里的人。';
    if (state.loading) $('hallListStatus').textContent = state.posts.length ? '正在加载更多分享…' : '正在寻找公开分享的旅程…';
    else if (failed) $('hallListStatus').textContent = state.posts.length ? '已加载的作品保留在下方。' : '';
    else $('hallListStatus').textContent = state.total ? `${state.mine ? '我的发布' : state.topic ? `#${state.topic}` : '公开分享'} · ${state.total} 页手帐` : '';
  }

  async function loadList(more = false) {
    if (more && (state.loading || !state.hasMore)) return;
    const version = ++listVersion;
    listController?.abort();
    listController = new AbortController();
    const key = listKey();
    const page = more ? state.page + 1 : 1;
    lastLoadWasMore = more;
    state.loading = true;
    $('hallListError').hidden = true;
    renderList();
    const query = new URLSearchParams({ page: String(page), page_size: '12' });
    if (state.topic) query.set('topic', state.topic);
    if (state.q) query.set('q', state.q);
    if (state.mine) query.set('mine', '1');
    try {
      const data = await requestJSON(`/api/hall/posts?${query}`, { signal: listController.signal });
      if (version !== listVersion || key !== listKey()) return;
      if (!Array.isArray(data.posts)) throw new Error('作品列表暂时没有返回有效结果，请重试。');
      const posts = data.posts.map(normalizePost);
      state.posts = more ? [...state.posts, ...posts.filter((post) => !state.posts.some((existing) => existing.id === post.id))] : posts;
      state.page = Number(data.page) || page;
      state.total = Math.max(0, Number(data.total) || 0);
      state.hasMore = data.has_more === true;
      lastListKey = key;
    } catch (error) {
      if (version !== listVersion || error.name === 'AbortError') return;
      $('hallListError').hidden = false;
      $('hallListErrorText').textContent = error.message;
    } finally {
      if (version === listVersion) { state.loading = false; renderList(); }
    }
  }

  function setFilters(next, navigate = true) {
    const previous = listKey();
    Object.assign(state, next);
    state.topic = String(state.topic || '').trim().slice(0, 100);
    state.q = String(state.q || '').trim().slice(0, 200);
    state.mine = !!state.mine;
    if (navigate) {
      closeDetail(false);
      writeURL(null);
    }
    renderFilters();
    if (previous !== listKey() || lastListKey !== listKey()) {
      state.posts = [];
      state.page = 0;
      state.hasMore = false;
      state.total = 0;
      loadList();
    }
  }

  function resetDetail() {
    $('hallDetailTitle').textContent = '手帐详情';
    $('hallDetailContent').hidden = true;
    $('hallDetailError').hidden = true;
    $('hallDetailLoading').hidden = false;
    $('hallDetail').setAttribute('aria-busy', 'true');
    $('hallDetailImage').removeAttribute('src');
    $('hallImageError').hidden = true;
    $('hallImageRetry').hidden = true;
    $('hallOwnerActions').hidden = true;
    $('hallWithdrawConfirm').hidden = true;
    $('hallWithdrawStatus').textContent = '';
  }

  function renderDetail(post) {
    $('hallDetailTitle').textContent = post.title;
    $('hallDetailAuthor').textContent = post.author_name;
    $('hallDetailTime').textContent = `发布于 ${formatTime(post.created_at, true)}`;
    $('hallDetailTime').dateTime = post.created_at;
    $('hallDetailCaption').textContent = post.caption;
    $('hallDetailCaption').hidden = !post.caption;
    $('hallDetailImage').width = post.image_width;
    $('hallDetailImage').height = post.image_height;
    $('hallDetailImage').src = post.image_url;
    $('hallDetailImage').alt = `${post.title}，${post.author_name}分享的完整旅行手帐`;
    $('hallDetailTopics').replaceChildren();
    post.topics.forEach((topic) => { const button = document.createElement('button'); button.type = 'button'; button.dataset.topic = topic; button.textContent = `#${topic}`; $('hallDetailTopics').append(button); });
    $('hallOwnerActions').hidden = !post.is_owner;
    $('hallWithdrawStart').disabled = state.withdrawing;
    $('hallWithdrawConfirmBtn').disabled = state.withdrawing;
    $('hallDetailContent').hidden = false;
    $('hallDetailLoading').hidden = true;
    $('hallDetailError').hidden = true;
    $('hallDetail').setAttribute('aria-busy', 'false');
  }

  async function openDetail(id, { navigate = true, trigger = null } = {}) {
    if (!validId(id)) return;
    const version = ++detailVersion;
    detailController?.abort();
    detailController = new AbortController();
    if (!$('hallDetail').open) lastFocus = trigger || document.activeElement;
    state.detailId = id;
    state.detail = null;
    resetDetail();
    if (!$('hallDetail').open) $('hallDetail').showModal();
    document.body.classList.add('hall-dialog-open');
    $('hallDetailClose').focus({ preventScroll: true });
    if (navigate) writeURL(id);
    try {
      const data = await requestJSON(`/api/hall/posts/${encodeURIComponent(id)}`, { signal: detailController.signal });
      if (version !== detailVersion || state.detailId !== id) return;
      const post = normalizePost(data.post);
      if (post.id !== id) throw new Error('作品信息暂时不一致，请重试。');
      state.detail = post;
      renderDetail(post);
    } catch (error) {
      if (version !== detailVersion || error.name === 'AbortError') return;
      $('hallDetailLoading').hidden = true;
      $('hallDetailError').hidden = false;
      $('hallDetail').setAttribute('aria-busy', 'false');
      $('hallDetailErrorTitle').textContent = error.status === 404 ? '这页手帐已撤回或不存在' : '这页手帐暂时打不开';
      $('hallDetailErrorText').textContent = error.status === 404 ? '作者可能已经撤回公开展示。回到大厅，看看其他旅程吧。' : error.message;
      $('hallDetailRetry').hidden = error.status === 404;
    }
  }

  function closeDetail(navigate = true) {
    const wasOpen = $('hallDetail').open;
    const returnPostId = lastFocus?.dataset?.postId;
    ++detailVersion;
    detailController?.abort();
    state.detail = null;
    state.detailId = null;
    if ($('hallDetail').open) {
      closingDialog = true;
      $('hallDetail').close();
      closingDialog = false;
    }
    document.body.classList.remove('hall-dialog-open');
    if (navigate) writeURL(null);
    if (wasOpen) {
      const returnCard = validId(returnPostId) ? $('hallFeed').querySelector(`a[data-post-id="${returnPostId}"]`) : null;
      if (lastFocus?.isConnected) lastFocus.focus({ preventScroll: true });
      else if (returnCard) returnCard.focus({ preventScroll: true });
      else $('hallLatestTab').focus({ preventScroll: true });
    }
    lastFocus = null;
  }

  async function withdraw() {
    const post = state.detail;
    if (!post?.is_owner || state.withdrawing || $('hallWithdrawConfirm').hidden) return;
    state.withdrawing = true;
    $('hallWithdrawConfirmBtn').disabled = true;
    $('hallWithdrawCancel').disabled = true;
    $('hallWithdrawStart').disabled = true;
    $('hallWithdrawStatus').textContent = '正在撤回公开展示…';
    try {
      await requestJSON(`/api/hall/posts/${encodeURIComponent(post.id)}/withdraw`, { method: 'POST' });
      ++listVersion;
      listController?.abort();
      state.loading = false;
      state.posts = state.posts.filter((item) => item.id !== post.id);
      state.total = Math.max(0, state.total - 1);
      if (state.detailId === post.id) closeDetail();
      $('hallListStatus').textContent = '这页手帐已撤回公开展示。';
      renderList();
      loadList();
      loadTopics();
    } catch (error) {
      const message = `暂时未能确认撤回结果。请重试，或回到大厅刷新确认。${error.message}`;
      if (state.detailId === post.id) $('hallWithdrawStatus').textContent = message;
      else { $('hallListError').hidden = false; $('hallListErrorText').textContent = message; }
    } finally {
      state.withdrawing = false;
      $('hallWithdrawConfirmBtn').disabled = false;
      $('hallWithdrawCancel').disabled = false;
      $('hallWithdrawStart').disabled = false;
    }
  }

  function syncLocation() {
    const url = new URL(location.href);
    setFilters({ topic: url.searchParams.get('topic') || '', q: url.searchParams.get('q') || '', mine: url.searchParams.get('mine') === '1' }, false);
    const id = url.searchParams.get('post');
    if (validId(id)) { if (state.detailId !== id) openDetail(id, { navigate: false }); }
    else { if (state.detailId) closeDetail(false); if (id) writeURL(null, true); }
  }

  $('hallLatestTab').addEventListener('click', () => setFilters({ mine: false }));
  $('hallMineTab').addEventListener('click', () => setFilters({ mine: true }));
  const commitSearch = () => { clearTimeout(searchTimer); setFilters({ q: $('hallSearchInput').value }); };
  const queueSearch = () => {
    $('hallSearchClear').hidden = !$('hallSearchInput').value;
    clearTimeout(searchTimer);
    if (!searchComposing) searchTimer = setTimeout(commitSearch, 300);
  };
  $('hallSearchForm').addEventListener('submit', (event) => { event.preventDefault(); if (!searchComposing) commitSearch(); });
  $('hallSearchInput').addEventListener('input', queueSearch);
  $('hallSearchInput').addEventListener('compositionstart', () => { searchComposing = true; clearTimeout(searchTimer); });
  $('hallSearchInput').addEventListener('compositionend', () => { searchComposing = false; queueSearch(); });
  $('hallSearchInput').addEventListener('search', () => { if (!$('hallSearchInput').value) commitSearch(); });
  $('hallSearchClear').addEventListener('click', () => { $('hallSearchInput').value = ''; commitSearch(); $('hallSearchInput').focus(); });
  $('hallTopics').addEventListener('click', (event) => { const button = event.target.closest('button[data-topic]'); if (button) setFilters({ topic: button.dataset.topic }); });
  $('hallDetailTopics').addEventListener('click', (event) => { const button = event.target.closest('button[data-topic]'); if (button) setFilters({ topic: button.dataset.topic, mine: false, q: '' }); });
  $('hallResetFilters').addEventListener('click', () => setFilters({ topic: '', q: '', mine: false }));
  $('hallClearFilters')?.addEventListener('click', () => setFilters({ topic: '', q: '' }));
  $('hallLoadMore').addEventListener('click', () => loadList(true));
  $('hallListRetry').addEventListener('click', () => loadList(lastLoadWasMore));
  $('hallTopicsRetry').addEventListener('click', loadTopics);
  $('hallFeed').addEventListener('click', (event) => {
    const link = event.target.closest('a[data-post-id]');
    if (!link || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    openDetail(link.dataset.postId, { trigger: link });
  });
  $('hallDetailClose').addEventListener('click', () => closeDetail());
  $('hallDetail').addEventListener('cancel', (event) => { event.preventDefault(); closeDetail(); });
  $('hallDetail').addEventListener('close', () => { if (!closingDialog && state.detailId) closeDetail(); });
  $('hallDetail').addEventListener('click', (event) => { if (event.target === $('hallDetail')) closeDetail(); });
  $('hallDetailRetry').addEventListener('click', () => { if (state.detailId) openDetail(state.detailId, { navigate: false }); });
  $('hallDetailImage').addEventListener('error', () => { if (!state.detail) return; $('hallImageError').hidden = false; $('hallImageRetry').hidden = false; });
  $('hallDetailImage').addEventListener('load', () => { $('hallImageError').hidden = true; $('hallImageRetry').hidden = true; });
  $('hallImageRetry').addEventListener('click', () => { if (state.detail) { $('hallDetailImage').removeAttribute('src'); $('hallDetailImage').src = state.detail.image_url; } });
  $('hallWithdrawStart').addEventListener('click', () => { if (!state.detail?.is_owner) return; $('hallWithdrawConfirm').hidden = false; $('hallWithdrawConfirmBtn').focus(); });
  $('hallWithdrawCancel').addEventListener('click', () => { $('hallWithdrawConfirm').hidden = true; $('hallWithdrawStatus').textContent = ''; $('hallWithdrawStart').focus(); });
  $('hallWithdrawConfirmBtn').addEventListener('click', withdraw);
  window.addEventListener('popstate', syncLocation);
  initializeTheme();
  syncLocation();
  loadTopics();
})();
