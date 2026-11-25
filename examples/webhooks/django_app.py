"""Didit webhook receiver for Django, as a single runnable file.

    pip install didit-sdk django
    DIDIT_WEBHOOK_SECRET=... python examples/webhooks/django_app.py runserver 8000

In a real project, put ``didit_webhook`` in your app's views.py and route it in urls.py.
"""

from __future__ import annotations

import os
import sys

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import didit

settings.configure(
    DEBUG=False,
    ALLOWED_HOSTS=["localhost", "127.0.0.1"],
    ROOT_URLCONF=__name__,
    SECRET_KEY=os.environ.get("DJANGO_SECRET_KEY", "change-me"),
)
SECRET = os.environ["DIDIT_WEBHOOK_SECRET"]


@csrf_exempt
@require_POST
def didit_webhook(request: HttpRequest) -> HttpResponse:
    try:
        event = didit.webhooks.verify(request.body, request.headers, SECRET)
    except didit.WebhookVerificationError as err:
        return HttpResponseBadRequest(err.reason)
    print("received", event.webhook_type, event.event_id)
    return HttpResponse(status=204)


urlpatterns = [path("webhooks/didit", didit_webhook)]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
