import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Broadcast(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=120, default="The live room with Jay")
    active = models.BooleanField(default=True)
    started_at = models.DateTimeField(default=timezone.now)
    host_last_seen = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["active"], condition=Q(active=True),
                                               name="one_active_broadcast")]

    def __str__(self):
        return self.title


class LivePeer(models.Model):
    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="peers")
    peer_id = models.UUIDField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["broadcast", "peer_id"], name="unique_room_peer")]


class ChatMessage(models.Model):
    class Room(models.TextChoices):
        LIVE = "live", "Live room"
        LOUNGE = "lounge", "Community lounge"

    room = models.CharField(max_length=10, choices=Room.choices, default=Room.LOUNGE)
    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name="messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    author_name = models.CharField(max_length=150)
    body = models.CharField(max_length=1000)
    is_host = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["room", "broadcast", "id"])]

    def __str__(self):
        return f"{self.author_name}: {self.body[:60]}"


class Signal(models.Model):
    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="signals")
    sender = models.CharField(max_length=36)
    recipient = models.CharField(max_length=36)
    kind = models.CharField(max_length=8)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["broadcast", "recipient", "id"])]
