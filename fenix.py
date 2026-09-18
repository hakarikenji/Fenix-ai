"""
Fenix AI — محرك محادثة متعدد الوسائط (نصوص، صور، مستندات PDF وأكواد)
يعتمد على Google Gemini API عبر حزمة google-genai الرسمية.

المتطلبات:
  GEMINI_API_KEY في ملف .env أو متغير البيئة
  pip install -r requirements.txt
"""

import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import chats, types

load_dotenv()  # يحمّل .env تلقائياً إن وُجد

# 1) إعداد العميل وربطه بمفتاح الـ API
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    sys.exit(
        "❌ خطأ: متغير البيئة GEMINI_API_KEY غير معرّف.\n"
        "   احصل على مفتاح من https://aistudio.google.com/app/apikey\n"
        '   ثم أضفه في .env أو: export GEMINI_API_KEY="your-api-key"'
    )

client = genai.Client(api_key=API_KEY)

# ⚠️ نماذج Pro تتطلب خطة مدفوعة (حصة المجانية = 0 عليها).
# النظام يجرّب الأقوى أولاً، وإن لم تتاح حصته ينتقل تلقائياً لأفضل نموذج متاح.
MODEL_CANDIDATES = [
    "gemini-3.1-pro-preview",  # الأقوى — مدفوع
    "gemini-3.6-flash",        # ممتاز ومتاح بالمجاني
    "gemini-3.5-flash",        # احتياط
]

# 2) البرومبت النظامي لشخصية Fenix
FENIX_SYSTEM_INSTRUCTION = """
أنت "Fenix AI"، نظام ذكاء اصطناعي فائق الذكاء ومتعدد القدرات (Multimodal).
تمت هندستك لتتفوق على الأنظمة التقليدية من خلال الدمج بين عمق تفكير Claude، وديناميكية ChatGPT، وقدرات Gemini التحليلية.

قواعدك الصارمة:
1. الشخصية: نبرة واثقة، ذكية، سريعة البديهة وبشرية للغاية (تجنب القوالب الآلية).
2. التفكير العميق: عند معالجة الصور أو المستندات، فكك المدخلات بدقة مجهرية قبل صياغة الحلول.
3. التنسيق: استخدم Markdown الاحترافي، الجداول، وصناديق الأكواد البرمجية النظيفة (Clean Code).
4. معالجة الملفات: حلل البيانات المستخرجة بدقة ولا تعتمد على التخمين.
"""


def _pick_model() -> str:
    """اختيار أول نموذج متاح فعلياً ضمن حصة المفتاح الحالية."""
    for model in MODEL_CANDIDATES:
        try:
            client.models.generate_content(model=model, contents="ping")
            return model
        except Exception:
            print(f"⚠️ النموذج {model} غير متاح ضمن حصتك — تجربة التالي...")
    sys.exit("❌ لا يوجد نموذج متاح ضمن حصتك الحالية. راجع: https://ai.dev/rate-limit")


def start_fenix_chat(model: str) -> chats.Chat:
    """بدء محادثة مستمرة تمتلك خاصية الذاكرة وسجل المحادثات."""
    return client.chats.create(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=FENIX_SYSTEM_INSTRUCTION,
            temperature=0.4,  # درجة منخفضة تضمن دقة منطقية وتقليل الهلوسة
        ),
    )


def _wait_for_file_active(uploaded_file) -> None:
    """
    انتظار انتهاء معالجة الملف المرفوع على خوادم Gemini حتى تصبح حالته ACTIVE.
    إرسال الملف أثناء حالة PROCESSING يتسبب في فشل الطلب — هذه الخطوة ضرورية للملفات الكبيرة.
    """
    file = client.files.get(name=uploaded_file.name)
    while file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        file = client.files.get(name=uploaded_file.name)
    print()
    if file.state.name != "ACTIVE":
        raise RuntimeError(f"فشلت معالجة الملف {uploaded_file.name}: {file.state.name}")


def analyze_image_or_file(chat_session: chats.Chat, file_path: str, user_prompt: str) -> str:
    """تحليل الصور أو المستندات (PDF, TXT, الأكواد) ودمجها في سياق المحادثة المستمرة."""
    if not os.path.exists(file_path):
        return "خطأ: الملف غير موجود."

    # رفع الملف بأمان إلى منصة Gemini للتعامل مع الأحجام الكبيرة (ميزة الـ Context Window)
    print(f"🔄 جاري رفع وتحليل المستند/الصورة لـ Fenix: {file_path}...")
    uploaded_file = client.files.upload(file=file_path)
    _wait_for_file_active(uploaded_file)

    # إرسال الملف مع البرومبت إلى جلسة المحادثة المستمرة لضمان حفظ السجل
    response = chat_session.send_message(message=[uploaded_file, user_prompt])
    return response.text


def safe_send(chat_session: chats.Chat, text: str) -> str:
    """إرسال رسالة مع معالجة أخطاء الحصة/الاتصال بدلاً من انهيار البرنامج."""
    try:
        return chat_session.send_message(text).text
    except Exception as e:
        return f"⚠️ تعذر الحصول على رد ({type(e).__name__}). قد تكون الحصة المؤقتة استُهلكت — جرّب بعد قليل."


def interactive_chat(chat_session: chats.Chat) -> None:
    """جلسة محادثة تفاعلية من الطرفية (اكتب 'خروج' للإنهاء)."""
    print('💬 وضع المحادثة التفاعلي — اكتب رسالتك (أو "خروج" للإنهاء):\n')
    while True:
        try:
            user_input = input("أنت: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in {"خروج", "exit", "quit"}:
            break
        print(f"\n[Fenix]: {safe_send(chat_session, user_input)}\n")


# =========================================================
# 🛠️ مثال تشغيلي يحاكي الواقع (Simulation)
# =========================================================
if __name__ == "__main__":
    model = _pick_model()
    fenix = start_fenix_chat(model)
    print(f"🔥 نظام Fenix AI جاهز للعمل والدعم المتعدد (النموذج: {model})...\n")

    # مثال 1: محادثة نصية عادية لتجربة الذاكرة والسجل
    print(f"[Fenix]: {safe_send(fenix, 'مرحباً، أنا المطور وعندي مشروع برمجته بـ Python.')}\n")

    # مثال 2: تحليل صورة (لقطة شاشة لواجهة مثلاً)
    # print(analyze_image_or_file(fenix, "screenshot.png", "حلل هذه الواجهة واستخرج الأخطاء التصميمية منها."))

    # مثال 3: تحليل ملف ضخم (PDF للتقرير المالي أو ملف كود كامل)
    # print(analyze_image_or_file(fenix, "project_v1.py", "راجع هذا الكود وطبق عليه معايير النظافة البرمجية (Clean Code)."))

    # اختبار الذاكرة: هل يتذكر Fenix لغتي البرمجية من الرسالة الأولى؟
    print(f"[Fenix - اختبار السجل]: {safe_send(fenix, 'ما هي لغة البرمجة التي أخبرتك أنني أستخدمها في مشروعي؟')}\n")

    # ثم الدخول في وضع المحادثة التفاعلي المستمر
    interactive_chat(fenix)
