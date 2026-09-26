from django.conf import settings
from django.db.models import F
from django.utils import timezone

from bot.models import DailyUsage


def try_consume_upstream_call():
    """Count one call to tax-model against today's budget. Returns False if we're over budget."""
    today = timezone.localdate()
    row, _ = DailyUsage.objects.get_or_create(day=today)
    updated = DailyUsage.objects.filter(
        pk=row.pk,
        upstream_calls__lt=settings.TAXMODEL["DAILY_CALL_BUDGET"],
    ).update(upstream_calls=F("upstream_calls") + 1)
    return updated == 1


def calls_today():
    row = DailyUsage.objects.filter(day=timezone.localdate()).first()
    return row.upstream_calls if row else 0
