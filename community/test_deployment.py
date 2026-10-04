"""Check deployment settings without connecting to a database or using local secrets.

Run with a Python environment containing requirements.txt:
    python -m unittest community.test_deployment

The LocalSettingsTests class also runs with the bundled preview Python.
"""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parent.parent
TEST_SECRET = "deployment-test-key-with-no-real-credentials-" * 3
TEST_DATABASE_URL = "postgresql://test_user:test_password@127.0.0.1:5432/test_database"
RENDER_HOST = "deployment-test.onrender.com"
PRODUCTION_ENV = {
    "JAY_ENV": "production",
    "SECRET_KEY": TEST_SECRET,
    "DATABASE_URL": TEST_DATABASE_URL,
    "RENDER_EXTERNAL_HOSTNAME": RENDER_HOST,
}

# Only return the settings needed for these assertions. In particular, never
# return the secret key or database username/password/URL in subprocess output.
SETTINGS_PROBE = r'''
import importlib.abc
import json
from pathlib import Path
import runpy
import sys

if sys.argv[2] == "local":
    class RejectProductionDependencies(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"dj_database_url", "whitenoise"}:
                raise ImportError("Local preview imported a production-only dependency")
    sys.meta_path.insert(0, RejectProductionDependencies())

try:
    configuration = runpy.run_path(sys.argv[1])
except Exception as error:
    print(json.dumps({"error_type": type(error).__name__, "error": str(error)}))
    raise SystemExit(1)

database = configuration["DATABASES"]["default"]
selected = {
    "DEBUG": configuration["DEBUG"],
    "ALLOWED_HOSTS": configuration["ALLOWED_HOSTS"],
    "CSRF_TRUSTED_ORIGINS": configuration.get("CSRF_TRUSTED_ORIGINS", []),
    "SESSION_COOKIE_SECURE": configuration.get("SESSION_COOKIE_SECURE", False),
    "CSRF_COOKIE_SECURE": configuration.get("CSRF_COOKIE_SECURE", False),
    "SECURE_SSL_REDIRECT": configuration.get("SECURE_SSL_REDIRECT", False),
    "SECURE_PROXY_SSL_HEADER": configuration.get("SECURE_PROXY_SSL_HEADER"),
    "SECURE_HSTS_SECONDS": configuration.get("SECURE_HSTS_SECONDS", 0),
    "MIDDLEWARE": configuration["MIDDLEWARE"],
    "STORAGES": configuration.get("STORAGES", {}),
    "STATIC_ROOT": str(configuration.get("STATIC_ROOT", "")),
    "BASE_DIR": str(configuration["BASE_DIR"]),
    "DATABASE_ENGINE": database["ENGINE"],
    "DATABASE_NAME": str(database["NAME"]),
    "DATABASE_SSLMODE": database.get("OPTIONS", {}).get("sslmode"),
    "DATABASE_CONN_MAX_AGE": database.get("CONN_MAX_AGE"),
    "DATABASE_CONN_HEALTH_CHECKS": database.get("CONN_HEALTH_CHECKS"),
}
print(json.dumps(selected))
'''


class SettingsProbeMixin:
    def probe_settings(self, overrides, *, local=False):
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith(("JAY_", "RENDER")) or name in {
                "SECRET_KEY", "DATABASE_URL", "DJANGO_SETTINGS_MODULE",
            }:
                environment.pop(name)
        environment.update(overrides)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        with tempfile.TemporaryDirectory(prefix="jay-deployment-test-") as directory:
            temporary_project = Path(directory)
            settings_path = temporary_project / "jayproject" / "settings.py"
            settings_path.parent.mkdir()
            shutil.copyfile(PROJECT_DIR / "jayproject" / "settings.py", settings_path)
            private_path = temporary_project / "private"
            private_path.mkdir()
            (private_path / "secret.key").write_text(TEST_SECRET, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", "-c", SETTINGS_PROBE,
                 str(settings_path), "local" if local else "production"],
                cwd=temporary_project,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertTrue(result.stdout.strip(), result.stderr)
            snapshot = json.loads(result.stdout)
            return result.returncode, snapshot

    def assert_settings_load(self, overrides, *, local=False):
        returncode, settings = self.probe_settings(overrides, local=local)
        self.assertEqual(returncode, 0, settings)
        return settings


