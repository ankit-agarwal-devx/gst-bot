from django.conf import settings
from django.utils import timezone

from bot.models import DailyUsage


def try_consume_upstream_call():
    """Count one call to tax-model against today's budget. Returns False if we're over budget."""
    today = timezone.localdate()
    row, _ = DailyUsage.objects.get_or_create(day=today)
    if row.upstream_calls >= settings.TAXMODEL["DAILY_CALL_BUDGET"]:
        return False
    row.upstream_calls = row.upstream_calls + 1
    row.save()
    return True


def calls_today():
    row = DailyUsage.objects.filter(day=timezone.localdate()).first()
    return row.upstream_calls if row else 0
