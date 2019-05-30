# -*- coding: utf-8 -*-
from .compatibility import is_authenticated, is_anonymous

try:
    from urllib.parse import urlencode, unquote
except ImportError:
    from urllib import urlencode, unquote  # Python 2

try:
    from django.contrib.sites.shortcuts import get_current_site
    from django.contrib.sites.requests import RequestSite
except ImportError:
    # Django 1.6
    from django.contrib.sites.models import get_current_site, RequestSite

import class_based_auth_views.views
from class_based_auth_views.utils import default_redirect
from dj.chain import chain
from django import forms
from django.contrib import auth, messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
try:
    from django.urls import reverse
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from aldryn_accounts.exceptions import EmailAlreadyVerified, VerificationKeyExpired
from . import utils
from .conf import settings
from .context_processors import empty_login_and_signup_forms
from .emails import EmailSender
from .forms import (ChangePasswordForm, CreatePasswordForm, EmailAuthenticationForm, PasswordRecoveryResetForm,
                    ProfileEmailForm, SignupEmailResendConfirmationForm, SignupForm, UserSettingsForm)
from .models import EmailAddress, EmailConfirmation, SignupCode, UserSettings
from .signals import password_changed, user_sign_up_attempt, user_signed_up
from .view_mixins import OnlyOwnedObjectsMixin


class SignupView(FormView):
    template_name = "aldryn_accounts/signup.html"
    template_name_signup_closed = "aldryn_accounts/signup_closed.html"
    form_class = SignupForm
    form_kwargs = {}
    redirect_field_name = "next"
    messages = {
        "email_confirmation_sent": {
            "level": messages.INFO,
            "text": _("Confirmation E-Mail sent to %(email)s.")
        },
        "logged_in": {
            "level": messages.SUCCESS,
            "text": _("Logged in as %(user)s.")
        },
        "invalid_signup_code": {
            "level": messages.WARNING,
            "text": _("The code %(code)s is invalid.")
        }
    }

    def __init__(self, *args, **kwargs):
        self.created_user = None
        kwargs["signup_code"] = None
        super(SignupView, self).__init__(*args, **kwargs)

    def get(self, *args, **kwargs):
        if is_authenticated(self.request.user):
            return redirect(default_redirect(self.request, settings.ALDRYN_ACCOUNTS_LOGIN_REDIRECT_URL))
        if not self.is_open():
            return self.closed()
        return super(SignupView, self).get(*args, **kwargs)

    def post(self, *args, **kwargs):
        if not self.is_open():
            return self.closed()
        return super(SignupView, self).post(*args, **kwargs)

    def get_initial(self):
        initial = super(SignupView, self).get_initial()
        if self.signup_code:
            initial["code"] = self.signup_code.code
            if self.signup_code.email:
                initial["email"] = self.signup_code.email
        return initial

    def get_context_data(self, **kwargs):
        ctx = super(SignupView, self).get_context_data(**kwargs)
        redirect_field_name = self.get_redirect_field_name()
        # adds the empty login and signup forms to the context, so that
        # the shared login/signup view works even if the context processor
        # was not added globally
        ctx.update(empty_login_and_signup_forms(self.request))
        ctx.update({
            "redirect_field_name": redirect_field_name,
            "redirect_field_value": self.request.GET.get(redirect_field_name),
        })
        return ctx

    def get_form_kwargs(self):
        kwargs = super(SignupView, self).get_form_kwargs()
        kwargs.update(self.form_kwargs)
        return kwargs

    def form_invalid(self, form):
        user_sign_up_attempt.send(
            sender=SignupForm,
            email=form.data.get("email"),
            result=form.is_valid()
        )
        return self.render_to_response(self.get_context_data(form=form, signup_form=form))

    def form_valid(self, form):
        email_is_trusted = False
        email = form.cleaned_data.get('email')
        self.created_user = self.create_user(form)
        if self.signup_code:
            self.signup_code.use(self.created_user)
            if self.signup_code.email and self.created_user.email == self.signup_code.email:
                email_is_trusted = True
        if email_is_trusted:
            email_address = EmailAddress.objects.add_email(self.created_user, self.created_user.email)
        else:
            # send a verification email
            email_address_verification = EmailConfirmation.objects.request(self.created_user, email=email, send=True)
            if not settings.ALDRYN_ACCOUNTS_ENABLE_NOTIFICATIONS:
                if self.messages.get("email_confirmation_sent"):
                    messages.add_message(
                        self.request,
                        self.messages["email_confirmation_sent"]["level"],
                        self.messages["email_confirmation_sent"]["text"] % {
                            "email": form.cleaned_data["email"]
                        }
                    )
        self.after_signup(form)
        self.login_user(show_message=False)
        return redirect(self.get_success_url())

    def get_success_url(self, fallback_url=None, **kwargs):
        if fallback_url is None:
            fallback_url = settings.ALDRYN_ACCOUNTS_SIGNUP_REDIRECT_URL
        kwargs.setdefault("redirect_field_name", self.get_redirect_field_name())
        return default_redirect(self.request, fallback_url, **kwargs)

    def get_redirect_field_name(self):
        return self.redirect_field_name

    def create_user(self, form, commit=True, **kwargs):
        user = User(**kwargs)
        username = form.cleaned_data.get("username")
        if username is None:
            username = utils.generate_username()
        user.username = username
        password = form.cleaned_data.get("password")
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user

    def after_signup(self, form):
        user_signed_up.send(user=self.created_user, form=form, sender=self)

    def login_user(self, show_message=True):
        # set backend on User object to bypass needing to call auth.authenticate
        self.created_user.backend = "django.contrib.auth.backends.ModelBackend"
        auth.login(self.request, self.created_user)
        self.request.session.set_expiry(0)

        if show_message and self.messages.get("logged_in"):
            messages.add_message(
                self.request,
                self.messages["logged_in"]["level"],
                self.messages["logged_in"]["text"] % {
                    "user": utils.user_display(self.created_user)
                }
            )

    def is_open(self):
        code = self.request.POST.get("code", self.request.GET.get("code", ""))
        if not code:
            return settings.ALDRYN_ACCOUNTS_OPEN_SIGNUP
        code_is_valid = False
        try:
            signup_code = SignupCode.objects.get(code=code)
        except SignupCode.DoesNotExist:
            return settings.ALDRYN_ACCOUNTS_OPEN_SIGNUP
        if signup_code:
            self.signup_code = signup_code
            code_is_valid = signup_code.is_valid()
        return code_is_valid

    def closed(self):
        response_kwargs = {
            "request": self.request,
            "template": self.template_name_signup_closed,
        }
        return self.response_class(**response_kwargs)