class LocalSettingsTests(SettingsProbeMixin, unittest.TestCase):
    def test_local_preview_needs_no_production_dependencies_or_hosted_services(self):
        settings = self.assert_settings_load({}, local=True)
        self.assertFalse(settings["DEBUG"])
        self.assertEqual(set(settings["ALLOWED_HOSTS"]), {"localhost", "127.0.0.1", "[::1]"})
        self.assertEqual(settings["DATABASE_ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(
            Path(settings["DATABASE_NAME"]),
            Path(settings["BASE_DIR"]) / "private" / "db.sqlite3",
        )
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertFalse(settings[name], name)
        self.assertNotIn("whitenoise.middleware.WhiteNoiseMiddleware", settings["MIDDLEWARE"])


@unittest.skipUnless(
    importlib.util.find_spec("dj_database_url") is not None,
    "Production dependencies are unavailable; run these checks with .venv Python.",
)
class ProductionSettingsTests(SettingsProbeMixin, unittest.TestCase):
    def test_unknown_environment_is_rejected_instead_of_starting_local_mode(self):
        returncode, result = self.probe_settings({"JAY_ENV": "prodution"})
        self.assertNotEqual(returncode, 0)
        self.assertIn("JAY_ENV", result["error"])

    def test_explicit_production_requires_environment_secret_key(self):
        environment = dict(PRODUCTION_ENV)
        environment.pop("SECRET_KEY")
        returncode, result = self.probe_settings(environment)
        self.assertNotEqual(returncode, 0)
        self.assertIn("SECRET_KEY", result["error"])

    def test_weak_or_default_production_secret_keys_are_rejected(self):
        for key in ("", "short", "x" * 100, "django-insecure-" + TEST_SECRET):
            with self.subTest(length=len(key)):
                returncode, result = self.probe_settings(dict(PRODUCTION_ENV, SECRET_KEY=key))
                self.assertNotEqual(returncode, 0)
                self.assertIn("SECRET_KEY", result["error"])

    def test_explicit_production_requires_postgres_database_url(self):
        for database_url in (None, "", "sqlite:///db.sqlite3", "mysql://test@localhost/test"):
            with self.subTest(database_url=database_url):
                environment = dict(PRODUCTION_ENV)
                if database_url is None:
                    environment.pop("DATABASE_URL")
                else:
                    environment["DATABASE_URL"] = database_url
                returncode, result = self.probe_settings(environment)
                self.assertNotEqual(returncode, 0)
                self.assertIn("DATABASE_URL", result["error"])

    def test_postgres_url_schemes_configure_postgres_without_a_connection(self):
        for scheme in ("postgres", "postgresql"):
            with self.subTest(scheme=scheme):
                environment = dict(PRODUCTION_ENV)
                environment["DATABASE_URL"] = TEST_DATABASE_URL.replace("postgresql:", scheme + ":", 1)
                settings = self.assert_settings_load(environment)
                self.assertEqual(settings["DATABASE_ENGINE"], "django.db.backends.postgresql")
                self.assertEqual(settings["DATABASE_NAME"], "test_database")
                self.assertEqual(settings["DATABASE_SSLMODE"], "require")
                self.assertEqual(settings["DATABASE_CONN_MAX_AGE"], 60)
                self.assertTrue(settings["DATABASE_CONN_HEALTH_CHECKS"])

    def test_malformed_postgres_urls_fail_without_echoing_credentials(self):
        password_marker = "do-not-echo-url-password"
        urls = {
            "missing hostname": f"postgresql://test_user:{password_marker}@/test_database",
            "missing database": f"postgresql://test_user:{password_marker}@127.0.0.1:5432",
            "invalid port": f"postgresql://test_user:{password_marker}@127.0.0.1:invalid/test_database",
        }
        for problem, database_url in urls.items():
            with self.subTest(problem=problem):
                returncode, result = self.probe_settings(dict(PRODUCTION_ENV, DATABASE_URL=database_url))
                self.assertNotEqual(returncode, 0)
                self.assertIn("DATABASE_URL", result["error"])
                self.assertNotIn(password_marker, result["error"])
                self.assertNotIn(database_url, result["error"])

    def test_production_hosts_are_explicit_and_https_origins_are_trusted(self):
        settings = self.assert_settings_load(PRODUCTION_ENV)
        self.assertEqual(set(settings["ALLOWED_HOSTS"]), {
            RENDER_HOST,
            "tradingwithjay.online", "www.tradingwithjay.online",
        })
        origins = set(settings["CSRF_TRUSTED_ORIGINS"])
        self.assertTrue({
            "https://" + RENDER_HOST,
            "https://tradingwithjay.online",
            "https://www.tradingwithjay.online",
        }.issubset(origins))
        self.assertTrue(all(origin.startswith("https://") and "*" not in origin for origin in origins))

    def test_production_without_render_hostname_still_loads_for_custom_domain(self):
        environment = dict(PRODUCTION_ENV)
        environment.pop("RENDER_EXTERNAL_HOSTNAME")
        settings = self.assert_settings_load(environment)
        self.assertIn("tradingwithjay.online", settings["ALLOWED_HOSTS"])
        self.assertNotIn(RENDER_HOST, settings["ALLOWED_HOSTS"])

    def test_invalid_render_hostname_fails_before_serving_requests(self):
        for hostname in ("https://" + RENDER_HOST, RENDER_HOST + "/path", "*.onrender.com", RENDER_HOST + ":443"):
            with self.subTest(hostname=hostname):
                environment = dict(PRODUCTION_ENV, RENDER_EXTERNAL_HOSTNAME=hostname)
                returncode, result = self.probe_settings(environment)
                self.assertNotEqual(returncode, 0)
                self.assertIn("RENDER_EXTERNAL_HOSTNAME", result["error"])

    def test_production_protects_sign_in_and_serves_collected_static_files(self):
        settings = self.assert_settings_load(PRODUCTION_ENV)
        self.assertFalse(settings["DEBUG"])
        for name in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertTrue(settings[name], name)
        self.assertEqual(settings["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertGreater(settings["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(Path(settings["STATIC_ROOT"]), Path(settings["BASE_DIR"]) / "staticfiles")
        self.assertEqual(
            settings["STORAGES"]["staticfiles"]["BACKEND"],
            "whitenoise.storage.CompressedStaticFilesStorage",
        )
        middleware = settings["MIDDLEWARE"]
        self.assertEqual(
            middleware.index("whitenoise.middleware.WhiteNoiseMiddleware"),
            middleware.index("django.middleware.security.SecurityMiddleware") + 1,
        )

    def test_render_environment_activates_production_without_jay_env(self):
        environment = dict(PRODUCTION_ENV)
        environment.pop("JAY_ENV")
        environment["RENDER"] = "true"
        settings = self.assert_settings_load(environment)
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])
        self.assertEqual(settings["DATABASE_ENGINE"], "django.db.backends.postgresql")
        environment.pop("SECRET_KEY")
        returncode, result = self.probe_settings(environment)
        self.assertNotEqual(returncode, 0)
        self.assertIn("SECRET_KEY", result["error"])


if __name__ == "__main__":
    unittest.main()
