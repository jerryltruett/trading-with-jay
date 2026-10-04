# Trading with Jay

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
The Windows runtime is for local use. Render installs its own Linux packages
from `requirements.txt`; `.runtime/`, `.venv/`, and `private/` stay out of GitHub.

For a separate new demo, install `requirements.txt` in a normal Python environment,
then run `python setup_preview.py` and `python manage.py runserver 127.0.0.1:8002
--noreload`. Setup creates an isolated database and signing key under `private/`
and writes new local demo credentials into `private/preview-accounts.json`.
That folder must never be published or included in a shared distribution. The
creator account uses username `Admin01`; the public site branding remains Jay.
`Admin` is the separate site-administrator account; `Viewer` is an ordinary member.
Public registration cannot claim the reserved creator or administrator names.
Setup uses the configured creator username and leaves existing preview accounts
unchanged while the private credentials file exists.

## Render hosting

The default configuration remains local. Setting `JAY_ENV=production` or using
Render's `RENDER=true` activates PostgreSQL, secure cookies, HTTPS redirects,
and WhiteNoise for the collected styles, scripts, and images. A hosted instance
refuses to start without a valid production secret and PostgreSQL URL; it cannot
fall back to the local database or signing key.

Commit and push these source files before configuring the Render web service.
Select the `main` branch and leave Root Directory blank. Use these commands:

| Render field | Value |
| --- | --- |
| Build Command | `bash build.sh` |
| Pre-Deploy Command | `python manage.py migrate --noinput` |
| Start Command | `python -m gunicorn jayproject.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -` |
| Health Check Path | `/` |

Pre-deploy commands require a paid Render web service. Choose hosting and database
plans deliberately before creating resources; no paid resource is defined by
this repository. The build script installs packages and collects static files.
Database migrations run separately before the new application starts.

Configure these private environment variables in Render:

- `JAY_ENV`: `production`.
- `SECRET_KEY`: use Render's Generate action for a new random secret of at least
  50 characters. Keep it stable across deployments and outside GitHub.
- `DATABASE_URL`: the Internal Database URL of a Render PostgreSQL database in
  the same workspace and region as the web service.

Render supplies `RENDER_EXTERNAL_HOSTNAME`. The allowed hosts also include
`tradingwithjay.online` and `www.tradingwithjay.online`; attach those domains to
the service and configure Porkbun DNS using the records Render provides. HTTPS
terminates at Render's proxy. The application trusts its forwarded HTTPS header.
Initial HSTS lasts one hour without including other subdomains or requesting
browser preload.

`.python-version` selects the latest Python 3.12 patch. Remove any conflicting
`PYTHON_VERSION` override in Render. The package versions in `requirements.txt`
are pinned; update them deliberately and rerun the checks below.

### Existing accounts and content

The first PostgreSQL deployment starts with an empty database. Migrations create
tables, not Jerry's existing accounts. Transfer the local account and community
data through a private database import before opening the hosted site to members.
Preserve user IDs, password hashes, and roles, including creator username
`Admin01`. A new signing key means everyone signs in again; it does not change
password hashes. Never commit a database export or paste it into a chat.

Do not run `setup_preview.py` on Render: it prepares a separate local demo with
demo accounts. Do not place the SQLite database on Render's temporary filesystem.

The current lesson catalog and protected lesson files are tracked under
`protected/` and deploy with the code. WhiteNoise serves only `staticfiles/`;
lesson media continues through the authenticated Django route. There is no
upload or recording feature, so the existing lesson files need no persistent
disk. Future uploads need a separate persistent storage design.

See [Render's Django guide](https://render.com/docs/deploy-django),
[Python version selection](https://render.com/docs/python-version), and
[custom domains](https://render.com/docs/custom-domains) for the current setup.

## Live room

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
therefore increases the host's upload bandwidth. A larger broadcast needs an
SFU/media service; public operation also needs appropriate rate limits,
monitoring, and member policies. The Render file configuration does not add a
media relay or test broadcasts across different networks.

## Starting lesson library

Nine existing educational sample videos, captions, and posters are included
under `protected/`. They are starting lessons, not recordings of Jay. Media is
served only to signed-in members, supports MP4 byte ranges, and uses private
no-store headers. No original private data is copied.

## Checks

Run `python manage.py test community` and `python manage.py check`. Tests cover
registration, host-only room actions, chat bounds and privacy, host/member
signal ownership, session isolation, and protected media.

Deployment setting tests use synthetic secrets and a dummy database URL without
connecting to PostgreSQL. Run `python -m unittest community.test_deployment`
with the installed requirements to check the hosted configuration. The bundled
Windows runtime runs the local compatibility check and skips production checks
because it does not include the hosting packages.

For production validation, set the hosting environment and run
`python manage.py check --deploy`. Real PostgreSQL migrations, Gunicorn startup
on Render. The four-account import and HTTPS sign-ins were verified on
2026-10-04. An end-to-end live broadcast and playback session still need
validation on the hosted service.


## Private QR login cards

The optional private card page is `/access-card/`. It has no menu links. The two
labelled codes are in `private/qr-codes/`: Study Logins (Study01 and Study02) and
Admin01 Login (Admin01 only). Admin02 is not included in either code. These are
possession-based links: anyone with a code or a copy of its decoded link can read
the assigned login details. Do not post the QR images publicly.

Each code contains an independent random 256-bit key in the URL fragment. The
browser removes the fragment, then sends it in a same-origin CSRF-protected POST.
Keys are absent from request paths, query strings, and normal access logs. The
server stores only key digests plus the explicitly configured login details in
`private/access-cards.json`. This additional plaintext password copy is private,
ignored by Git, and never collected into static files. Responses use no-store,
no-referrer, noindex, frame denial and a restrictive content security policy.

Local previews read the private configuration automatically. Production is
**disabled by default**. Publication of the selected login details was approved
and activated on Render on 2026-10-04. For Render, add a secret
file named `access-cards.json` containing the private configuration and set
`JAY_ACCESS_CARDS_FILE=/etc/secrets/access-cards.json`. Never commit that file,
`access-card-links.json`, or QR images. Do not paste private links or passwords
into deployment logs, screenshots, or source files.

All three QR passwords were checked against the local account hashes. The
Study Logins card (Study01 and Study02) and Admin01 Login card (Admin01 only)
were verified on the hosted site on 2026-10-04. The same day, the four accounts
were transferred into the confirmed empty Render database in one verified
transaction, preserving password hashes, IDs and role flags. All four HTTPS
sign-ins passed: both Study users are members, Admin01 can access the broadcast
studio, and Admin02 can access Django administration. The hosted user list
contains exactly these four accounts. No local chat or broadcast history was
transferred. A card showing details does not itself create an account.

The current local accounts are Admin01 (creator), Admin02 (administrator),
Study01 and Study02 (members). Fresh demo setup defaults described earlier are
independent of those existing renamed accounts; do not rerun setup to replace them.

To revoke a card, set its `enabled` to false or remove it from the private
configuration, then replace the active Render secret file and redeploy. An optional
UTC `expires_at` can limit its lifetime; null means it stays valid until revoked.
Changing a login password also requires updating its private card details. Rotating
a card key invalidates its old QR code independently of the account password.

The offline generator in `private/qr-tools/generate_qr_cards.py` uses the local
Segno and zxing-cpp packages; they are not runtime website dependencies. It creates
labelled PNG/SVG cards and a printable PDF and verifies the PNGs with an independent
decoder. Its configuration, key links, and output all remain in `private/`.
