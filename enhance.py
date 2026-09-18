"""
Fenix Prompt Enhancer — مهندس الأوامر الأول
تعطيه أمراً بسيطاً من سطر الأوامر، يرجع لك الأمر المحسّن (Enhanced Prompt) جاهزاً للإرسال.

الاستخدام:
  python enhance.py "اكتب لي تقرير عن مبيعات المتجر"
  echo "نص المستخدم" | python enhance.py
"""

import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL_NAME = "gemini-3.6-flash"  # سريع وغير مكلف — مثالي لمهام إعادة الصياغة (gemini-2.5-flash أُوقف للمستخدمين الجدد)

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


def enhance_prompt(user_text: str) -> str:
    """إرسال نص المستخدم إلى Gemini وإرجاع الأمر المحسّن."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"أمر المستخدم:\n\"\"\"\n{user_text}\n\"\"\"",
        config=types.GenerateContentConfig(
            system_instruction=ENHANCER_SYSTEM_INSTRUCTION,
            temperature=0.3,  # دقة عالية وتقليل الإبداع الزائد في إعادة الصياغة
        ),
    )
    return response.text


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit(
            "❌ خطأ: متغير البيئة GEMINI_API_KEY غير معرّف.\n"
            "   احصل على مفتاح من https://aistudio.google.com/app/apikey\n"
            '   ثم أضفه في .env أو: export GEMINI_API_KEY="your-api-key"'
        )

    # قراءة النص من الوسيطات، أو من stdin عند الأنابيب (echo "..." | python enhance.py)
    if len(sys.argv) > 1:
        user_text = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        user_text = sys.stdin.read().strip()
    else:
        sys.exit('الاستخدام: python enhance.py "أمر المستخدم هنا"')

    if not user_text:
        sys.exit("الاستخدام: python enhance.py \"أمر المستخدم هنا\"")

    print("🔄 جاري تحسين الأمر...", file=sys.stderr)
    try:
        result = enhance_prompt(user_text)
    except Exception as e:
        sys.exit(f"❌ فشل الاتصال بـ Gemini: {e}")

    print(result)


if __name__ == "__main__":
    main()
