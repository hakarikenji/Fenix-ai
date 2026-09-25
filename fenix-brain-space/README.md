---
title: Fenix Brain
emoji: 🐦‍🔥
colorFrom: teal
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Fenix Brain — API للعقل المدرَّب

يحمّل `Qwen/Qwen3-4B-Instruct-2507` + adapter التدريب من `Hakari66684/fenix-core-lora` ويقدّم API متوافق مع OpenAI:

```
POST https://<space-url>/v1/chat/completions
```

## الربط بخادم Fenix
اضبط على الخادم:

```
CUSTOM_LLM_BASE_URL=https://<space-url>/v1
CUSTOM_LLM_MODEL=fenix-core
```

أي فشل → يرجع تلقائياً لـ Gemini (الخادم مصمم كذلك أصلاً).
