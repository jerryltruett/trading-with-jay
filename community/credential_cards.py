"""Optional, bearer-authorized credential cards; never put secrets in URLs."""

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods, require_POST


MAX_REQUEST_BYTES = 1024
MAX_CONFIG_BYTES = 16384
MAX_CARDS = 8
MAX_ACCOUNTS_PER_CARD = 8
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
UTC_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)"
)
UNAVAILABLE = {"error": "This access link is unavailable."}
CARD_FIELDS = {"label", "token_sha256", "enabled", "expires_at", "accounts"}
RESPONSE_HEADERS = {
    "Cache-Control": "no-store, private",
    "Pragma": "no-cache",
    "Expires": "0",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _protect(response):
    for name, value in RESPONSE_HEADERS.items():
        response[name] = value
    return response


class AccessCardProtectionMiddleware:
    """Place first in MIDDLEWARE so redirects and CSRF/errors stay protected."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        protected = any(
            request.path == path.rstrip("/") or request.path.startswith(path)
            for path in ("/access-card/", "/api/access-card/")
        )
        return _protect(response) if protected else response


def _unavailable():
    return _protect(JsonResponse(UNAVAILABLE, status=404))


@sensitive_variables("pairs", "value", "values")
def _unique_object(pairs):
    values = {}
    for name, value in pairs:
        if name in values:
            raise ValueError("Invalid access-card configuration.")
        values[name] = value
    return values


@sensitive_variables("value")
def _bounded_text(value, maximum):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and bool(value.strip())
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


@sensitive_variables("raw", "config", "entries", "entry", "accounts", "account", "cards")
def _load_cards():
    """Read bounded private configuration on each request to support revocation."""
    config_path = getattr(settings, "ACCESS_CARDS_FILE", "")
    if not config_path:
        return []
    try:
        with Path(config_path).open("rb") as source:
            raw = source.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            return []
        config = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(config, dict) or set(config) != {"cards"}:
            return []
        entries = config["cards"]
        if not isinstance(entries, list) or len(entries) > MAX_CARDS:
            return []
        cards, digests = [], set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != CARD_FIELDS:
                return []
            digest = entry["token_sha256"]
            if (not isinstance(digest, str) or not DIGEST_PATTERN.fullmatch(digest)
                    or digest in digests or type(entry["enabled"]) is not bool
                    or not _bounded_text(entry["label"], 100)):
                return []
            digests.add(digest)
            expiry = entry["expires_at"]
            if expiry is not None:
                if not isinstance(expiry, str) or not UTC_PATTERN.fullmatch(expiry):
                    return []
                expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if expiry.tzinfo is None or expiry.utcoffset() != timedelta(0):
                    return []
            accounts = entry["accounts"]
            if not isinstance(accounts, list) or not 1 <= len(accounts) <= MAX_ACCOUNTS_PER_CARD:
                return []
            usernames = set()
            for account in accounts:
                if (not isinstance(account, dict) or set(account) != {"username", "password"}
                        or not _bounded_text(account["username"], 150)
                        or not _bounded_text(account["password"], 256)
                        or account["username"] in usernames):
                    return []
                usernames.add(account["username"])
            cards.append({
                "label": entry["label"], "token_sha256": digest,
                "enabled": entry["enabled"], "expires_at": expiry,
                "accounts": accounts,
            })
        return cards
    except (OSError, ValueError, UnicodeError, TypeError, OverflowError, RecursionError):
        # Private configuration and credentials must never appear in an error.
        return []


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD"])
def access_card(request):
    # A public, empty shell: credentials are never included in HTML or GETs.
    response = render(request, "access_card.html")
    if request.method == "HEAD":
        response.content = b""
    return _protect(response)


@require_POST
@sensitive_post_parameters("token")
@sensitive_variables("raw", "payload", "token", "digest", "cards", "card", "selected")
def access_card_api(request):
    if request.content_type != "application/json" or request.GET:
        return _unavailable()
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            return _unavailable()
        raw = request.body
        if len(raw) > MAX_REQUEST_BYTES:
            return _unavailable()
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, OSError, RecursionError):
        return _unavailable()
    if not isinstance(payload, dict) or set(payload) != {"token"}:
        return _unavailable()
    token = payload["token"]
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        return _unavailable()
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    cards = _load_cards()
    now = datetime.now(timezone.utc)
    selected = None
    for card in cards:
        matches = hmac.compare_digest(card["token_sha256"], digest)
        if (matches and card["enabled"]
                and (card["expires_at"] is None or card["expires_at"] > now)):
            selected = card
    if selected is None:
        return _unavailable()
    return _protect(JsonResponse({"label": selected["label"], "accounts": selected["accounts"]}))
