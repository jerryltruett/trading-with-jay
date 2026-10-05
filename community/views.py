import base64
import hashlib
import hmac
import json
import mimetypes
import re
import time
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.staticfiles import finders
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .forms import JoinForm
from .identity import display_name
from .models import Broadcast, ChatMessage, LivePeer, Signal


def can_host(user):
    return bool(user.is_authenticated and user.is_active and (
        user.is_superuser or user.username.casefold() == settings.CREATOR_USERNAME.casefold()))


def current_host(user, broadcast):
    return bool(user.is_authenticated and user.is_active and (
        user.pk == broadcast.host_id or user.is_superuser))


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def read_json(request):
    if request.content_type != "application/json":
        raise ValueError("Send a JSON request.")
    if int(request.META.get("CONTENT_LENGTH") or 0) > 65536:
        raise ValueError("Request is too large.")
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON.")
    if not isinstance(data, dict):
        raise ValueError("Send a JSON object.")
    return data


def after_id(request):
    value = request.GET.get("after", "0")
    if not value.isdecimal() or len(value) > 18:
        raise ValueError("Invalid message cursor.")
    return int(value)


def canonical_peer(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("A peer must be a UUID.")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ValueError("A peer must be a UUID.")


def ice_servers(user):
    servers = []
    if settings.STUN_URLS:
        servers.append({"urls": settings.STUN_URLS})
    if user.is_authenticated and settings.TURN_URLS and settings.TURN_SHARED_SECRET:
        username = f"{int(time.time()) + 3600}:{user.pk}"
        credential = base64.b64encode(hmac.new(
            settings.TURN_SHARED_SECRET.encode(), username.encode(), hashlib.sha1).digest()).decode()
        servers.append({"urls": settings.TURN_URLS, "username": username, "credential": credential})
    return servers


def common_context(request):
    return {"can_host": can_host(request.user),
            "current_broadcast": Broadcast.objects.filter(active=True).select_related("host").first()
            if request.user.is_authenticated else None}


def active_broadcast():
    # Polling is the local demo's heartbeat; abandoned rooms become offline.
    expired = Broadcast.objects.filter(active=True,
                                       host_last_seen__lt=timezone.now() - timedelta(seconds=120))
    expired.update(active=False, ended_at=timezone.now())
    return Broadcast.objects.filter(active=True).select_related("host").first()


@ensure_csrf_cookie
def home(request):
    return render(request, "home.html", common_context(request))


@login_required
@ensure_csrf_cookie
def live(request):
    context = common_context(request)
    context["ice_servers"] = ice_servers(request.user)
    return render(request, "live.html", context)


class JayLoginView(LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def join(request):
    if request.user.is_authenticated:
        return redirect("members")
    form = JoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("members")
    return render(request, "join.html", {"form": form})


@login_required
@ensure_csrf_cookie
def members(request):
    context = common_context(request)
    context["posts"] = list(reversed(list(ChatMessage.objects.filter(room=ChatMessage.Room.LOUNGE)
                                          .select_related("user").order_by("-pk")[:50])))
    # Session history is metadata; it is not advertised as a video recording.
    context["broadcasts"] = Broadcast.objects.all().select_related("host")[:10]
    return render(request, "members.html", context)


def library_lessons():
    source = settings.PROTECTED_DIR / "courses.json"
    if not source.is_file():
        return []
    data = json.loads(source.read_text(encoding="utf-8"))
    lessons = []
    for course in data:
        clips = [{"number": 1, "title": course["lesson"], "duration": course["duration"],
                  "description": course["description"]}] + course.get("extraLessons", [])
        for clip in clips:
            number = clip["number"]
            asset = course["id"] if number == 1 else f"{course['id']}-{number}"
            lessons.append({"slug": course["id"], "number": number, "title": clip["title"],
                            "course_title": course["title"], "duration": clip["duration"],
                            "description": clip.get("description", ""), "topic": course["id"],
                            "takeaways": clip.get("takeaways", course.get("takeaways", [])),
                            "video_url": f"/media/{asset}.mp4",
                            "poster_url": f"/media/{asset}-poster.jpg",
                            "caption_url": f"/media/{asset}.vtt"})
    return lessons


@login_required
def library(request):
    context = common_context(request)
    return render(request, "library.html", context)


@login_required
@require_http_methods(["GET", "HEAD"])
def protected_media(request, asset):
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp4|jpg|vtt)", asset):
        raise Http404()
    root = (settings.PROTECTED_DIR / "media").resolve()
    target = (root / asset).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise Http404()
    size = target.stat().st_size
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    range_header = request.headers.get("Range")
    if range_header and target.suffix == ".mp4":
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or not (match[1] or match[2]):
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        start = int(match[1]) if match[1] else max(0, size - int(match[2]))
        end = min(int(match[2]), size - 1) if match[1] and match[2] else size - 1
        if start > end or start >= size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        handle = target.open("rb")
        handle.seek(start)

        def chunks():
            remaining = end - start + 1
            try:
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                handle.close()

        response = StreamingHttpResponse(chunks(), status=206, content_type=media_type)
        response._resource_closers.append(handle.close)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = end - start + 1
    else:
        response = FileResponse(target.open("rb"), content_type=media_type)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def static_asset(request, asset):
    if ".." in Path(asset).parts or "\\" in asset or asset.startswith("/"):
        raise Http404()
    if Path(asset).suffix.lower() not in (".css", ".js", ".webp", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".gif", ".woff", ".woff2", ".ttf"):
        raise Http404()
    found = finders.find(asset)
    if not found or not Path(found).is_file():
        raise Http404()
    response = FileResponse(open(found, "rb"), content_type=mimetypes.guess_type(found)[0] or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=300"
    return response


def live_status(request, broadcast=None):
    broadcast = broadcast or active_broadcast()
    active = bool(broadcast and broadcast.active)
    viewers = LivePeer.objects.filter(broadcast=broadcast, active=True,
                                      last_seen__gte=timezone.now() - timedelta(seconds=45)).count() if active else 0
    return {"active": active, "session_id": str(broadcast.session_id) if active else None,
            "title": broadcast.title if active else "The live room with Jay",
            "host_name": display_name(broadcast.host) if active and broadcast.host else settings.CREATOR_DISPLAY_NAME,
            "host_id": broadcast.host_id if active else None,
            "is_host": current_host(request.user, broadcast) if active else can_host(request.user),
            "viewer_count": viewers}


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def live_api(request):
    if not request.user.is_authenticated:
        return error("Sign in to enter the live room.", 401)
    if request.method == "GET":
        broadcast = active_broadcast()
        if broadcast and current_host(request.user, broadcast):
            Broadcast.objects.filter(pk=broadcast.pk).update(host_last_seen=timezone.now())
        return JsonResponse(live_status(request, broadcast))
    if not can_host(request.user):
        return error("Only Jay or an administrator can host a session.", 403)
    try:
        data = read_json(request)
    except ValueError as exc:
        return error(str(exc))
    action = data.get("action")
    if action not in ("start", "stop", "title"):
        return error("Choose start, stop, or title.")
    title = data.get("title", "The live room with Jay")
    if action in ("start", "title") and (not isinstance(title, str) or not title.strip() or len(title) > 120):
        return error("Use a title between 1 and 120 characters.")
    try:
        with transaction.atomic():
            broadcast = Broadcast.objects.select_for_update().filter(active=True).first()
            if broadcast and not current_host(request.user, broadcast):
                return error("Another host already has an active session.", 403)
            if action == "start":
                if not broadcast:
                    broadcast = Broadcast.objects.create(host=request.user, title=title.strip())
            elif not broadcast:
                return error("There is no active session.", 409)
            elif action == "title":
                broadcast.title = title.strip()
                broadcast.save(update_fields=["title"])
            else:
                broadcast.active = False
                broadcast.ended_at = timezone.now()
                broadcast.save(update_fields=["active", "ended_at"])
                broadcast.peers.update(active=False)
    except IntegrityError:
        return error("A session is already starting. Refresh the live room.", 409)
    return JsonResponse(live_status(request, broadcast))


def message_payload(message):
    return {"id": message.pk, "user": message.author_name, "body": message.body,
            "created_at": message.created_at.isoformat(), "is_host": message.is_host}


@require_http_methods(["GET", "POST"])
def chat_api(request):
    if not request.user.is_authenticated:
        return error("Sign in to join the conversation.", 401)
    data = {}
    try:
        cursor = after_id(request)
        if request.method == "POST":
            data = read_json(request)
    except ValueError as exc:
        return error(str(exc))
    room = data.get("room", request.GET.get("room", "live"))
    if room not in (ChatMessage.Room.LIVE, ChatMessage.Room.LOUNGE):
        return error("Choose the live or lounge room.")
    broadcast = active_broadcast() if room == "live" else None
    session_id = str(broadcast.session_id) if broadcast else None
    if room == "live":
        if not broadcast:
            return error("The live session has ended. Use the community lounge.", 409)
        requested_session = data.get("session_id", request.GET.get("session_id"))
        if requested_session != session_id:
            return error("This live chat session has changed. Rejoin the room.", 409)
    messages = ChatMessage.objects.filter(room=room, broadcast=broadcast)
    if request.method == "GET":
        if cursor:
            found = list(messages.filter(pk__gt=cursor)[:100])
        else:
            found = list(reversed(list(messages.order_by("-pk")[:100])))
        return JsonResponse({"messages": [message_payload(item) for item in found],
                             "newest_id": found[-1].pk if found else cursor,
                             "session_id": session_id})
    if data.get("action") == "delete":
        if not can_host(request.user):
            return error("Only the host or administrator can moderate messages.", 403)
        message_id = data.get("id")
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            return error("Choose a message to delete.")
        deleted, _ = messages.filter(pk=message_id).delete()
        return JsonResponse({"deleted": bool(deleted)})
    body = data.get("body")
    if not isinstance(body, str) or not body.strip() or len(body) > 1000:
        return error("Use a message between 1 and 1,000 characters.")
    if ChatMessage.objects.filter(user=request.user, created_at__gte=timezone.now() - timedelta(seconds=5)).count() >= 5:
        return error("Give the conversation a moment before posting again.", 429)
    message = ChatMessage.objects.create(room=room, broadcast=broadcast, user=request.user,
                                         author_name=display_name(request.user), body=body.strip(),
                                         is_host=current_host(request.user, broadcast) if broadcast else can_host(request.user))
    return JsonResponse({"message": message_payload(message), "session_id": session_id}, status=201)


def validate_signal_payload(kind, payload):
    if not isinstance(payload, dict) or len(json.dumps(payload)) > 40000:
        raise ValueError("Invalid signal payload.")
    if kind in ("join", "leave"):
        if payload:
            raise ValueError("Join and leave payloads must be empty objects.")
    elif kind in ("offer", "answer"):
        if set(payload) != {"type", "sdp"} or payload["type"] != kind:
            raise ValueError("Send the matching SDP type and description.")
        if not isinstance(payload["sdp"], str) or not payload["sdp"] or len(payload["sdp"]) > 32000:
            raise ValueError("Invalid SDP description.")
    elif kind == "ice":
        allowed = {"candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"}
        if not set(payload).issubset(allowed) or not isinstance(payload.get("candidate"), str) or len(payload["candidate"]) > 4096:
            raise ValueError("Invalid ICE candidate.")
        for key in ("sdpMid", "usernameFragment"):
            if payload.get(key) is not None and (not isinstance(payload[key], str) or len(payload[key]) > 256):
                raise ValueError("Invalid ICE metadata.")
        index = payload.get("sdpMLineIndex")
        if index is not None and (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= 512):
            raise ValueError("Invalid ICE media index.")


@require_http_methods(["GET", "POST"])
def signals_api(request):
    if not request.user.is_authenticated:
        return error("Sign in to enter the live room.", 401)
    broadcast = active_broadcast()
    if not broadcast:
        if request.method == "GET":
            return JsonResponse({"active": False, "signals": [], "newest_id": 0})
        return error("There is no active live session.", 409)
    try:
        cursor = after_id(request)
        data = read_json(request) if request.method == "POST" else {}
    except ValueError as exc:
        return error(str(exc))
    session_id = data.get("session_id", request.GET.get("session_id"))
    if session_id is not None and session_id != str(broadcast.session_id):
        return error("This live session has changed. Rejoin the room.", 409)
    if request.method == "GET":
        peer = request.GET.get("peer", "")
        if peer == "host":
            if not current_host(request.user, broadcast):
                return error("Only the session host can read host signals.", 403)
            Broadcast.objects.filter(pk=broadcast.pk).update(host_last_seen=timezone.now())
        else:
            try:
                peer = canonical_peer(peer)
            except ValueError as exc:
                return error(str(exc))
            owned = LivePeer.objects.filter(broadcast=broadcast, peer_id=peer, user=request.user).first()
            if not owned:
                return error("Join the room with your own peer ID first.", 403)
            LivePeer.objects.filter(pk=owned.pk).update(last_seen=timezone.now())
        signals = list(Signal.objects.filter(broadcast=broadcast, recipient=peer, pk__gt=cursor)[:100])
        return JsonResponse({"active": True, "signals": [{
            "id": signal.pk, "session_id": str(broadcast.session_id), "sender": signal.sender,
            "recipient": signal.recipient, "kind": signal.kind, "payload": signal.payload,
        } for signal in signals], "newest_id": signals[-1].pk if signals else cursor})
    if data.get("session_id") != str(broadcast.session_id):
        return error("Include the active session ID.", 409)
    sender, recipient, kind = data.get("sender"), data.get("recipient"), data.get("kind")
    if kind not in ("join", "offer", "answer", "ice", "leave"):
        return error("Unsupported signal kind.")
    payload = data.get("payload")
    try:
        validate_signal_payload(kind, payload)
        if sender == "host":
            if not current_host(request.user, broadcast):
                return error("Only the session host can send host signals.", 403)
            recipient = canonical_peer(recipient)
            if kind not in ("offer", "ice", "leave"):
                return error("The host may send offers, candidates, or leave signals.")
            if not LivePeer.objects.filter(broadcast=broadcast, peer_id=recipient).exists():
                return error("That viewer has not joined this session.", 403)
        else:
            sender = canonical_peer(sender)
            if recipient != "host" or kind not in ("join", "answer", "ice", "leave"):
                return error("Viewer signals must be addressed to the host.", 403)
            peer = LivePeer.objects.filter(broadcast=broadcast, peer_id=sender).first()
            if peer and peer.user_id != request.user.pk:
                return error("This peer ID belongs to another member.", 403)
            if not peer and kind != "join":
                return error("Join this session before sending signals.", 403)
            if kind == "join":
                peer, _ = LivePeer.objects.get_or_create(broadcast=broadcast, peer_id=sender,
                                                        defaults={"user": request.user})
                if peer.user_id != request.user.pk:
                    return error("This peer ID belongs to another member.", 403)
                peer.active = True
            elif kind == "leave":
                peer.active = False
            elif not peer.active:
                return error("Rejoin the live room before sending signals.", 409)
            peer.last_seen = timezone.now()
            peer.save(update_fields=["active", "last_seen"])
    except (ValueError, TypeError) as exc:
        return error(str(exc))
    signal = Signal.objects.create(broadcast=broadcast, sender=sender, recipient=recipient,
                                   kind=kind, payload=payload)
    return JsonResponse({"id": signal.pk}, status=201)
