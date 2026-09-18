"""أدوات مشتركة لدوال Fenix Studio على الاستضافة السحابية."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

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

# شخصية Fenix الافتراضية للمحادثة العامة (نفس روح Claude: ذكي، إنساني، مباشر)
FENIX_SYSTEM_INSTRUCTION = """
أنت "Fenix AI"، مساعد ذكاء اصطناعي فائق الذكاء ومتعدد القدرات.
تمت هندستك لتتفوق على الأنظمة التقليدية من خلال الدمج بين عمق تفكير Claude، وديناميكية ChatGPT، وقدرات Gemini التحليلية.

قواعدك:
1. الشخصية: نبرة واثقة، ذكية، سريعة البديهة وبشرية للغاية (تجنب القوالب الآلية والردود الجافة).
2. الدقة: لا تخترع معلومات — إن لم تكن متأكداً قل ذلك بصراحة.
3. التنسيق: استخدم Markdown عند الحاجة (عناوين، قوائم، جداول، صناديق أكواد نظيفة).
4. الإجابة بلغة المستخدم: إن كتب بالعربية أجب بالعربية الفصحى المبسطة، وإن كتب بإنجليزية أجب بالإنجليزية.
5. الاختصار الذكي: أجب كاملاً دون حشو — التفاصيل الزائدة المملة عدوك.
"""

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}


def load_prompts() -> dict:
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _generate(system_instruction: str, contents, temperature: float) -> str:
    """توليد عبر Gemini مع تجربة سلسلة النماذج عند الضغط/الفشل."""
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
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            return response.text
        except Exception as e:  # 503 ضغط / 429 حصة / 404 إيقاف → النموذج التالي
            last_error = e
    raise last_error  # type: ignore[misc]


def _chat_contents(history: list[dict], message: str):
    """بناء محتوى المحادثة: السجل كاملاً + الرسالة الجديدة (ذاكرة كاملة)."""
    contents = []
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=str(msg.get("content", "")))],
        ))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    return contents


def gemini_chat(history: list[dict], message: str) -> str:
    """محادثة بذاكرة كاملة: يُمرر سجل الرسائل مع كل طلب."""
    return _generate(
        FENIX_SYSTEM_INSTRUCTION,
        _chat_contents(history, message),
        temperature=0.7,
    )


def gemini_enhance(contents: str) -> str:
    """تحسين أمر المستخدم مع برومبت المهندس (بدون ذاكرة — مهمة واحدة)."""
    return _generate(ENHANCER_SYSTEM_INSTRUCTION, contents, temperature=0.3)
