from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


class JoinForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if username.casefold() in (settings.CREATOR_USERNAME.casefold(), settings.CREATOR_DISPLAY_NAME.casefold(), "admin"):
            raise forms.ValidationError("Choose another username. This name is reserved.")
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username
