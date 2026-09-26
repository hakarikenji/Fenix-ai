/* Fenix — studio live layer
 *  - Brain pills reflect real /api/brains health (no fake state).
 *  - Scene images retry automatically (the free provider is shared and can be busy).
 *  - Honest messaging when audio generation needs the one-time GPU worker.
 *  - Video pipeline disables the "Fenix Music bed" option while no generator is set up.
 *  - Scene image prompts are rewritten so every shot is anchored to the user's
 *    own topic and style. The director brain writes each scene prompt in
 *    isolation, which is why shots drifted away from the brief.
 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

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
    $$('#vd-scenes .scene').forEach(function (node) {
      if (node.dataset.slLive) return; /* already bound */
      var img = node.querySelector('.thumb img');
      if (!img) return;
      node.dataset.slLive = '1';
      var tries = 0;
      var retry = function () {
        /* The free image host is shared and returns 5xx when busy. Bust the
           cache each time so a retry really re-requests the image. */
        img.src = img.src.split('&slr=')[0] + '&slr=' + Date.now();
      };
      var guard = 0;
      var timer = setInterval(function () {
        guard += 1;
        if (img.complete && img.naturalWidth) { clearInterval(timer); return; }
        if (guard > 4 || tries >= 3) { clearInterval(timer); return; }
        tries += 1;
        retry();
      }, 4000);
    });
    return true;
  }

  function watchScenes() {
    var root = document.getElementById('vd-scenes');
    if (!root) return;
    new MutationObserver(function () { sceneImagesPatch(); }).observe(root, { childList: true, subtree: true });
    sceneImagesPatch();
  }

  /* ---------------- Keep every shot tied to the user's own brief ----------
   * The director brain writes each scene's `visual` prompt on its own, so two
   * adjacent scenes can end up describing different worlds. Re-anchoring each
   * prompt to the topic and style the user actually chose is what makes the
   * shots read as one film instead of unrelated stills. */
  function anchorScenePrompts() {
    VD = VD || (typeof window.VD !== 'undefined' ? window.VD : null);
    if (!VD || !VD.scenes) return;
    var topic = String(VD.topic || VD.brief || '').trim();
    var style = String(VD.style || '').trim();
    if (!topic) return;
    VD.scenes.forEach(function (sc) {
      if (!sc) return;
      if (!sc._anchored) {
        sc._anchored = true;
        sc._rawVisual = sc.visual || '';
      }
      var core = sc._rawVisual || sc.visual || '';
      if (core.toLowerCase().indexOf(topic.toLowerCase()) >= 0) return; /* already on-topic */
      sc.visual = (core + ' ' + topic + (style ? ', ' + style : '')).slice(0, 600);
    });
  }

  /* ---------------- Honest messaging for audio generation ---------------- */
  function toast(msg) {
    if (typeof window.__fenixToast === 'function') { window.__fenixToast(msg); return; }
    var el = $('#vd-state') || $('#mu-state');
    if (el) { el.textContent = msg; el.className = 'err'; }
  }

  function onAudioAttempt() {
    fetchBrains().then(function (b) {
      if (b && b.audio_gen) return; /* a real engine exists: stay quiet */
      toast('The audio engine is not connected yet. Lyrics, audio prompts and the ' +
            'whole video studio work without it. /api/music/generator-check shows the ' +
            'exact state.');
    }).catch(function () {});
  }

  /* The music bed follows the real engine state instead of being hard-disabled:
     an engine that comes online must not stay greyed out. */
  function patchMusicPicker() {
    var sel = $('#vd-music-src');
    if (!sel) return;
    var opt = sel.querySelector('option[value="fenix"]');
    if (!opt) return;
    fetchBrains().then(function (b) {
      var on = !!(b && b.audio_gen);
      opt.disabled = !on;
      opt.textContent = on ? 'Fenix Music bed (AI)'
                            : 'Fenix Music bed (the audio engine is not connected)';
    }).catch(function () {
      opt.disabled = true;
    });
  }

  function boot() {
    watchScenes();
    patchMusicPicker();
    document.addEventListener('click', function (e) {
      if (e.target && e.target.closest && e.target.closest('#mu-btn-generate')) onAudioAttempt();
    });
    /* Re-anchor as soon as a new script lands, before the images are fetched. */
    setInterval(function () { anchorScenePrompts(); sceneImagesPatch(); }, 2000);
    anchorScenePrompts();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
