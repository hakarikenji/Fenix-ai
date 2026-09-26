"""
Coder mode must never be a one-way door.

This reads the real front-end source and checks the specific failure that was
reported: entering Coder mode left no way out, so the only escapes were
deleting the project or signing out — both of which destroy something the user
wanted to keep.

Run:  python3 api/test_coder_exit.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI_PATH = os.path.join(ROOT, "web", "index_new.html")

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


src = open(UI_PATH, encoding="utf-8").read()
# The markup, with scripts and styles removed, is what the user actually sees.
markup = re.sub(r"<style[^>]*>[\s\S]*?</style>", "",
                re.sub(r"<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?</script>", "", src))


def body_of(name):
    i = src.index("function %s(" % name)
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j > 0 else len(src)]


print("the Coder label is a control, not a dead label")
check("the tag is a button", '<button type="button" class="model-tag" id="modelTag"' in markup,
      "modelTag is still a span")
check("it opens a menu", "openModeMenu" in src and "aria-haspopup" in markup)
check("the menu is a real container", 'id="modeMenu"' in markup and "role=\"menu\"" in markup)
check("it closes on Escape", "e.key === 'Escape'" in src)
check("it closes on an outside click", "!e.target.closest('#modeMenu')" in src)

print("the menu offers a way back to a normal chat")
menu = src[src.index("function openModeMenu("):src.index("$('#modelTag').addEventListener")]
check("it lists 'Back to normal chat' when in Coder", "'leave', 'Back to normal chat'" in menu)
check("it lists the project files", "item('files'" in menu)
check("it lists switching project", "item('projects'" in menu)
check("it lists both chat brains", "item('flash'" in menu and "item('pro'" in menu)
check("it shows which project is active", "Coder mode · " in menu)

print("leaving Coder is a real function that does not destroy anything")
leave = body_of("leaveCoder")
check("leaveCoder exists", bool(leave))
check("it clears the project id", "activeProjectId = null" in leave)
check("it does not delete the project", "DELETE" not in leave)
check("it does not remove files", "/files" not in leave)
check("it keeps the conversation", "saveChats()" in leave and "DELETE" not in leave)
check("it re-renders the chat", "renderMessages()" in leave and "syncModelTag()" in leave)
check("it says the project is still there", "still in your projects" in leave)
check("it is a no-op when not in Coder", "if (!activeProjectId) return" in leave)

print("there is more than one way out, so none can be a dead end")
check("the drawer has a 'Normal chat' row", "Normal chat" in src)
check("tapping the active project leaves Coder",
      "el.dataset.pid === activeProjectId" in src and "leaveCoder()" in src)
check("the Coder screen has a visible exit button", "coder-exit" in src and "welcomeExit" in src)
check("the exit button calls leaveCoder", "leaveCoder())" in src)
check("the exit button disappears on a normal chat", "if (ex) ex.remove()" in src)
check("switching to a chat brain also leaves Coder", "if (on) leaveCoder('silent')" in src)
check("signing out goes through the same path", "leaveCoder('silent')" in src)
check("deleting a project still works", "loadProjects(); syncModelTag(); renderMessages();" in src)

print("Coder mode still needs an account, and cannot trap a signed-out user")
check("coderMode requires a signed-in user", "activeProjectId && USER" in src)
check("a signed-out boot clears a stale project", "else if (activeProjectId)" in src)
check("a deleted project does not trap the user", "else leaveCoder('silent')" in src)

print("the menu is positioned after it is laid out")
menu_fn = body_of("openModeMenu")
check("the hide class comes off before measuring", menu_fn.index("classList.remove('hide')")
      < menu_fn.index("menu.offsetHeight"))
check("it is kept on screen horizontally", "window.innerWidth - mw - 10" in menu_fn)
check("and its height is capped to the viewport", "window.innerHeight - 20" in menu_fn)
check("it flips above the tag when there is no room", "r.top - 8 - mh" in menu_fn)

print("nothing about Coder mode changed on the server")
server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
check("no new server route was needed", "coder" not in server.lower()
      or "def api_coder" not in server, "coder logic leaked into the API")
print("  (note: leaving Coder is a client-side mode switch, so the API is untouched)")

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
