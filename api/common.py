"""أدوات مشتركة لدوال Fenix Studio على الاستضافة السحابية."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# سلسلة النماذج: عند ضغط/فشل أحدها ينتقل تلقائياً للتالي
MODEL_CHAIN = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

PROMPTS_PATH = Path(__file__).parent / "prompts.json"

ENHANCER_SYSTEM_INSTRUCTION = """
أنت "مهندس أوامر أول" (Senior Prompt Engineer) بخبرة 10+ سنوات في هندسة الأوامر للنماذج التوليدية (GPT، Claude، Gemini).
مهمتك: تحويل "أمر المستخدم" إلى أمر محسّن (Enhanced Prompt) مفصّل ودقيق يُنتج أفضل نتيجة ممكنة من المحاولة الأولى.

قواعد إعادة الصياغة:
1. الدور: افتح الأمر المحسّن بتحديد شخصية خبير مناسبة لسياق الطلب (مبرمج سينيور، كاتب محترف، محلل بيانات...) مع سطر واحد يبرر اختيارها.
2. السياق: أضف خلفية واضحة للمهمة، القيود الفنية أو الزمنية، والجمهور المستهدف للمخرجات.
3. الجودة والأسلوب: حدّد نبرة الإجابة (رسمية / ودّية / تقنية) ومعايير الجودة (دقة، أمثلة عملية، تجنب الحشو).
4. شكل المخرجات: حدّده إلزامياً (نقاط مرقمة، جدول مقارنة، كود نظيف مع تعليقات، تقرير بأقسام...).
5. الالتزام: حافظ تماماً على نية المستخدم الأساسية — حسّن الصياغة ولا تغيّر الهدف أبداً.
6. الانضباط: لا تُضف طلبات جديدة لم يطلبها المستخدم، ولا تُغرق الأمر بتفاصيل زائدة.

حالات خاصة:
- إن كان الأمر غامضاً: اختر التفسير الأرجح وأكمل الصياغة، واذكر افتراضك في سطر واحد في النهاية.
- إن كان الأمر واضحاً ومكتمل الأركان: حسّن بنيته فقط دون إقحام تعقيد.

قواعد المخرجات (صارمة):
- أخرج الأمر المحسّن فقط داخل صندوق كود واحد (```).
- ممنوع أي مقدمات أو تفسيرات أو ملاحظات قبل الصندوق أو بعده.
- افحص مخرجاتك مقابل القاعدة 5 قبل الإخراج: أي انحراف عن نية المستخدم = صحّحه داخلياً ثم أخرج النسخة النهائية فقط.
"""


def load_prompts() -> dict:
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def gemini_enhance(contents: str) -> str:
    """إرسال نص جاهز إلى Gemini مع برومبت المهندس — مع تجربة النماذج بالتتابع عند الضغط."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY غير معرّف")
    client = genai.Client(api_key=api_key)
    last_error: Exception | None = None
    for model in MODEL_CHAIN:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=ENHANCER_SYSTEM_INSTRUCTION,
                    temperature=0.3,
                ),
            )
            return response.text
        except Exception as e:  # 503 ضغط / 429 حصة / 404 إيقاف → النموذج التالي
            last_error = e
    raise last_error  # type: ignore[misc]
