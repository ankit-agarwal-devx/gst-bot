import json
import re

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from bot import chat, gst
from bot.models import Conversation


def healthz(request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
def create_conversation(request):
    if request.method != "POST":
        return JsonResponse({"detail": "method not allowed"}, status=405)
    c = Conversation.objects.create()
    return JsonResponse({"id": c.id}, status=201)


@csrf_exempt
def messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if request.method == "GET":
        return JsonResponse({"messages": [m.as_dict() for m in conversation.messages.all()]})
    if request.method != "POST":
        return JsonResponse({"detail": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"errors": ["body must be a JSON object"]}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"errors": ["body must be a JSON object"]}, status=400)

    errors = []
    cmid = body.get("client_message_id")
    text = body.get("text")
    if not isinstance(cmid, str) or not re.match(r"^[A-Za-z0-9_-]{1,64}$", cmid):
        errors.append("client_message_id must be 1-64 characters of A-Z, a-z, 0-9, _ or -")
    if not isinstance(text, str) or not text.strip():
        errors.append("text must be a non-empty string")
    elif len(text) > 2000:
        errors.append("text must be at most 2000 characters")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    user_msg, reply, created = chat.post_message(conversation, cmid, text.strip())
    return JsonResponse({"message": user_msg.as_dict(), "reply": reply.as_dict()}, status=201 if created else 200)


@csrf_exempt
def calculate(request):
    if request.method != "POST":
        return JsonResponse({"detail": "method not allowed"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"errors": ["body must be a JSON object"]}, status=400)
    result, errors = gst.calculate(data)
    if errors:
        return JsonResponse({"errors": errors}, status=400)
    return JsonResponse(result)
