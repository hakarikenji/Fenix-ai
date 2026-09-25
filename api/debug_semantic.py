"""Debug: inspect semantic similarity scores for a sample query."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("FENIX_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402
import semantic_memory as sm  # noqa: E402

entries = [
    {"id": "e1", "category": "projects", "text": "User is building an Android music app with Capacitor"},
    {"id": "e2", "category": "preferences", "text": "User prefers concise answers in Arabic"},
    {"id": "e3", "category": "goals", "text": "User wants to publish the app on Google Play"},
    {"id": "e4", "category": "facts", "text": "User's birthday is in March"},
]
print("scores for: how is the android music app development going?")
sm.reindex_all("tok4", entries)
qv = sm._embed("how is the android music app development going?")
vecs = db.all_embeddings("tok4")
for e in entries:
    print(e["id"], round(db.cosine(qv, vecs.get(e["id"], [])), 3), e["text"][:45])
