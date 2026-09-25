/* Fenix stream identity compatibility layer.
   Keeps older cached pages aligned with the Fenix Core LoRA public identity. */
(function () {
  window.streamAI = async function (message, history, atts, onDelta) {
    const controller = new AbortController();
    stopGen = controller;
    const response = await fetch(apiUrl('/api/chat/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        message, history, attachments: atts, model: SET.model, style: SET.style,
        projectId: activeProjectId || undefined,
      }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error('Server unreachable (HTTP ' + response.status + ')');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let full = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const event of events) {
        const line = event.split('\n').find((item) => item.startsWith('data:'));
        if (!line) continue;
        let payload;
        try { payload = JSON.parse(line.slice(5).trim()); } catch (_) { continue; }
        if (payload.t === 'delta' && payload.v) {
          full += payload.v;
          onDelta(payload.v, full);
        } else if (payload.t === 'error') {
          if (!full) throw new Error(payload.v || 'Stream error');
        } else if (payload.t === 'done') {
          window.__fenixStreamBrain = payload.brain || 'fenix-core-lora';
          return full;
        }
      }
    }
    if (full) {
      window.__fenixStreamBrain = 'fenix-core-lora';
      return full;
    }
    throw new Error('Empty response — try again');
  };

  window.renderBrainBadge = function () {
    const reportedBrain = window.__fenixStreamBrain || lastBrain;
    if (!reportedBrain) return;
    const label = 'Fenix Core LoRA';
    $$('.brain-tag').forEach((element) => element.remove());
    $('#chatCol').insertAdjacentHTML('beforeend', '<div class="brain-tag"><i class="fa-solid fa-microchip"></i>' + escHtml(label) + '</div>');
    scrollDown();
    window.__fenixStreamBrain = null;
  };
})();
