from django.db import models


class Conversation(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16)  # "user" / "assistant"
    text = models.TextField()
    client_message_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)
    source = models.CharField(max_length=16, blank=True)  # faq / upstream / fallback
    degraded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def as_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "text": self.text,
            "client_message_id": self.client_message_id,
            "source": self.source or None,
            "degraded": self.degraded,
            "created_at": self.created_at.isoformat(),
        }


class DailyUsage(models.Model):
    day = models.DateField(unique=True)
    upstream_calls = models.PositiveIntegerField(default=0)