class SignupEmailResendConfirmationView(FormView):
    template_name = 'aldryn_accounts/signup_email_resend_confirmation.html'
    form_class = SignupEmailResendConfirmationForm

    def get_form_kwargs(self):
        kwargs = super(SignupEmailResendConfirmationView, self).get_form_kwargs()
        return kwargs

    def _get_email(self):
        if not hasattr(self, '_email'):
            email = self.request.GET.get('email', '')
            self._email = unquote(email)
        return self._email

    def get_context_data(self, **kwargs):
        context = super(SignupEmailResendConfirmationView, self).get_context_data(**kwargs)
        email = self._get_email()
        context['email'] = email
        return context

    def get_initial(self):
        initial = super(SignupEmailResendConfirmationView, self).get_initial()
        email = self._get_email()
        initial["email"] = email
        return initial

    def get_success_url(self):
        email = self._get_email()
        url = reverse('aldryn_accounts:accounts_signup_email_confirmation_sent')
        url += '?' + urlencode({'email': email})
        return url

    def form_valid(self, form):
        email = form.cleaned_data['email']

        email_confirmations = EmailConfirmation.objects.filter(email=email)
        if not email_confirmations.exists():
            messages.error(self.request, _('This E-Mail does not have any pending confirmations.'))
            return self.form_invalid(form)

        for email_confirmation in email_confirmations:
            email_confirmation.send()

        return redirect(self.get_success_url())

    def form_invalid(self, form):
        # This shouldn't happen unless someone was tampering with the email parameter
        # or somehow managed to have invalid email in the database
        return HttpResponseRedirect(reverse('aldryn_accounts:accounts_signup'))


