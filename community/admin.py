from django.contrib import admin
from .models import Broadcast, ChatMessage, LivePeer, Signal


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    list_display = ("title", "host", "active", "started_at", "ended_at")
    readonly_fields = ("session_id", "started_at")
    list_filter = ("active",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("author_name", "room", "body", "created_at")
    list_filter = ("room",)
    search_fields = ("author_name", "body")
    readonly_fields = ("created_at",)


@admin.register(LivePeer)
class LivePeerAdmin(admin.ModelAdmin):
    list_display = ("peer_id", "user", "broadcast", "active", "last_seen")


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ("broadcast", "sender", "recipient", "kind", "created_at")
    readonly_fields = ("payload", "created_at")
