# Trading with Jay — consolidated local website

A new Django project with its own accounts, community lounge, starting lesson
library, and creator-hosted live room. It does not use the earlier school's
accounts, database, signing key, teacher mechanics, or uploads.

Everything needed for this Windows local copy lives in this folder, including
Python and the installed website packages under `.runtime/python/`. It does not
need the earlier project or Codex's Python cache to run. Start it by double-clicking
`Start Trading with Jay.cmd`, then visit `http://127.0.0.1:8002/`. Keep the launcher
window open. The launcher uses paths relative to this folder, so the complete
folder can be moved together on a Windows 64-bit computer.

The existing accounts, chat data, and signing key have been preserved in `private/`.
Do not rerun setup to replace them. Back up this complete local folder privately.
GitHub Desktop uses `.gitignore` to leave `private/` and `.runtime/` out of uploads.
The Windows runtime is for local use; Render installs Linux packages using
`requirements.txt` after the production deployment configuration is prepared.

For a separate new demo, install `requirements.txt` in a normal Python environment,
then run `python setup_preview.py` and `python manage.py runserver 127.0.0.1:8002
--noreload`. Setup creates an isolated database and signing key under `private/`
and writes new local demo credentials into `private/preview-accounts.json`.
That folder must never be published or included in a shared distribution. Jay signs in
with the creator username `Admin01`; his public display name remains Jay.
`Admin` is the separate site-administrator account; `Viewer` is an ordinary member.
Public registration cannot claim the reserved creator or administrator names.
Setup uses the configured creator username and leaves existing preview accounts
unchanged while the private credentials file exists.

## Local live room

Jay or an administrator starts one live session. Signed-in members can receive
camera or screen-sharing media and participate in live chat. WebRTC signaling
uses authenticated HTTP polling and confines messages to the active session
and a host/member pair. The community lounge persists independently of live
sessions. Messages can be moderated through Django admin or the chat API's
creator/admin-only delete action. Live session history is metadata, not a video
recording; this demo does not record broadcasts.

No external streaming, signaling, AI, chat, or Discord service is configured.
The initial WebRTC setup has no external ICE servers. Localhost is a browser
secure context for camera/screen prompts. Hosting for people on other networks
needs HTTPS, a production web server, hardened settings, and a configured
STUN/TURN service. Configure optional comma-separated `JAY_STUN_URLS` and
`JAY_TURN_URLS` plus a server-only `JAY_TURN_SHARED_SECRET`. TURN credentials are
issued to signed-in users with a one-hour expiry; the shared secret is never
sent to the browser. No remote relay has been configured or tested here.

This prototype sends a separate peer connection per viewer. Audience size
therefore increases the host's upload bandwidth; a production broadcast needs
an SFU/media service, rate limits, moderation tools, monitoring, privacy policy,
and a reviewed deployment configuration. Those services are not claimed to be
present in the local demo.

## Starting lesson library

Nine existing educational sample videos, captions, and posters are included
under `protected/`. They are starting lessons, not recordings of Jay. Media is
served only to signed-in members, supports MP4 byte ranges, and uses private
no-store headers. No original private data is copied.

## Checks

Run `python manage.py test community` and `python manage.py check`. Tests cover
registration, host-only room actions, chat bounds and privacy, host/member
signal ownership, session isolation, and protected media.

The app defaults to `DEBUG=False`, loopback-only hosts, CSRF middleware, and
private SQLite storage. These are local-demo settings, not a public deployment.
