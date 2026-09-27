"""Fenix on PythonAnywhere.

PythonAnywhere does not start a process the way a container host does — it
imports this file and calls `application`. So the dev server, the reloader and
gunicorn are all deliberately absent here: none of them would run.

Paste the whole file into the WSGI configuration file your web app points at
(Web tab → WSGI configuration file), or point that file at this one.

Two things this host changes and the app has to be told about:

  FENIX_DATA_DIR   where accounts, conversations, memory, evolution and the
                   training pairs live. PythonAnywhere gives a real filesystem
                   that survives restarts, so this is the one place the
                   training flywheel can actually accumulate. Set it in the
                   web app's environment variables.

  FENIX_TRUST_PROXY  PythonAnywhere serves the app from behind its own
                   proxy. Whether that proxy supplies X-Forwarded-For has to
                   be checked against the running app, because if it does and
                   the app does not believe it, every visitor shares one
                   generation allowance. Verify with /api/quota from two
                   networks before trusting the answer.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# server.py puts this on the path itself, but the WSGI import order can be the
# other way round on this host, and the api package must be importable first.
_API = os.path.join(_HERE, "api")
if _API not in sys.path:
    sys.path.insert(0, _API)

os.environ.setdefault("FENIX_DATA_DIR", os.path.join(_HERE, ".data"))

from server import app as application  # noqa: E402

# PythonAnywhere looks for this exact name.
app = application
