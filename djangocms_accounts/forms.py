# -*- coding: utf-8 -*-
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import ugettext_lazy as _
from django import forms


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label=_("Email"), max_length=100)



class ChangePasswordForm(forms.Form):
    password_current = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(render_value=False)
    )
    password_new = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(render_value=False)
    )
    password_new_confirm = forms.CharField(
        label=_("New Password (again)"),
        widget=forms.PasswordInput(render_value=False)
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(ChangePasswordForm, self).__init__(*args, **kwargs)

    def clean_password_current(self):
        if not self.user.check_password(self.cleaned_data.get("password_current")):
            raise forms.ValidationError(_("Please type your current password."))
        return self.cleaned_data["password_current"]

    def clean_password_new_confirm(self):
        if "password_new" in self.cleaned_data and "password_new_confirm" in self.cleaned_data:
            if self.cleaned_data["password_new"] != self.cleaned_data["password_new_confirm"]:
                raise forms.ValidationError(_("You must type the same password each time."))
        return self.cleaned_data["password_new_confirm"]

    def save(self, user):
        user.set_password(self.cleaned_data["password_new"])
        user.save()