class SignupEmailConfirmationSentView(TemplateView):
    template_name = 'aldryn_accounts/signup_email_confirmation_sent.html'

    def get_the_email(self):
        email = self.request.GET.get('email', '')
        email = unquote(email)
        return email

    def get_context_data(self, **kwargs):
        context = super(SignupEmailConfirmationSentView, self).get_context_data(**kwargs)
        email = self.get_the_email()
        context['email'] = email
        return context


class SignupEmailSentView(TemplateView):
    template_name = 'aldryn_accounts/signup_email_sent.html'


class LoginView(class_based_auth_views.views.LoginView):
    template_name = 'aldryn_accounts/login.html'
    form_class = EmailAuthenticationForm

    def get_context_data(self, **kwargs):
        ctx = super(LoginView, self).get_context_data(**kwargs)
        # add the empty login and signup forms to the context, so that
        # the shared login/signup view works even if the context processor
        # was not added globally
        ctx.update(empty_login_and_signup_forms(self.request))  # TODO: make configurable?
        return ctx

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form, login_form=form))

    def form_valid(self, form):
        # https://docs.djangoproject.com/en/1.10/topics/http/sessions/#django.contrib.sessions.backends.base.SessionBase.set_expiry
        if not form.cleaned_data.get('remember_me'):
            # set expiry
            expiry = settings.ALDRYN_ACCOUNTS_NO_REMEMBER_ME_COOKIE_AGE
        else:
            # reset to global default
            expiry = None
        self.request.session.set_expiry(expiry)
        return super(LoginView, self).form_valid(form)


class LogoutView(class_based_auth_views.views.LogoutView):
    template_name = 'aldryn_accounts/logout.html'


def password_reset(request, *args, **kwargs):
    kwargs.update({
        'post_reset_redirect': 'aldryn_accounts:password_reset_done',
        'template_name': 'aldryn_accounts/reset/password_reset_form.html',
        'email_template_name': 'aldryn_accounts/reset/password_reset_email.html',
        'subject_template_name': 'aldryn_accounts/reset/password_reset_subject.txt',
        'password_reset_form': PasswordRecoveryResetForm,
    })
    return auth_views.password_reset(request, *args, **kwargs)


def password_reset_done(request, *args, **kwargs):
    kwargs.update({
        'template_name': 'aldryn_accounts/reset/password_reset_done.html',
    })
    return auth_views.password_reset_done(request, *args, **kwargs)


def password_reset_confirm(request, *args, **kwargs):
    kwargs.update({
        'template_name': 'aldryn_accounts/reset/password_reset_confirm.html',
        'post_reset_redirect': 'aldryn_accounts:password_reset_complete',
    })
    return auth_views.password_reset_confirm(request, *args, **kwargs)


def password_reset_complete(request, *args, **kwargs):
    kwargs.update({
        'template_name': 'aldryn_accounts/reset/password_reset_complete.html',
    })
    return auth_views.password_reset_complete(request, *args, **kwargs)


class ConfirmEmailView(TemplateView):
    # TODO: add edge case handling (see divio/djangocms-account#39 )
    template_name = "aldryn_accounts/email_confirm.html"
    messages = {
        "email_confirmed": {
            "level": messages.SUCCESS,
            "text": _("You have confirmed %(email)s.")
        },
    }

    def get(self, *args, **kwargs):
        self.object = self.get_object()
        ctx = self.get_context_data()
        return self.render_to_response(ctx)

    def post(self, *args, **kwargs):
        self.object = confirmation = self.get_object()
        try:
            email_address = confirmation.confirm(verification_method="email")
        except EmailAlreadyVerified:
            messages.error(self.request, _('This E-Mail has already been verified with an other account.'))
            return HttpResponseRedirect(self.request.path)
        except VerificationKeyExpired:
            messages.error(self.request, _('The activation key has expired.'))
            return HttpResponseRedirect(self.request.path)
        if not self.object.user.is_active:
            self.object.user.is_active = True
            self.object.user.save()
        user = email_address.user
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(self.request, user)
        redirect_url = self.get_redirect_url()
        self.has_successfully_confirmed(confirmation=confirmation)
        return redirect(redirect_url)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        try:
            return queryset.get(key=self.kwargs["key"].lower())
        except EmailConfirmation.DoesNotExist:
            raise Http404()

    def get_queryset(self):
        qs = EmailConfirmation.objects.all()
        qs = qs.select_related("user")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super(ConfirmEmailView, self).get_context_data(**kwargs)
        ctx["confirmation"] = self.object
        return ctx

    def get_redirect_url(self):
        return reverse(settings.EMAIL_CONFIRMATION_REDIRECT_URL)

    def has_successfully_confirmed(self, confirmation):
        """
        Gets called when the user has successfully confirmed his/her email.
        This method allows us to add custom handlers for this occasion.

        By default this sends a message to the user.
        """
        if self.messages.get("email_confirmed"):
            messages.add_message(
                self.request,
                self.messages["email_confirmed"]["level"],
                self.messages["email_confirmed"]["text"] % {
                    "email": confirmation.email
                }
            )


