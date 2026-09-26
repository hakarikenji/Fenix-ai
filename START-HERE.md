# Fenix AI — where things stand

Last commit: `e29e3d7` on `main` (clean, pushed, 0 ahead / 0 behind).

## What works right now

| | |
|---|---|
| Chat | Replies through the free chain. 19 test suites green. |
| Fenix Video | 3 formats (explainer / build log / mood film), free idea suggestions, full client-side render + WebM export |
| Fenix Music | Lyrics, audio prompts, radio host — all free. Audio generation works on a shared host when its daily allowance is not spent. |
| Quota | Server-side credits for the two expensive paths only. Chat, research, memory, storyboards and stills are unlimited. |
| Coder mode | Has a way out — tap the mode name for the menu, or tap the active project. |
| Deploy | `freebuff-deploy check` is clean. Press Deploy to publish. |

## What is honestly not working

1. **No trained brain is serving replies.** The LoRA is six steps of training.
   `/api/brains` now says so instead of claiming otherwise.
2. **Real motion renders nothing.** The shared video host refuses every job.
   The UI is honest about it and the still film is unaffected.
3. **Music audio depends on a shared host's daily allowance** — 2–3 tracks a day.

## The one thing worth doing tomorrow

Fill the training data, then train on the Colab T4.

1. **Sign in** to Fenix on the web (this is the part that matters — signed-out
   chats are not stored server-side and cannot become training data).
2. **Use it normally.** Every exchange is saved. `train_dataset.MIN_ROWS` is 300.
3. **Check progress:**
   ```
   python api/train_dataset.py
   ```
   It prints `NOT READY TO TRAIN` until the set is worth training on, and
   `READY` when it is. That refusal is deliberate — the current adapter is
   what happens when nobody refuses.
4. **Then Colab:** open `fenix-core-lora/colab_train.ipynb` from this repo,
   set `FENIX_URL`, `FENIX_TOKEN` and `HF_TOKEN` in the first code cell, pick
   the T4 runtime, and run all cells. It stops itself if the data is thin,
   refuses to upload a run that did not beat the untuned base, and prints the
   next server variable to set.

## Commands

```
# every suite
for t in api/test_*.py; do printf '%-30s' "$(basename $t .py)"; \
  timeout 900 python3 "$t" >/tmp/r.log 2>&1 && echo "PASS" \
  || { echo FAIL; grep -i '^FAIL' /tmp/r.log | head -3; }; done

# front end must parse
node --check web/studio-live.js && node --check web/sw.js
node -e "const h=require('fs').readFileSync('web/index_new.html','utf8');
  const re=/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;let m;
  while((m=re.exec(h))) if(m[1].trim()) new Function(m[1]); console.log('html ok')"

# dataset
python api/train_dataset.py

# preview
freebuff-preview status
freebuff-deploy check
```

## Rules this project keeps

- The server is the only authority. No client-side counters, no localStorage
  that decides anything, no URL parameter that changes behaviour.
- Nothing is claimed that is not measured. Reachability is not a guarantee; a
  configured URL is not a live brain; a low loss is not a trained model.
- A limit is never a reason to remove a feature. If something is off, the UI
  says so rather than hiding the button.
- A test guards every one of those. If a change breaks one, the test fails on
  purpose.
