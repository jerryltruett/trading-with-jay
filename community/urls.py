from django.contrib.auth.views import LogoutView
from django.urls import path
from . import credential_cards, views

urlpatterns = [
    path("access-card/", credential_cards.access_card, name="access_card"),
    path("api/access-card/", credential_cards.access_card_api, name="access_card_api"),
    path("", views.home, name="home"),
    path("live/", views.live, name="live"),
    path("login/", views.JayLoginView.as_view(), name="login"),
    path("join/", views.join, name="join"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("members/", views.members, name="members"),
    path("library/", views.library, name="library"),
    path("media/<str:asset>", views.protected_media, name="protected_media"),
    path("api/live/", views.live_api, name="live_api"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/signals/", views.signals_api, name="signals_api"),
    path("static/<path:asset>", views.static_asset, name="static_asset"),
]
