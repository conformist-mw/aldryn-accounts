# -*- coding: utf-8 -*-
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.models import User
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from six.moves.urllib.parse import urlencode

from .emails import EmailSender
from .models import EmailAddress, EmailConfirmation, UserSettings


def get_user_email(user, form_email):
    """
    Search for confirmed emails with respect to form_email.
    Returns string, email address
    """
    # check if there is confirmed emails for this user
    confirmed_emails = EmailAddress.objects.get_for_user(
        user).order_by('is_primary')
    if not confirmed_emails:
        # if there is no confirmed emails - don't return anything
        return None
    email_instance = confirmed_emails[0]
    # check if entered email is confirmed
    matching_email = confirmed_emails.filter(email=form_email)
    if matching_email:
        email_instance = matching_email.get()
    # if entered email is not among the confirmed - user first
    # confirmed email
    return email_instance.email


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label=_("E-Mail"), max_length=255)
    remember_me = forms.BooleanField(
        label=_('Remember me?'),
        initial=True,
        widget=forms.CheckboxInput(),
        required=False,
    )


class PasswordResetForm(forms.Form):
    password = forms.CharField(
        label=_('New password'),
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(PasswordResetForm, self).__init__(*args, **kwargs)

    def save(self):
        self.user.set_password(self.cleaned_data['password'])
        User.objects.filter(pk=self.user.pk).update(
            password=self.user.password,
        )


class ChangePasswordForm(forms.Form):
    password_current = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(render_value=False)
    )
    password_new = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(render_value=False)
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(ChangePasswordForm, self).__init__(*args, **kwargs)

    def clean_password_current(self):
        if not self.user.check_password(self.cleaned_data.get("password_current")):
            raise forms.ValidationError(_("Please type your current password."))
        return self.cleaned_data["password_current"]

    def save(self, user):
        user.set_password(self.cleaned_data["password_new"])
        user.save()


class CreatePasswordForm(ChangePasswordForm):
    def __init__(self, *args, **kwargs):
        super(CreatePasswordForm, self).__init__(*args, **kwargs)
        del self.fields['password_current']


class EmailForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"), required=True)


class ProfileEmailForm(EmailForm):

    def clean_email(self):
        email = self.cleaned_data.get('email')
        verified_qs = EmailAddress.objects.filter(email__iexact=email)
        if verified_qs.exists():
            raise forms.ValidationError(_("This E-Mail address is already in use."))
        return email


class SignupForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"), widget=forms.TextInput, required=True)
    code = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.HiddenInput()
    )
    error_messages = {
        'email_exists': _("A user is already registered with this E-Mail address.")
    }

    def clean_email(self):
        value = self.cleaned_data["email"]
        unverified_qs = EmailConfirmation.objects.filter(email__iexact=value)
        # check for incomplete signups
        if unverified_qs.exists():
            resend_url = reverse('aldryn_accounts:accounts_signup_email_resend_confirmation')
            resend_url += '?' + urlencode({'email': value})
            body = render_to_string(
                'aldryn_accounts/inc/email_already_in_the_verification_phase.html',
                {'resend_url': resend_url}
            )
            raise forms.ValidationError(body)
        # check for complete signups
        verified_qs = EmailAddress.objects.filter(email__iexact=value)
        if verified_qs.exists():
            raise forms.ValidationError(self.error_messages['email_exists'])
        # check for other users (e.g aldryn-sso)
        user_qs = User.objects.filter(email__iexact=value)
        if user_qs.exists():
            raise forms.ValidationError(self.error_messages['email_exists'])
        return value


class SignupEmailResendConfirmationForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"), required=True, widget=forms.HiddenInput())

    def clean_email(self):
        email = self.cleaned_data["email"]
        verified_qs = EmailAddress.objects.filter(email__iexact=email)
        if verified_qs.exists():
            raise forms.ValidationError(_("A user is already registered with this E-Mail address."))
        return email


class PasswordRecoveryResetForm(DjangoPasswordResetForm):
    def get_users(self, email):
        """
        Given an email, return matching user(s) who should receive a reset.

        Removes users without a usable password (set e.g. in admin)
        and no social auth
        """
        users = get_user_model()._default_manager.filter(
            email__iexact=email, is_active=True
        )

        def is_active_user(user):
            if user.has_usable_password():
                # mimic super class
                return True

            if settings.ALDRYN_ACCOUNTS_ENABLE_PYTHON_SOCIAL_AUTH:
                try:
                    # check for connected social accounts
                    return user.social_auth.exists()
                except AttributeError:  # social auth not configured
                    pass

            return False

        return list(filter(is_active_user, users))

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        return EmailSender.send_password_recovery_reset(
            subject_template_name=subject_template_name,
            email_template_name=email_template_name,
            context=context,
            from_email=from_email,
            to_email=to_email,
            html_email_template_name=None,
        )


class UserSettingsForm(forms.ModelForm):
    first_name = forms.CharField(label=_("First name"), required=True)
    last_name = forms.CharField(label=_("Last name"), required=True)

    class Meta:
        model = UserSettings
        fields = ('birth_date', 'preferred_language', 'timezone',
                  'location_name', 'location_latitude', 'location_longitude', 'profile_image')
        widgets = {
            'location_latitude': forms.HiddenInput(),
            'location_longitude': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(UserSettingsForm, self).__init__(*args, **kwargs)
        user = self.instance.user
        self.fields['first_name'].initial = user.first_name
        self.fields['last_name'].initial = user.last_name

    def save(self):
        first_name = self.cleaned_data['first_name']
        last_name = self.cleaned_data['last_name']
        user = self.instance.user
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        return super(UserSettingsForm, self).save()
