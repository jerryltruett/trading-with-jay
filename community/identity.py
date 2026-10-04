"""Keep the creator's public name separate from the sign-in username."""
from django.conf import settings


def display_name(user):
    if not user or not user.is_authenticated:
        return ""
    if user.username.casefold() == settings.CREATOR_USERNAME.casefold():
        return settings.CREATOR_DISPLAY_NAME
    return user.username


def account_identity(request):
    return {"current_user_display_name": display_name(request.user)}
