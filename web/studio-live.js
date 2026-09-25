/* Fenix — studio live layer
 * Late-binding upgrades for the Music & Video studios:
 *  - Brain pills on both studios reflect real /api/brains health (no fake state).
 *  - Scene images retry automatically (the free image provider is shared, it can be busy).
 *  - Honest messaging when audio generation needs the one-time GPU worker.
 *  - Video pipeline disables the "Fenix Music bed" option while no generator is set up.
 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  };

  /* ---------------- Brain pills: real health, no faking ---------------- */
  function renderStudioPills(b) {
    var mp = $('#music-pill');
    if (mp) {
      var mOk = !!(b && b.music && b.music.configured);
      mp.classList.toggle('off', !mOk);
      mp.innerHTML = '<i></i>' + (mOk ? 'Fenix Music \u00b7 live' : 'Fenix Music \u00b7 offline');
    }
    var vp = $('#video-pill');
    if (vp) {
      var vOk = !!(b && b.video && b.video.configured);
      vp.classList.toggle('off', !vOk);
      vp.innerHTML = '<i></i>' + (vOk ? 'Fenix Video \u00b7 live' : 'Fenix Video \u00b7 offline');
    }
    var bp = $('#builder-pill');
    if (bp) {
      /* The Coder brain is the same trained mind on a coding persona: report the
         real server answer, never a hardcoded "online". */
      var bOk = !!(b && b.builder && b.builder.configured);
      bp.classList.toggle('off', !bOk);
      bp.innerHTML = '<i></i>' + (bOk ? 'Fenix Core LoRA Coder \u00b7 live' : 'Fenix Core LoRA Coder \u00b7 offline');
    }
  }

  function fetchBrains() {
    /* Same rule as the app: browsers always talk to their own origin; the
       absolute server URL is honored only inside the native APK WebView. */
    var isNative = typeof window.Capacitor !== 'undefined';
    var base = isNative
      ? (((window.FENIX_SERVER || window.PHOENIX_SERVER) || '') + '').replace(/\/+$/, '')
      : '';
    try {
      return fetch(base + '/api/brains').then(function (r) { return r.json(); });
    } catch (e) { return Promise.reject(e); }
  }

  function pollPills() {
    fetchBrains().then(renderStudioPills).catch(function () {});
    setTimeout(pollPills, 5 * 60 * 1000);
  }
  setTimeout(pollPills, 1500);

  /* ---------------- Scene images: automatic retry ---------------- */
  var VD = (typeof window.VD !== 'undefined') ? window.VD : null;
  function sceneImagesPatch() {
    VD = VD || (typeof window.VD !== 'undefined' ? window.VD : null);
    if (!VD) return false;
    var tries = {}; /* scene index -> attempts, keyed per node instead */
    $$('#vd-scenes .scene').forEach(function (node) {
      if (node.dataset.slLive) return; /* already bound */
      var img = node.querySelector('.thumb img');
      var status = node.querySelector('.img-status');
      if (!img || !status) return;
      node.dataset.slLive = '1';
      var attempts = 0;
      var ok = null, bad = null;
      ok = function () {
        attempts = 0;
        status.textContent = '\u2713 Image ready';
        status.style.color = 'var(--ok)';
      };
      bad = function () {
        attempts++;
        if (attempts <= 2) {
          status.textContent = '\u23f3 Busy \u2014 retrying automatically\u2026';
          status.style.color = '';
          setTimeout(function () {
            img.src = img.src.split('&slr=')[0] + '&slr=' + attempts;
          }, 2500 + attempts * 1500);
        } else {
          status.textContent = '\u2717 Image provider busy \u2014 tap \u201cNew image\u201d to retry';
          status.style.color = 'var(--danger)';
        }
      };
      img.addEventListener('load', ok);
      img.addEventListener('error', bad);
      /* trigger one fresh attempt now so errors fire through these handlers */
      img.src = img.src + (img.src.indexOf('?') > -1 ? '&' : '?') + 'slr=0';
    });
    return true;
  }
  /* scenes render twice per script write; hook renderScenes via scene-list observer */
  var sceneList = $('#vd-scenes');
  if (sceneList && 'MutationObserver' in window) {
    new MutationObserver(function () { sceneImagesPatch(); })
      .observe(sceneList, { childList: true });
  }

  /* ---------------- Honest audio-generation messaging ---------------- */
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('#mu-btn-generate');
    if (!btn) return;
    var note = $('#mu-state');
    if (note && note.classList.contains('show')) return; /* already running */
    setTimeout(function () {
      if (note && /Generating/i.test(note.textContent)) {
        note.textContent = '\ud83c\udfb9 Generating audio\u2026 (needs the free GPU worker on the server \u2014 lyrics & prompts stay free)';
      }
    }, 50);
  }, true);

  /* Toast helper consistent with the app's own toast */
  function toast(msg) {
    try {
      if (typeof window.showToast === 'function') { window.showToast(msg); return; }
    } catch (e) {}
    var t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:84px;inset-inline-start:50%;transform:translateX(-50%);'
      + 'background:#1a1a1f;color:#f7f5f2;border:1px solid #323238;border-radius:12px;'
      + 'padding:10px 16px;font-size:13px;z-index:9999;box-shadow:0 8px 24px rgba(0,0,0,.4)';
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3600);
  }
  window.__fenixToast = toast;

  /* Honest video music-bed picker: disable the AI bed while no generator exists */
  function patchMusicPicker(brains) {
    var sel = $('#vd-music-src');
    if (!sel || !brains) return;
    var audioReady = !!brains.audio_gen;
    var opt = sel.querySelector('option[value="fenix"]');
    if (!opt) return;
    if (!audioReady) {
      opt.textContent = 'Fenix Music bed \u2014 needs free GPU worker (setup required)';
      opt.disabled = true;
      if (sel.value === 'fenix') {
        sel.value = 'none';
        var m = $('#vd-music-name');
        if (m) { m.textContent = 'No music \u2014 AI bed needs setup'; m.classList.remove('hide'); }
      }
    } else {
      opt.disabled = false;
      opt.textContent = 'Fenix Music brain (free AI bed)';
    }
  }
  fetchBrains().then(patchMusicPicker).catch(function () {});
  setTimeout(function () { fetchBrains().then(patchMusicPicker).catch(function () {}); }, 4000);
})();