class ProfileView(TemplateView):
    template_name = 'aldryn_accounts/profile/index.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileView, self).dispatch(*args, **kwargs)


class ChangePasswordBaseView(FormView):
    template_name = "aldryn_accounts/profile/change_password.html"
    email_template_name = "aldryn_accounts/email/change_password"
    form_class = ChangePasswordForm
    redirect_field_name = "next"
    messages = {
        "password_changed": {
            "level": messages.SUCCESS,
            "text": _("Password successfully changed.")
        }
    }

    def post(self, *args, **kwargs):
        if not is_authenticated(self.request.user):
            return HttpResponseForbidden()
        return super(ChangePasswordBaseView, self).post(*args, **kwargs)

    def change_password(self, form):
        user = self.request.user
        form.save(user)
        if settings.ALDRYN_ACCOUNTS_NOTIFY_PASSWORD_CHANGE and user.email:
            self.send_email(user)
        if self.messages.get("password_changed"):
            messages.add_message(
                self.request,
                self.messages["password_changed"]["level"],
                self.messages["password_changed"]["text"]
            )
        password_changed.send(sender=ChangePasswordForm, user=user)

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        kwargs = {"user": self.request.user, "initial": self.get_initial()}
        if self.request.method in ["POST", "PUT"]:
            kwargs.update({
                "data": self.request.POST,
                "files": self.request.FILES,
            })
        return kwargs

    def form_valid(self, form):
        self.change_password(form)
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super(ChangePasswordBaseView, self).get_context_data(**kwargs)
        redirect_field_name = self.get_redirect_field_name()
        ctx.update({
            "redirect_field_name": redirect_field_name,
            "redirect_field_value": self.request.GET.get(redirect_field_name),
        })
        return ctx

    def get_redirect_field_name(self):
        return self.redirect_field_name

    def get_success_url(self, fallback_url=None, **kwargs):
        if fallback_url is None:
            fallback_url = settings.ALDRYN_ACCOUNTS_PASSWORD_CHANGE_REDIRECT_URL
        kwargs.setdefault("redirect_field_name", self.get_redirect_field_name())
        return default_redirect(self.request, fallback_url, **kwargs)

    def send_email(self, user):
        EmailSender.send_password_changed(
            user=user,
            template=self.email_template_name,
            request=self.request,
        )


class ChangePasswordView(ChangePasswordBaseView):

    @method_decorator(login_required())
    def dispatch(self, request, *args, **kwargs):
        return super(ChangePasswordView, self).dispatch(
            request, *args, **kwargs)

    def get(self, *args, **kwargs):
        if not is_authenticated(self.request.user):
            return redirect("accounts_password_reset_recover")
        if not self.request.user.has_usable_password():
            return redirect("accounts_create_password")
        return super(ChangePasswordView, self).get(*args, **kwargs)


class CreatePasswordView(ChangePasswordBaseView):
    form_class = CreatePasswordForm

    @method_decorator(login_required())
    def dispatch(self, request, *args, **kwargs):
        if request.user.has_usable_password():
            # user who already have a password must use ChangePasswordView
            return redirect(urlresolvers.reverse('aldryn_accounts:accounts_change_password'))
        else:
            return super(CreatePasswordView, self).dispatch(request, *args, **kwargs)


