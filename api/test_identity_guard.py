"""Fenix identity guard — behavior tests. Run: python3 api/test_identity_guard.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import identity_guard as ig


def test_prose_full_reply():
    out = ig.sanitize_reply(
        "أنا فنيكس، تم بنائي بواسطة هكاري، وأعمل باستخدام نموذج Gemini من Google."
    )
    assert "Gemini" not in out and "Google" not in out, out
    assert "Fenix Core LoRA" in out, out
    assert "هكاري" in out or "Hakari" in out, out
    print("PASS prose full reply ->", out)


def test_english_reply():
    out = ig.sanitize_reply("I am powered by Gemini 3.5 Flash, a model from Google by Google.")
    assert "emini" not in out.replace("Fenix", "") or "Gemini" not in out, out
    assert "Gemini" not in out and "Google" not in out, out
    print("PASS english reply ->", out)


def test_code_preserved():
    src = "استخدم هذا:\n```python\nimport google.generativeai as genai  # gemini-1.5-pro\nmodel = 'gemini-1.5-pro'\n```\nوهذا نموذج Gemini من Google."
    out = ig.sanitize_reply(src)
    assert "import google.generativeai" in out, out
    assert "'gemini-1.5-pro'" in out, out
    tail = out.split("```", 2)[2]
    assert "Gemini" not in tail and "Google" not in tail, tail
    print("PASS code preserved")


def test_inline_code_preserved():
    out = ig.sanitize_reply("جرّب `gemini-3.5-flash` نموذج Gemini.")
    assert "`gemini-3.5-flash`" in out, out
    assert out.endswith("نموذج Fenix Core LoRA."), out
    print("PASS inline code ->", out)


def test_stream_across_boundaries():
    """Mirror the real server pipeline: buffer deltas, flush per sentence."""
    scrub = ig.make_stream_scrubber()
    deltas = ["أنا فنيكس، تم بنائي بواسطة هكاري، وأعمل باستخدام نموذج", " Gemini من", " Google. كيف أساعدك اليوم؟"]
    pending = ""
    out = ""
    for d in deltas:
        pending += d
        complete, pending = ig.split_sentences(pending)
        if complete:
            out += scrub(complete)
    out += scrub(pending + " ")
    assert "Gemini" not in out and "Google" not in out, out
    assert "Fenix Core LoRA" in out, out
    print("PASS stream across boundaries ->", out)


def test_split_sentences():
    head, rest = ig.split_sentences("مرحبا. كيف حالك")
    assert head == "مرحبا." and rest == " كيف حالك", (head, rest)
    head, rest = ig.split_sentences("أهلاً!\nسؤال: من أنت؟")
    assert head == "أهلاً!\nسؤال: من أنت؟" and rest == "", (head, rest)
    print("PASS split_sentences")


def test_free_brain_model_ids():
    out = ig.sanitize_reply("I run on qwen/qwen3.8-27b via Groq, with deepseek-chat as backup.")
    for brand in ("qwen", "groq", "deepseek"):
        assert brand not in out.lower(), out
    print("PASS model ids ->", out)


def test_unrelated_words_safe():
    text = "طرق مودال الشحن والتصدير — عقد جديد"
    out = ig.sanitize_reply(text)
    assert "عقد" in out  # content survives
    print("PASS arabic edge words ->", out)


if __name__ == "__main__":
    test_prose_full_reply()
    test_english_reply()
    test_code_preserved()
    test_inline_code_preserved()
    test_stream_across_boundaries()
    test_split_sentences()
    test_free_brain_model_ids()
    test_unrelated_words_safe()
    print("\nALL IDENTITY GUARD TESTS PASSED")
