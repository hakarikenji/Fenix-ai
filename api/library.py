"""دالة الاستضافة: إرجاع قائمة برومبتات المكتبة."""
import json

from common import load_prompts


def handler(request):
    items = [
        {"id": key, "title": item["title"], "description": item["description"]}
        for key, item in load_prompts().items()
    ]
    body = json.dumps(items, ensure_ascii=False)
    return (200, {"Content-Type": "application/json; charset=utf-8"}, body)