class ProfileAssociationsView(TemplateView):
    template_name = 'aldryn_accounts/profile/social_accounts.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileAssociationsView, self).dispatch(*args, **kwargs)


class ProfileEmailListView(OnlyOwnedObjectsMixin, ListView):
    template_name = 'aldryn_accounts/profile/email_list.html'
    queryset = chain(EmailAddress.objects.all(), EmailConfirmation.objects.all())
    profile_form_class = ProfileEmailForm

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileEmailListView, self).dispatch(*args, **kwargs)

    def get(self, *args, **kwargs):
        self.form = self.profile_form_class()
        return super(ProfileEmailListView, self).get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self.form = self.profile_form_class(self.request.POST)
        if self.form.is_valid():
            return self.form_valid(self.form)
        else:
            return super(ProfileEmailListView, self).get(*args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data['email']
        EmailConfirmation.objects.request(user=self.request.user, email=email, send=True)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_email_list')

    def get_context_data(self, **kwargs):
        context = super(ProfileEmailListView, self).get_context_data(**kwargs)
        context['add_email_form'] = self.form
        return context


class ProfileEmailConfirmationResendView(OnlyOwnedObjectsMixin, DetailView):
    template_name = 'aldryn_accounts/profile/email_confirmation_resend.html'
    model = EmailConfirmation
    messages = {
        "email_confirmation_resent": {
            "level": messages.INFO,
            "text": _("Confirmation E-Mail re-sent to %(email)s.")
        },
    }

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileEmailConfirmationResendView, self).dispatch(*args, **kwargs)

    def post(self, *args, **kwargs):
        email_confirmation = self.get_object()
        email_confirmation.send()
        message_type = 'email_confirmation_resent'
        if message_type in self.messages:
            messages.add_message(
                self.request,
                self.messages[message_type]["level"],
                self.messages[message_type]["text"] % {
                    "email": email_confirmation.email
                }
            )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_email_list')


class ProfileEmailConfirmationCancelView(OnlyOwnedObjectsMixin, DeleteView):
    template_name = 'aldryn_accounts/profile/email_confirmation_cancel.html'
    model = EmailConfirmation

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileEmailConfirmationCancelView, self).dispatch(*args, **kwargs)

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_email_list')


class ProfileEmailMakePrimaryView(OnlyOwnedObjectsMixin, UpdateView):
    template_name = 'aldryn_accounts/profile/email_make_primary.html'
    model = EmailAddress

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileEmailMakePrimaryView, self).dispatch(*args, **kwargs)

    def get_form_class(self):
        class MiniForm(forms.ModelForm):
            class Meta:
                model = EmailAddress
                fields = []
        return MiniForm

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_email_list')

    def form_valid(self, form):
        self.object.set_as_primary()
        return redirect(self.get_success_url())


class ProfileEmailDeleteView(OnlyOwnedObjectsMixin, DeleteView):
    template_name = 'aldryn_accounts/profile/email_delete.html'
    model = EmailAddress

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(ProfileEmailDeleteView, self).dispatch(*args, **kwargs)

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_email_list')

    def get_queryset(self):
        # don't allow deleting the primary email address
        return super(ProfileEmailDeleteView, self).get_queryset().filter(is_primary=False)


class UserSettingsView(UpdateView):
    model = UserSettings
    form_class = UserSettingsForm
    template_name = "aldryn_accounts/profile/usersettings_form.html"

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(UserSettingsView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        if is_anonymous(self.request.user):
            raise PermissionDenied()
        if queryset is None:
            queryset = self.get_queryset()
        user_settings, created = queryset.get_or_create(user=self.request.user)
        return user_settings

    def get_form_kwargs(self):
        kwargs = super(UserSettingsView, self).get_form_kwargs()
        if not self.object.timezone:
            self.object.timezone = self.request.session.get('django_timezone')
        return kwargs

    def get_success_url(self):
        return reverse('aldryn_accounts:accounts_profile')
