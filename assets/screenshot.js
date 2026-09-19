/*  Legacy Books — full-page screenshot download
    Adds a camera FAB that captures the entire page as PNG via html2canvas.  */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.textContent = [
    '.lb-screenshot-fab{position:fixed;bottom:1.4rem;right:4.8rem;z-index:9997;width:3rem;height:3rem;border-radius:50%;',
    'border:none;background:#b0472b;color:#fff;font-size:1.2rem;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,.25);',
    'display:flex;align-items:center;justify-content:center;transition:transform .15s ease,box-shadow .15s ease,opacity .15s ease}',
    '.lb-screenshot-fab:hover{transform:scale(1.08);box-shadow:0 4px 20px rgba(0,0,0,.35)}',
    '.lb-screenshot-fab.capturing{opacity:.5;pointer-events:none}',
    '.lb-screenshot-toast{position:fixed;bottom:5.2rem;right:1.4rem;z-index:9997;font-family:system-ui,sans-serif;',
    'font-size:.85rem;background:#222;color:#fff;padding:.55rem 1rem;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.3);',
    'opacity:0;transform:translateY(8px);transition:opacity .25s ease,transform .25s ease;pointer-events:none}',
    '.lb-screenshot-toast.show{opacity:1;transform:translateY(0)}',
  ].join('\n');
  document.head.appendChild(style);

  var h2cLoaded = false;
  var h2cLoading = false;

  function loadHtml2Canvas(cb) {
    if (h2cLoaded) { cb(); return; }
    if (h2cLoading) { var iv = setInterval(function () { if (h2cLoaded) { clearInterval(iv); cb(); } }, 100); return; }
    h2cLoading = true;
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
    s.onload = function () { h2cLoaded = true; h2cLoading = false; cb(); };
    s.onerror = function () { h2cLoading = false; toast('Failed to load screenshot library'); };
    document.head.appendChild(s);
  }

  var toastEl;
  var toastTimer;
  function toast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'lb-screenshot-toast';
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 3000);
  }

  function capture() {
    var fab = document.querySelector('.lb-screenshot-fab');
    fab.classList.add('capturing');
    toast('Capturing page…');

    // Close any open drawers/dropdowns
    document.querySelectorAll('details[open]').forEach(function (d) { d.removeAttribute('open'); });

    // Hide FABs and overlays during capture
    var fabs = document.querySelectorAll('.lb-search-fab,.lb-screenshot-fab,.lb-screenshot-toast,.lb-search-overlay');
    fabs.forEach(function (el) { el.style.visibility = 'hidden'; });

    loadHtml2Canvas(function () {
      html2canvas(document.body, {
        scrollY: -window.scrollY,
        scrollX: 0,
        windowWidth: document.documentElement.scrollWidth,
        windowHeight: document.documentElement.scrollHeight,
        useCORS: true,
        allowTaint: true,
        scale: 2,
        ignoreElements: function (el) {
          return el.classList && (
            el.classList.contains('lb-search-fab') ||
            el.classList.contains('lb-screenshot-fab') ||
            el.classList.contains('lb-screenshot-toast') ||
            el.classList.contains('lb-search-overlay')
          );
        },
      }).then(function (canvas) {
        var title = document.title.replace(/[^a-zA-Z0-9 _-]/g, '').trim().replace(/\s+/g, '-') || 'page';
        var link = document.createElement('a');
        link.download = title + '.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
        toast('Screenshot saved!');
      }).catch(function (err) {
        console.error('Screenshot error:', err);
        toast('Screenshot failed — try again');
      }).finally(function () {
        fabs.forEach(function (el) { el.style.visibility = ''; });
        fab.classList.remove('capturing');
      });
    });
  }

  function init() {
    var fab = document.createElement('button');
    fab.className = 'lb-screenshot-fab';
    fab.setAttribute('aria-label', 'Download page as image');
    fab.title = 'Download page as PNG';
    fab.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>';
    fab.addEventListener('click', capture);
    document.body.appendChild(fab);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
