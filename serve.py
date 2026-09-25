#!/usr/bin/env python3
"""Fenix server launcher.

Tries gunicorn (production WSGI) and falls back to the Flask dev server when
gunicorn is unavailable. Keeps the Freebuff preview command stable
(`python server.py`) while upgrading the actual serving stack.
"""
import os
import sys


def _start_prober() -> None:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
    try:
        import brain_health  # noqa: E402

        brain_health.start_background()
    except Exception:
        pass


def main() -> None:
    _start_prober()
    try:
        import gunicorn  # type: ignore  # noqa: F401

        os.execvp(sys.executable, [sys.executable, "-m", "gunicorn",
                                   "-c", "gunicorn.conf.py", "server:app"])
    except ImportError:
        import server  # noqa: E402

        if hasattr(server, "brain_health") and hasattr(server.brain_health, "start_background"):
            pass  # already started via _start_prober import side effects
        port = int(os.environ.get("PORT", "8010"))
        print(f"🐦‍🔥 Fenix running on port {port} (dev server — install gunicorn for production)")
        server.app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
