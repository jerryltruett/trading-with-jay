import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Broadcast, ChatMessage, Signal
from .views import library_lessons


class CommunityPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jay = User.objects.create_user(settings.CREATOR_USERNAME, password="Preview-host-passphrase-293")
        cls.viewer = User.objects.create_user("MemberA", password="Preview-viewer-passphrase-293")
        cls.other = User.objects.create_user("MemberB", password="Preview-other-passphrase-293")
        cls.admin = User.objects.create_superuser("Admin", "", "Preview-admin-passphrase-293")

    def post(self, route, data):
        return self.client.post(reverse(route), json.dumps(data), content_type="application/json")

    def start(self):
        self.client.force_login(self.jay)
        response = self.post("live_api", {"action": "start", "title": "Reading a chart together"})
        self.assertEqual(response.status_code, 200)
        return response.json()["session_id"]

    def join_peer(self, user, session, peer=None):
        peer = peer or str(uuid.uuid4())
        self.client.force_login(user)
        response = self.post("signals_api", {"session_id": session, "sender": peer,
                                             "recipient": "host", "kind": "join", "payload": {}})
        self.assertEqual(response.status_code, 201)
        return peer

    def test_live_room_requires_sign_in_and_remains_available_to_members(self):
        response = self.client.get(reverse("live"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('live')}",
                             fetch_redirect_response=False)
        for user in (self.viewer, self.jay):
            with self.subTest(username=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("live"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "live.html")
                self.assertEqual(response.context["can_host"], user == self.jay)

    def test_live_metadata_is_private_even_during_an_active_session(self):
        session = self.start()
        self.client.logout()
        response = self.client.get(reverse("live_api"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {"error"})
        self.assertNotContains(response, session, status_code=401)
        home = self.client.get(reverse("home"))
        self.assertIsNone(home.context["current_broadcast"])
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("live_api"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["active"])
        self.assertEqual(response.json()["session_id"], session)
        self.assertEqual(response.json()["title"], "Reading a chart together")
        self.assertFalse(response.json()["is_host"])

    def test_public_pages_do_not_offer_a_stream_entry_point(self):
        for route in ("home", "login", "join"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, f'href="{reverse("live")}"')
                self.assertNotContains(response, "data-live-label")

    def test_stream_entry_point_is_in_the_signed_in_community(self):
        self.client.force_login(self.viewer)
        home = self.client.get(reverse("home"))
        self.assertNotContains(home, f'href="{reverse("live")}"')
        self.assertNotContains(home, "data-live-label")
        members = self.client.get(reverse("members"))
        self.assertContains(members, f'href="{reverse("live")}"')

    def test_signed_in_members_can_read_offline_status(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("live_api"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["active"])
        self.assertFalse(response.json()["is_host"])

    @override_settings(CREATOR_USERNAME="HostLogin42", CREATOR_DISPLAY_NAME="Jay")
    def test_creator_login_identity_stays_separate_from_display_name(self):
        creator = get_user_model().objects.create_user("HostLogin42", password="Preview-host-passphrase-293")
        self.client.force_login(creator)
        members = self.client.get(reverse("members"))
        self.assertEqual(members.status_code, 200)
        self.assertTrue(members.context["can_host"])
        self.assertEqual(members.context["current_user_display_name"], "Jay")
        self.assertContains(members, f'class="member-link" href="{reverse("members")}">{creator.username}</a>')
        offline = self.client.get(reverse("live_api"))
        self.assertEqual(offline.status_code, 200)
        self.assertEqual(offline.json()["host_name"], "Jay")
        self.assertEqual(self.post("live_api", {"action": "start"}).status_code, 200)
        active = self.client.get(reverse("live_api"))
        self.assertTrue(active.json()["active"])
        self.assertEqual(active.json()["host_name"], "Jay")

    def test_only_creator_and_admin_can_start_or_stop(self):
        self.assertEqual(self.post("live_api", {"action": "start"}).status_code, 401)
        self.client.force_login(self.viewer)
        self.assertEqual(self.post("live_api", {"action": "start"}).status_code, 403)
        self.start()
        self.client.force_login(self.viewer)
        self.assertEqual(self.post("live_api", {"action": "stop"}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.post("live_api", {"action": "stop"}).status_code, 200)

    def test_one_session_and_title_bounds(self):
        session = self.start()
        response = self.post("live_api", {"action": "start"})
        self.assertEqual(response.json()["session_id"], session)
        self.assertEqual(Broadcast.objects.filter(active=True).count(), 1)
        self.assertEqual(self.post("live_api", {"action": "title", "title": "x" * 121}).status_code, 400)
        self.assertEqual(self.post("live_api", {"action": "title", "title": "A new topic"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("live_api")).json()["title"], "A new topic")

    def test_csrf_required_for_live_mutations(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.jay)
        response = protected.post(reverse("live_api"), json.dumps({"action": "start"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_abandoned_host_session_expires(self):
        self.start()
        Broadcast.objects.update(host_last_seen=timezone.now() - timedelta(seconds=121))
        self.client.force_login(self.viewer)
        self.assertFalse(self.client.get(reverse("live_api")).json()["active"])
        self.assertFalse(Broadcast.objects.get().active)

    def test_registration_creates_member_and_rejects_reserved_names(self):
        response = self.client.post(reverse("join"), {"username": "FreshMember",
            "password1": "A-unique-member-passphrase-198", "password2": "A-unique-member-passphrase-198"})
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="FreshMember")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.client.logout()
        reserved_username = settings.CREATOR_USERNAME.swapcase()
        response = self.client.post(reverse("join"), {"username": reserved_username,
            "password1": "A-unique-member-passphrase-198", "password2": "A-unique-member-passphrase-198"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username=reserved_username).exists())

    def test_login_next_cannot_redirect_off_site(self):
        response = self.client.post(reverse("login"), {"username": "MemberA",
            "password": "Preview-viewer-passphrase-293", "next": "https://untrusted.invalid/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("members"))

    def test_members_library_and_chat_require_sign_in(self):
        self.assertEqual(self.client.get(reverse("members")).status_code, 302)
        self.assertEqual(self.client.get(reverse("library")).status_code, 302)
        self.assertEqual(self.client.get(reverse("chat_api")).status_code, 401)
        self.assertEqual(self.post("chat_api", {"body": "hello"}).status_code, 401)

    def test_live_chat_is_bounded_and_separate_from_lounge(self):
        session = self.start()
        self.client.force_login(self.viewer)
        self.assertEqual(self.post("chat_api", {"session_id": session, "body": " "}).status_code, 400)
        self.assertEqual(self.post("chat_api", {"session_id": session, "body": "x" * 1001}).status_code, 400)
        self.assertEqual(self.post("chat_api", {"session_id": session, "body": ["bad"]}).status_code, 400)
        self.assertEqual(self.post("chat_api", {"session_id": session, "body": "Live question"}).status_code, 201)
        self.assertEqual(self.post("chat_api", {"room": "lounge", "body": "Community question"}).status_code, 201)
        live = self.client.get(reverse("chat_api"), {"session_id": session}).json()
        self.assertEqual([message["body"] for message in live["messages"]], ["Live question"])
        self.assertEqual(live["session_id"], session)
        lounge = self.client.get(reverse("chat_api"), {"room": "lounge"}).json()
        self.assertEqual([message["body"] for message in lounge["messages"]], ["Community question"])

    def test_new_live_session_hides_old_chat_and_signals(self):
        old_session = self.start()
        self.post("chat_api", {"session_id": old_session, "body": "Old live message"})
        old_peer = self.join_peer(self.viewer, old_session)
        self.client.force_login(self.jay)
        self.post("live_api", {"action": "stop"})
        new_session = self.start()
        self.assertNotEqual(old_session, new_session)
        self.assertEqual(self.client.get(reverse("chat_api"), {"session_id": new_session}).json()["messages"], [])
        self.client.force_login(self.viewer)
        stale = self.post("signals_api", {"session_id": old_session, "sender": old_peer,
                                           "recipient": "host", "kind": "join", "payload": {}})
        self.assertEqual(stale.status_code, 409)

    def test_live_chat_requires_matching_session_for_get_and_post(self):
        first_session = self.start()
        self.assertEqual(self.post("chat_api", {"body": "No session"}).status_code, 409)
        self.assertEqual(self.client.get(reverse("chat_api")).status_code, 409)
        self.assertEqual(self.post("chat_api", {"session_id": first_session, "body": "First room"}).status_code, 201)
        self.post("live_api", {"action": "stop"})
        self.assertEqual(self.client.get(reverse("chat_api"), {"session_id": first_session}).status_code, 409)
        second_session = self.start()
        self.assertEqual(self.post("chat_api", {"session_id": first_session, "body": "Stale tab"}).status_code, 409)
        self.assertEqual(self.client.get(reverse("chat_api"), {"session_id": first_session}).status_code, 409)
        valid = self.post("chat_api", {"session_id": second_session, "body": "Second room"})
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(valid.json()["session_id"], second_session)
        second_chat = self.client.get(reverse("chat_api"), {"session_id": second_session}).json()
        self.assertEqual([item["body"] for item in second_chat["messages"]], ["Second room"])
        self.assertFalse(ChatMessage.objects.filter(body="Stale tab").exists())

    def test_moderation_is_creator_only(self):
        self.client.force_login(self.viewer)
        posted = self.post("chat_api", {"room": "lounge", "body": "A message"}).json()["message"]["id"]
        self.assertEqual(self.post("chat_api", {"room": "lounge", "action": "delete", "id": posted}).status_code, 403)
        self.client.force_login(self.jay)
        self.assertTrue(self.post("chat_api", {"room": "lounge", "action": "delete", "id": posted}).json()["deleted"])
        self.assertFalse(ChatMessage.objects.filter(pk=posted).exists())

    def test_viewer_cannot_impersonate_host_or_another_peer(self):
        session = self.start()
        peer = self.join_peer(self.viewer, session)
        self.client.force_login(self.other)
        stolen = self.post("signals_api", {"session_id": session, "sender": peer,
                                            "recipient": "host", "kind": "join", "payload": {}})
        self.assertEqual(stolen.status_code, 403)
        host = self.post("signals_api", {"session_id": session, "sender": "host", "recipient": peer,
                                          "kind": "offer", "payload": {"type": "offer", "sdp": "v=0"}})
        self.assertEqual(host.status_code, 403)
        self.assertEqual(self.client.get(reverse("signals_api"), {"peer": "host"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("signals_api"), {"peer": peer}).status_code, 403)

    def test_signals_are_only_between_host_and_owned_viewer(self):
        session = self.start()
        first = self.join_peer(self.viewer, session)
        second = self.join_peer(self.other, session)
        self.client.force_login(self.viewer)
        self.assertEqual(self.post("signals_api", {"session_id": session, "sender": first,
            "recipient": second, "kind": "ice", "payload": {"candidate": "candidate:one"}}).status_code, 403)
        self.client.force_login(self.jay)
        offer = self.post("signals_api", {"session_id": session, "sender": "host", "recipient": first,
            "kind": "offer", "payload": {"type": "offer", "sdp": "v=0"}})
        self.assertEqual(offer.status_code, 201)
        self.client.force_login(self.viewer)
        received = self.client.get(reverse("signals_api"), {"peer": first}).json()["signals"]
        self.assertEqual([item["kind"] for item in received], ["offer"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("signals_api"), {"peer": second}).json()["signals"], [])
        self.assertEqual(Signal.objects.filter(kind="offer").count(), 1)

    def test_signal_payloads_are_validated(self):
        session = self.start()
        peer = self.join_peer(self.viewer, session)
        bad = self.post("signals_api", {"session_id": session, "sender": peer, "recipient": "host",
            "kind": "answer", "payload": {"type": "offer", "sdp": "v=0"}})
        self.assertEqual(bad.status_code, 400)
        large = self.post("signals_api", {"session_id": session, "sender": peer, "recipient": "host",
            "kind": "ice", "payload": {"candidate": "x" * 4097}})
        self.assertEqual(large.status_code, 400)
        self.assertEqual(self.client.get(reverse("signals_api"), {"peer": peer, "after": "bad"}).status_code, 400)

    def test_signed_in_sample_media_and_range_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "media").mkdir()
            (root / "media" / "sample.mp4").write_bytes(b"0123456789")
            with override_settings(PROTECTED_DIR=root):
                self.assertEqual(self.client.get("/media/sample.mp4").status_code, 302)
                self.client.force_login(self.viewer)
                response = self.client.get("/media/sample.mp4", HTTP_RANGE="bytes=2-5")
                try:
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(b"".join(response.streaming_content), b"2345")
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                finally:
                    response.close()
                self.assertEqual(self.client.get("/media/secret.key").status_code, 404)

    def test_library_notes_follow_each_sample_lesson(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "courses.json").write_text(json.dumps([{
                "id": "stocks", "title": "Foundations", "lesson": "Ownership",
                "duration": 176, "description": "The basics", "takeaways": ["A share is ownership"],
                "extraLessons": [{"number": 2, "title": "Costs", "duration": 176,
                                  "takeaways": ["Costs affect returns"]}],
            }]), encoding="utf-8")
            with override_settings(PROTECTED_DIR=root):
                lessons = library_lessons()
            self.assertEqual(lessons[0]["takeaways"], ["A share is ownership"])
            self.assertEqual(lessons[1]["takeaways"], ["Costs affect returns"])

    def test_members_feed_renders_chronologically(self):
        ChatMessage.objects.create(room="lounge", user=self.viewer, author_name="MemberA", body="First")
        ChatMessage.objects.create(room="lounge", user=self.other, author_name="MemberB", body="Second")
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("members"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([post.body for post in response.context["posts"]], ["First", "Second"])
