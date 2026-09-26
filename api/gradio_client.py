"""Call a Gradio Space API and get the file it produced.

A Gradio app (which is what a hosted GPU Space must be) does not answer a
plain POST /. It exposes a small queue protocol instead:

    POST /gradio_api/call/<api_name>   {"data": [...]}  -> {"event_id": "..."}
    GET  /gradio_api/call/<api_name>/<event_id>         -> SSE stream
    ...whose completed event carries a file url to download.

This module speaks that protocol with the standard library only, so the Fenix
server needs no extra dependency to talk to a hosted engine. It is also the
fallback path for a Space: the Fenix server contract stays "POST / returns
bytes", so a Space is just another place to point the engine at.

Honest by design: every failure raises with the reason the Space gave, never
a silent empty result.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

# Routes to try, newest first. Gradio moved /call under /gradio_api.
_ROUTES = ("/gradio_api/call", "/call")


class GradioError(RuntimeError):
    """The Space refused, was unreachable, or answered something unusable."""


def _headers(extra: dict | None = None) -> dict:
    """Content type plus an optional bearer token.

    A hosted GPU Space meters its daily allowance per caller. An anonymous
    caller gets a small share of a shared pool that anyone can drain; a token
    gets its own allowance. The token is optional — a Space still answers
    without one — but it is the difference between a working engine and a
    quota error on a bad afternoon.
    """
    h = {"Content-Type": "application/json"}
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        h["Authorization"] = "Bearer " + token
    if extra:
        h.update(extra)
    return h


def _post(url: str, payload: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read(400).decode("utf-8", "replace")
        raise GradioError(f"HTTP {e.code} from the Space: {detail[:200]}") from e
    except Exception as e:  # noqa: BLE001
        raise GradioError(f"{type(e).__name__}: {e}") from e


def _events(url: str, timeout: int):
    """Stream the SSE response, yielding (event_name, payload) pairs.

    The event name matters: a Space signals failure with `event: error` and a
    null payload, which looks exactly like an empty result if only the payload
    is read. Without the name, a quota refusal reads as "the stream ended".
    """
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    name = "message"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk:
                    continue
                try:
                    yield name, json.loads(chunk)
                except ValueError:
                    continue  # a truncated keep-alive is not a result
    except urllib.error.HTTPError as e:
        raise GradioError(f"HTTP {e.code} while streaming the result: "
                          f"{e.read(300).decode('utf-8', 'replace')[:200]}") from e
    except Exception as e:  # noqa: BLE001
        raise GradioError(f"{type(e).__name__}: {e}") from e


def _reason(event) -> str:
    """Turn an error event into a sentence a person can act on.

    A hosted GPU host answers a spent allowance with an error event whose
    payload is null, so there is nothing to quote. Saying so — and naming the
    fix — beats printing `{'error': None}`.
    """
    if isinstance(event, dict):
        detail = event.get("message") or event.get("msg")
        if isinstance(event.get("error"), str):
            detail = event["error"]
        if detail:
            return f": {str(detail)[:300]}"
    elif isinstance(event, str) and event.strip() not in ("null", ""):
        return f": {event[:300]}"
    return (" with no reason given \u2014 on a shared GPU host this is almost always a spent "
            "daily allowance. A free token raises it, and hosting your own engine removes it.")


def _result_file(event, base: str):
    """Return the produced file's url from one SSE event, or None.

    Gradio has shipped two result shapes and both are live in the wild:
      older: {"data": [...], "is_completed": true, ...}
      newer: [{"url": ...}]  with the event name `complete`
    Assuming either one breaks against the other, so both are read, plus the
    error shape, so a real failure is never mistaken for a finished job.
    """
    if isinstance(event, dict):
        if event.get("error"):
            raise GradioError(f"the Space reported: {str(event['error'])[:300]}")
        if not event.get("is_completed"):
            return None
        event = event.get("data")

    items = event if isinstance(event, list) else [event]
    for item in items:
        if isinstance(item, str) and item:
            return urllib.parse.urljoin(base + "/", item)
        if isinstance(item, dict):
            url = item.get("url")
            if url:
                return urllib.parse.urljoin(base + "/", url)
            path = item.get("path")
            if path:
                return urllib.parse.urljoin(base + "/", "file=" + urllib.parse.quote(path))
    return None


def _download(url: str, timeout: int) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001
        raise GradioError(f"could not download the result: {type(e).__name__}: {e}") from e


def run(api_name: str, data: list, space_url: str, timeout: int = 600) -> bytes:
    """Call <api_name> on a Space and return the bytes of the file it made.

    `api_name` is the endpoint's name, e.g. "fenix_generate". `data` is the
    ordered list of arguments, matching the app's input order.
    """
    base = (space_url or "").rstrip("/")
    if not base:
        raise GradioError("no Space URL configured")
    if not api_name:
        raise GradioError("no api_name given")

    last = None
    for route in _ROUTES:
        try:
            queued = _post(f"{base}{route}/{api_name}",
                           {"data": list(data)}, min(timeout, 60))
        except GradioError as e:
            last = e
            continue
        event_id = queued.get("event_id")
        if not event_id:
            last = GradioError(f"the Space accepted the job but returned no event id: "
                               f"{str(queued)[:200]}")
            continue

        for name, event in _events(f"{base}{route}/{api_name}/{event_id}", timeout):
            if name == "error":
                raise GradioError("the hosted engine refused the job" + _reason(event))
            url = _result_file(event, base)
            if url:
                return _download(url, timeout)
        last = GradioError("the Space stream ended without a result")
    raise last or GradioError("the Space answered nothing usable")


def _page_status(page: str) -> str:
    """A short status from a Space's HTML page.

    The page is a full Gradio app shell, which is useless to read and worse to
    show a user, so only the parts that carry meaning are kept.
    """
    title = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    name = " ".join(title.group(1).split()) if title else ""
    stage = re.search(r'id="status"[^>]*>\s*([^<]{1,40})', page, re.I)
    parts = [name] if name else []
    if stage:
        parts.append(stage.group(1).strip())
    if "Slept" in page or "slept" in page:
        parts.append("wakes on request")
    return " · ".join(parts)[:120] or "reachable"


def health(space_url: str, timeout: int = 25) -> str:
    """Return the Space's own status string, or raise with the reason.

    A Space that is asleep still answers — that is the point of this call: it
    distinguishes "reachable but cold" from "gone", which a raw connection
    error cannot.
    """
    base = (space_url or "").rstrip("/")
    if not base:
        raise GradioError("no Space URL configured")
    try:
        # The token goes here too: a private or gated Space will not answer a
        # bare GET, and "unreachable" would be the wrong thing to report.
        with urllib.request.urlopen(urllib.request.Request(
                base + "/", headers=_headers()), timeout=timeout) as r:
            page = r.read(4000).decode("utf-8", "replace")
        return _page_status(page)
    except urllib.error.HTTPError as e:
        # A 404 on the root is normal: many Spaces only serve /gradio_api.
        if e.code in (404, 405):
            return "reachable (no root page)"
        raise GradioError(f"HTTP {e.code} from the Space") from e
    except Exception as e:  # noqa: BLE001
        raise GradioError(f"{type(e).__name__}: {e}") from e
