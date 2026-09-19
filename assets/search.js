/*  Legacy Books — global search overlay
    Loads assets/search-index.json, builds a MiniSearch index, and provides
    a Cmd/Ctrl+K search popup usable from any page.                          */
(function () {
  'use strict';

  /* ── paths ── */
  var scriptEl = document.currentScript;
  var base = '';
  if (scriptEl) {
    var src = scriptEl.getAttribute('src') || '';
    base = src.replace(/assets\/search\.js.*$/, '');
  }
  if (!base && document.querySelector('link[href*="assets/search.css"]')) {
    base = document.querySelector('link[href*="assets/search.css"]').href.replace(/assets\/search\.css.*$/, '');
  }
  // fallback: figure out depth from path
  if (!base) {
    var depth = (location.pathname.match(/\//g) || []).length - 1;
    base = '../'.repeat(Math.max(0, depth));
  }

  var INDEX_URL = base + 'assets/search-index.json';

  /* ── state ── */
  var docs = null;       // raw array from JSON
  var miniSearch = null;  // MiniSearch instance
  var overlay = null;
  var input = null;
  var results = null;
  var activeIdx = -1;
  var loading = false;
  var loaded = false;

  /* ── inject CSS ── */
  var style = document.createElement('style');
  style.textContent = [
    /* fab */
    '.lb-search-fab{position:fixed;bottom:1.4rem;right:1.4rem;z-index:9998;width:3rem;height:3rem;border-radius:50%;',
    'border:none;background:#0d4f4f;color:#fff;font-size:1.3rem;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,.25);',
    'display:flex;align-items:center;justify-content:center;transition:transform .15s ease,box-shadow .15s ease}',
    '.lb-search-fab:hover{transform:scale(1.08);box-shadow:0 4px 20px rgba(0,0,0,.35)}',
    '.lb-search-fab .kbd{font-size:.6rem;position:absolute;top:-.45rem;right:-.3rem;background:#fff;color:#333;',
    'padding:.1rem .35rem;border-radius:4px;font-family:system-ui,sans-serif;box-shadow:0 1px 3px rgba(0,0,0,.2);pointer-events:none}',
    /* overlay */
    '.lb-search-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:none;align-items:flex-start;justify-content:center;padding:8vh 1rem 1rem;',
    'backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}',
    '.lb-search-overlay.open{display:flex}',
    /* modal */
    '.lb-search-modal{width:100%;max-width:600px;background:#fff;border-radius:14px;box-shadow:0 8px 40px rgba(0,0,0,.25);overflow:hidden;display:flex;flex-direction:column;max-height:72vh}',
    '@media(prefers-color-scheme:dark){.lb-search-modal{background:#1c1f25;color:#e8e3db}}',
    /* input row */
    '.lb-search-top{display:flex;align-items:center;gap:.6rem;padding:.75rem 1rem;border-bottom:1px solid #e2d9ce}',
    '@media(prefers-color-scheme:dark){.lb-search-top{border-color:#2c313a}}',
    '.lb-search-top svg{flex:none;width:1.2rem;height:1.2rem;stroke:#888;stroke-width:2.5;fill:none}',
    '.lb-search-input{flex:1;border:none;outline:none;background:transparent;font:inherit;font-size:1.05rem;color:inherit}',
    '.lb-search-input::placeholder{color:#aaa}',
    '.lb-search-esc{font-family:system-ui,sans-serif;font-size:.72rem;padding:.15rem .45rem;border-radius:4px;border:1px solid #ccc;color:#888;background:transparent;cursor:pointer}',
    '@media(prefers-color-scheme:dark){.lb-search-esc{border-color:#444;color:#888}}',
    /* results */
    '.lb-search-results{overflow-y:auto;padding:.4rem;flex:1}',
    '.lb-search-empty{padding:2rem 1rem;text-align:center;color:#999;font-size:.95rem}',
    '.lb-search-item{display:block;padding:.65rem .85rem;border-radius:8px;text-decoration:none;color:inherit;cursor:pointer;transition:background .1s}',
    '.lb-search-item:hover,.lb-search-item.active{background:#f0ece6}',
    '@media(prefers-color-scheme:dark){.lb-search-item:hover,.lb-search-item.active{background:#2c313a}}',
    '.lb-search-item-title{font-family:system-ui,sans-serif;font-weight:600;font-size:.95rem;line-height:1.3;display:block}',
    '.lb-search-item-crumb{font-family:system-ui,sans-serif;font-size:.75rem;color:#888;display:block;margin-top:.15rem}',
    '.lb-search-item-snippet{font-size:.82rem;color:#666;display:block;margin-top:.25rem;line-height:1.4}',
    '@media(prefers-color-scheme:dark){.lb-search-item-snippet{color:#999}}',
    '.lb-search-item-tags{display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.3rem}',
    '.lb-search-tag{font-family:system-ui,sans-serif;font-size:.65rem;padding:.1rem .4rem;border-radius:99px;background:#e8f4f4;color:#0d4f4f;font-weight:600}',
    '@media(prefers-color-scheme:dark){.lb-search-tag{background:#16262a;color:#5fbdb5}}',
    '.lb-search-footer{padding:.5rem 1rem;border-top:1px solid #e2d9ce;font-family:system-ui,sans-serif;font-size:.72rem;color:#aaa;text-align:center}',
    '@media(prefers-color-scheme:dark){.lb-search-footer{border-color:#2c313a}}',
    '.lb-search-loading{padding:2rem 1rem;text-align:center;color:#888}',
    '.lb-search-loading .spinner{display:inline-block;width:1.4rem;height:1.4rem;border:2.5px solid #ddd;border-top-color:#0d4f4f;border-radius:50%;animation:lb-spin .6s linear infinite}',
    '@keyframes lb-spin{to{transform:rotate(360deg)}}',
  ].join('\n');
  document.head.appendChild(style);

  /* ── create DOM ── */
  function createUI() {
    // floating action button
    var fab = document.createElement('button');
    fab.className = 'lb-search-fab';
    fab.setAttribute('aria-label', 'Search');
    fab.title = 'Search (Ctrl+K)';
    fab.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2.5" fill="none"><circle cx="10.5" cy="10.5" r="7"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>' +
      '<span class="kbd">⌘K</span>';
    fab.addEventListener('click', openSearch);
    document.body.appendChild(fab);

    // overlay
    overlay = document.createElement('div');
    overlay.className = 'lb-search-overlay';
    overlay.innerHTML = [
      '<div class="lb-search-modal">',
      '  <div class="lb-search-top">',
      '    <svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="7"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>',
      '    <input class="lb-search-input" type="text" placeholder="Search all books…" autocomplete="off" spellcheck="false">',
      '    <button class="lb-search-esc">Esc</button>',
      '  </div>',
      '  <div class="lb-search-results"></div>',
      '  <div class="lb-search-footer">Fuzzy search across 1,500+ pages &middot; ↑↓ to navigate &middot; Enter to open</div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);

    input = overlay.querySelector('.lb-search-input');
    results = overlay.querySelector('.lb-search-results');

    // events
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeSearch();
    });
    overlay.querySelector('.lb-search-esc').addEventListener('click', closeSearch);
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);
  }

  /* ── open / close ── */
  function openSearch() {
    overlay.classList.add('open');
    input.value = '';
    results.innerHTML = '';
    activeIdx = -1;
    input.focus();
    if (!loaded && !loading) loadIndex();
    else if (loaded) showHint();
  }

  function closeSearch() {
    overlay.classList.remove('open');
    activeIdx = -1;
  }

  function showHint() {
    results.innerHTML = '<div class="lb-search-empty">Type to search across all books, chapters, and sections</div>';
  }

  /* ── load index ── */
  function loadIndex() {
    loading = true;
    results.innerHTML = '<div class="lb-search-loading"><span class="spinner"></span><br>Loading search index…</div>';

    fetch(INDEX_URL)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        docs = data;
        buildMiniSearch();
        loaded = true;
        loading = false;
        showHint();
        if (input.value.trim()) onInput();
      })
      .catch(function (err) {
        loading = false;
        results.innerHTML = '<div class="lb-search-empty">Failed to load search index.</div>';
        console.error('Search index load error:', err);
      });
  }

  function buildMiniSearch() {
    miniSearch = new MiniSearch({
      fields: ['title', 'headings', 'body', 'tags', 'chapter', 'book'],
      storeFields: ['title', 'book', 'bookPath', 'chapter', 'chapterPath', 'section', 'path', 'body', 'tags'],
      searchOptions: {
        boost: { title: 5, headings: 3, tags: 4, chapter: 2, book: 1, body: 1 },
        fuzzy: 0.2,
        prefix: true,
      },
    });
    miniSearch.addAll(docs);
  }

  /* ── search ── */
  function onInput() {
    var q = input.value.trim();
    activeIdx = -1;
    if (!q) { showHint(); return; }
    if (!loaded) return;

    var hits = miniSearch.search(q, { combineWith: 'AND' });
    if (hits.length === 0) {
      hits = miniSearch.search(q, { combineWith: 'OR' });
    }
    hits = hits.slice(0, 30);

    if (hits.length === 0) {
      results.innerHTML = '<div class="lb-search-empty">No results for “' + escHtml(q) + '”</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i];
      var snippet = makeSnippet(h.body || '', q);
      var crumb = h.book;
      if (h.chapter && h.chapter !== h.title) crumb += ' › ' + h.chapter;
      var tagHtml = '';
      if (h.tags) {
        var ts = h.tags.split(' ');
        for (var t = 0; t < Math.min(ts.length, 4); t++) {
          tagHtml += '<span class="lb-search-tag">' + escHtml(ts[t]) + '</span>';
        }
      }
      html += '<a class="lb-search-item" href="' + base + escHtml(h.path) + '" data-idx="' + i + '">' +
        '<span class="lb-search-item-title">' + highlight(escHtml(h.title), q) + '</span>' +
        '<span class="lb-search-item-crumb">' + escHtml(crumb) + '</span>' +
        (snippet ? '<span class="lb-search-item-snippet">' + snippet + '</span>' : '') +
        (tagHtml ? '<span class="lb-search-item-tags">' + tagHtml + '</span>' : '') +
        '</a>';
    }
    results.innerHTML = html;
  }

  function makeSnippet(body, query) {
    if (!body) return '';
    var words = query.toLowerCase().split(/\s+/);
    var lBody = body.toLowerCase();
    var best = -1;
    for (var w = 0; w < words.length; w++) {
      var pos = lBody.indexOf(words[w]);
      if (pos !== -1) { best = pos; break; }
    }
    if (best === -1) best = 0;
    var start = Math.max(0, best - 40);
    var end = Math.min(body.length, best + 160);
    var snip = (start > 0 ? '…' : '') + body.substring(start, end) + (end < body.length ? '…' : '');
    return highlight(escHtml(snip), query);
  }

  function highlight(text, query) {
    var words = query.split(/\s+/).filter(Boolean);
    for (var i = 0; i < words.length; i++) {
      var ew = escRegex(escHtml(words[i]));
      text = text.replace(new RegExp('(' + ew + ')', 'gi'), '<b>$1</b>');
    }
    return text;
  }

  function escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function escRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* ── keyboard nav ── */
  function onKeydown(e) {
    var items = results.querySelectorAll('.lb-search-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      updateActive(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, -1);
      updateActive(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0 && items[activeIdx]) {
        items[activeIdx].click();
      } else if (items.length > 0) {
        items[0].click();
      }
    } else if (e.key === 'Escape') {
      closeSearch();
    }
  }

  function updateActive(items) {
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle('active', i === activeIdx);
    }
    if (activeIdx >= 0 && items[activeIdx]) {
      items[activeIdx].scrollIntoView({ block: 'nearest' });
    }
  }

  /* ── global shortcut ── */
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (overlay && overlay.classList.contains('open')) closeSearch();
      else openSearch();
    }
  });

  /* ── load MiniSearch from CDN then init ── */
  function boot() {
    if (window.MiniSearch) {
      createUI();
      return;
    }
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/minisearch@7.2.0/dist/umd/index.min.js';
    s.onload = createUI;
    s.onerror = function () { console.error('Failed to load MiniSearch'); };
    document.head.appendChild(s);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
