"""Credential-card checks with synthetic secrets and no database access."""

import hashlib
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path

from . import credential_cards


urlpatterns = [
    path("access-card/", credential_cards.access_card),
    path("api/access-card/", credential_cards.access_card_api),
]

TOKEN_STUDY = "A" * 43
TOKEN_HOST = "B" * 43
TEST_TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "OPTIONS": {"loaders": [("django.template.loaders.locmem.Loader", {
        "access_card.html": (
            "<!doctype html><title>Private access</title>"
            "<main>Scan an access card to continue.</main>{% csrf_token %}"
        ),
    })]},
}]


def make_card(token=TOKEN_STUDY, label="Synthetic Study Logins", **changes):
    card = {
        "label": label,
        "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
        "enabled": True,
        "expires_at": None,
        "accounts": [{"username": "StudyFixture01", "password": "Synthetic-study-only!"}],
    }
    card.update(changes)
    return card


@override_settings(
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["testserver"],
    CSRF_TRUSTED_ORIGINS=[],
    SECURE_SSL_REDIRECT=False,
    MIDDLEWARE=[
        "community.credential_cards.AccessCardProtectionMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
    ],
    TEMPLATES=TEST_TEMPLATES,
)
class CredentialCardTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="jay-card-test-")
        self.addCleanup(temporary.cleanup)
        self.config_path = Path(temporary.name) / "synthetic-cards.json"
        override = override_settings(ACCESS_CARDS_FILE=self.config_path)
        override.enable()
        self.addCleanup(override.disable)
        self.write_cards(make_card())

    def write_cards(self, *cards):
        self.config_path.write_text(json.dumps({"cards": list(cards)}), encoding="utf-8")

    def post_card(self, token=TOKEN_STUDY, client=None, **extra):
        return (client or self.client).post(
            "/api/access-card/", json.dumps({"token": token}),
            content_type="application/json", **extra,
        )

    def assert_protected(self, response):
        for name, value in credential_cards.RESPONSE_HEADERS.items():
            self.assertEqual(response.headers[name], value)

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), credential_cards.UNAVAILABLE)
        self.assert_protected(response)

    def test_valid_card_reveals_only_assigned_study_accounts(self):
        accounts = [
            {"username": "StudyFixture01", "password": "Synthetic-study-one!"},
            {"username": "StudyFixture02", "password": "Synthetic-study-two!"},
        ]
        self.write_cards(
            make_card(accounts=accounts),
            make_card(TOKEN_HOST, "Synthetic Admin01 Login", accounts=[{
                "username": "HostFixture01", "password": "Synthetic-host-only!",
            }]),
        )
        response = self.post_card()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"label": "Synthetic Study Logins", "accounts": accounts})
        self.assertNotIn(b"HostFixture01", response.content)
        self.assert_protected(response)

    def test_host_card_cannot_reveal_study_accounts(self):
        host = [{"username": "HostFixture01", "password": "Synthetic-host-only!"}]
        self.write_cards(make_card(), make_card(TOKEN_HOST, "Synthetic Admin01 Login", accounts=host))
        response = self.post_card(TOKEN_HOST)
        self.assertEqual(response.json()["accounts"], host)
        self.assertNotIn(b"StudyFixture01", response.content)
        self.assert_protected(response)

    def test_shell_and_head_never_include_credentials_or_token(self):
        for method in (self.client.get, self.client.head):
            with self.subTest(method=method.__name__):
                response = method("/access-card/")
                self.assertEqual(response.status_code, 200)
                for secret in ("StudyFixture01", "Synthetic-study-only!", TOKEN_STUDY):
                    self.assertNotIn(secret.encode(), response.content)
                self.assert_protected(response)
        self.assertEqual(self.client.head("/access-card/").content, b"")

    def test_direct_get_and_token_query_cannot_reveal_credentials(self):
        response = self.client.get("/api/access-card/", {"token": TOKEN_STUDY})
        self.assertEqual(response.status_code, 405)
        self.assertNotIn(b"StudyFixture01", response.content)
        self.assert_protected(response)
        response = self.client.post(
            "/api/access-card/?token=" + TOKEN_STUDY, json.dumps({"token": TOKEN_STUDY}),
            content_type="application/json",
        )
        self.assert_unavailable(response)

    def test_unknown_token_matches_missing_expired_and_revoked_errors(self):
        self.assert_unavailable(self.post_card("C" * 43))
        for change in ({"enabled": False}, {"expires_at": "2000-01-01T00:00:00Z"}):
            with self.subTest(change=change):
                self.write_cards(make_card(**change))
                self.assert_unavailable(self.post_card())

    def test_future_utc_expiry_is_accepted(self):
        for expiry in ("2100-01-01T00:00:00Z", "2100-01-01T00:00:00.123456+00:00"):
            with self.subTest(expiry=expiry):
                self.write_cards(make_card(expires_at=expiry))
                self.assertEqual(self.post_card().status_code, 200)

    def test_rotation_or_disable_takes_effect_on_next_request(self):
        self.assertEqual(self.post_card().status_code, 200)
        self.write_cards(make_card(TOKEN_HOST))
        self.assert_unavailable(self.post_card())
        self.assertEqual(self.post_card(TOKEN_HOST).status_code, 200)
        self.write_cards(make_card(TOKEN_HOST, enabled=False))
        self.assert_unavailable(self.post_card(TOKEN_HOST))

    def test_blank_or_missing_file_fails_closed(self):
        with override_settings(ACCESS_CARDS_FILE=""):
            self.assert_unavailable(self.post_card())
        self.config_path.unlink()
        self.assert_unavailable(self.post_card())

    def test_file_read_error_fails_closed(self):
        with override_settings(ACCESS_CARDS_FILE=self.config_path.parent):
            self.assert_unavailable(self.post_card())

    def test_malformed_or_oversized_config_fails_closed_without_echo(self):
        for config in (
            b"Synthetic-private-malformed", b"\xff",
            b" " * (credential_cards.MAX_CONFIG_BYTES + 1), b"[" * 2000 + b"]" * 2000,
        ):
            with self.subTest(length=len(config)):
                self.config_path.write_bytes(config)
                response = self.post_card()
                self.assert_unavailable(response)
                self.assertNotIn(b"Synthetic-private-malformed", response.content)

    def test_duplicate_digest_invalidates_entire_configuration(self):
        self.write_cards(make_card(), make_card(label="Another synthetic card"))
        self.assert_unavailable(self.post_card())

    def test_duplicate_json_keys_fail_closed(self):
        card = json.dumps(make_card())
        self.config_path.write_text('{"cards":[' + card + '],"cards":[]}', encoding="utf-8")
        self.assert_unavailable(self.post_card())
        duplicate_request = '{"token":"' + TOKEN_STUDY + '","token":"' + TOKEN_STUDY + '"}'
        self.assert_unavailable(self.client.post(
            "/api/access-card/", duplicate_request, content_type="application/json",
        ))

    def test_invalid_card_fields_fail_closed(self):
        invalid = [
            {"token_sha256": "not-a-digest"}, {"token_sha256": "A" * 64},
            {"enabled": "true"}, {"enabled": 1}, {"label": ""},
            {"expires_at": "2100-01-01T00:00:00"},
            {"expires_at": "2100-01-01T00:00:00+01:00"},
            {"expires_at": "2100-02-30T00:00:00Z"},
            {"accounts": []}, {"accounts": [{"username": "", "password": "Synthetic-only!"}]},
            {"accounts": [{"username": "Fixture", "password": ""}]},
            {"accounts": [{"username": "Fixture", "password": "bad\nvalue"}]},
            {"accounts": [{"username": "Fixture", "password": "Synthetic-only!", "role": "admin"}]},
            {"accounts": [{"username": "Fixture", "password": "a"}, {"username": "Fixture", "password": "b"}]},
            {"unrecognized": "Synthetic-extra-value"},
        ]
        for changes in invalid:
            with self.subTest(field=list(changes)):
                self.write_cards(make_card(**changes))
                self.assert_unavailable(self.post_card())

    def test_invalid_unmatched_card_also_invalidates_configuration(self):
        self.write_cards(make_card(), make_card(TOKEN_HOST, accounts=[]))
        self.assert_unavailable(self.post_card())

    def test_config_structure_and_card_count_are_bounded(self):
        for config in ([], {"cards": "wrong"}, {"cards": [], "extra": "wrong"},
                       {"cards": [make_card()] * (credential_cards.MAX_CARDS + 1)}):
            with self.subTest(config_type=type(config).__name__):
                self.config_path.write_text(json.dumps(config), encoding="utf-8")
                self.assert_unavailable(self.post_card())

    def test_account_count_and_text_lengths_are_bounded(self):
        for changes in (
            {"label": "x" * 101},
            {"accounts": [{"username": "x" * 151, "password": "Synthetic-only!"}]},
            {"accounts": [{"username": "Fixture", "password": "x" * 257}]},
            {"accounts": [{"username": f"Fixture{index}", "password": "Synthetic-only!"}
                          for index in range(credential_cards.MAX_ACCOUNTS_PER_CARD + 1)]},
        ):
            with self.subTest(field=list(changes)):
                self.write_cards(make_card(**changes))
                self.assert_unavailable(self.post_card())

    def test_malformed_request_and_tokens_fail_uniformly(self):
        requests = [b"not-json", b"\xff", b"[]", b"{}", b'{"token":null}',
                    json.dumps({"token": TOKEN_STUDY, "account": "other"}).encode(),
                    json.dumps({"token": "A" * 42}).encode(),
                    json.dumps({"token": "." * 43}).encode(),
                    json.dumps({"token": "\u00e9" * 43}).encode()]
        for payload in requests:
            with self.subTest(length=len(payload)):
                self.assert_unavailable(self.client.post(
                    "/api/access-card/", payload, content_type="application/json",
                ))

    def test_oversized_body_is_rejected(self):
        payload = json.dumps({"token": TOKEN_STUDY}) + " " * credential_cards.MAX_REQUEST_BYTES
        self.assert_unavailable(self.client.post(
            "/api/access-card/", payload, content_type="application/json",
        ))

    def test_form_and_other_content_types_are_not_accepted(self):
        self.assert_unavailable(self.client.post("/api/access-card/", {"token": TOKEN_STUDY}))
        self.assert_unavailable(self.client.post(
            "/api/access-card/", json.dumps({"token": TOKEN_STUDY}), content_type="text/plain",
        ))

    def test_wrong_methods_have_protected_headers(self):
        for method, endpoint in (("get", "/api/access-card/"), ("head", "/api/access-card/"),
                                 ("post", "/access-card/"), ("put", "/access-card/")):
            with self.subTest(method=method, endpoint=endpoint):
                response = getattr(self.client, method)(endpoint)
                self.assertEqual(response.status_code, 405)
                self.assert_protected(response)

    def test_csrf_missing_token_failure_is_protected(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post_card(client=client)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"StudyFixture01", response.content)
        self.assert_protected(response)

    def test_same_origin_csrf_request_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/access-card/")
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = self.post_card(
            client=client, HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(response.status_code, 200)
        self.assert_protected(response)

    def test_foreign_origin_is_rejected_even_with_correct_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/access-card/")
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = self.post_card(
            client=client, HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="https://foreign.invalid",
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"StudyFixture01", response.content)
        self.assert_protected(response)

    def test_unknown_sensitive_paths_and_https_redirects_remain_protected(self):
        for endpoint in ("/access-card/nonexistent/", "/api/access-card/nonexistent/"):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 404)
            self.assert_protected(response)
        with override_settings(SECURE_SSL_REDIRECT=True):
            response = Client().get("/access-card/")
            self.assertEqual(response.status_code, 301)
            self.assert_protected(response)

    def test_bearer_input_and_plaintext_are_not_reflected_in_invalid_errors(self):
        self.write_cards(make_card(enabled=False))
        response = self.post_card()
        for secret in (TOKEN_STUDY, "StudyFixture01", "Synthetic-study-only!"):
            self.assertNotIn(secret.encode(), response.content)
        self.assert_unavailable(response)
