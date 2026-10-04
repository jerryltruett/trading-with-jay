"""Prepare only this fresh project's isolated local preview state."""
import json
import secrets
from pathlib import Path

from manage import prepare_runtime

project = Path(__file__).resolve().parent
private = project / "private"
private.mkdir(exist_ok=True)
key_path = private / "secret.key"
if not key_path.exists():
    key_path.write_text(secrets.token_urlsafe(64), encoding="utf-8")
prepare_runtime()
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from community.models import ChatMessage

call_command("migrate", interactive=False)
account_file = private / "preview-accounts.json"
if not account_file.exists():
    User = get_user_model()
    accounts = []
    for username, role in ((settings.CREATOR_USERNAME, "creator"), ("Viewer", "member"), ("Admin", "administrator")):
        password = secrets.token_urlsafe(20)
        if User.objects.filter(username=username).exists():
            raise RuntimeError("An account already exists; do not overwrite preview credentials.")
        if role == "administrator":
            user = User.objects.create_superuser(username=username, email="", password=password)
        else:
            user = User.objects.create_user(username=username, password=password)
        accounts.append({"username": username, "password": password, "role": role})
    account_file.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    creator = User.objects.get(username=settings.CREATOR_USERNAME)
    ChatMessage.objects.create(room="lounge", user=creator, author_name=settings.CREATOR_DISPLAY_NAME, is_host=True,
                               body="Welcome in. Bring your questions, compare ideas, and make this space your own.")
print("Fresh local preview ready. Preview accounts are stored privately; no passwords printed.")
