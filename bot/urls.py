from django.urls import path

from bot import views

urlpatterns = [
    path("healthz", views.healthz),
    path("api/conversations", views.create_conversation),
    path("api/conversations/<int:conversation_id>/messages", views.messages),
    path("api/gst/calculate", views.calculate),
]
